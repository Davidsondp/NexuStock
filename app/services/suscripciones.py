"""Solicitudes, pagos idempotentes y activación de suscripciones."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import hmac
import json
import time

from sqlalchemy.exc import IntegrityError

from ..models import Pago, PlanSaaS, SolicitudCambioPlan, Suscripcion, db, utcnow
from ..permisos import evaluar_permiso
from .auditoria import registrar_auditoria

DOS = Decimal("0.01")
PROVEEDORES = frozenset({"mercadopago", "webpay"})
ESTADOS_PROVEEDOR = {"pagado", "rechazado", "pendiente"}


class ErrorSuscripcion(ValueError):
    codigo = "suscripcion_invalida"


class FirmaWebhookInvalida(ErrorSuscripcion):
    codigo = "firma_webhook_invalida"


class ConflictoPago(ErrorSuscripcion):
    codigo = "conflicto_pago"


class ServicioSuscripciones:
    def __init__(self, usuario):
        self.usuario = usuario
        if not usuario.empresa_id or usuario.rol == "super_admin":
            raise PermissionError("Usuario sin ámbito empresarial")

    def resumen(self):
        self._exigir("suscripciones.ver")
        suscripcion = suscripcion_facturable(self.usuario.empresa_id)
        if not suscripcion:
            raise ErrorSuscripcion("La empresa no tiene una suscripción base para renovar")
        solicitudes = list(
            db.session.scalars(
                db.select(SolicitudCambioPlan)
                .where(SolicitudCambioPlan.empresa_id == self.usuario.empresa_id)
                .order_by(SolicitudCambioPlan.creado_en.desc())
                .limit(20)
            )
        )
        return suscripcion, solicitudes

    def planes_disponibles(self):
        self._exigir("suscripciones.ver")

        consulta = (
            db.select(PlanSaaS)
            .where(
                PlanSaaS.activo.is_(True),
                PlanSaaS.codigo != "prueba",
            )
            .order_by(
                PlanSaaS.orden,
                PlanSaaS.id,
            )
        )

        return list(db.session.scalars(consulta))

    def solicitar_cambio(self, *, plan_codigo, ciclo):
        self._exigir("suscripciones.solicitar")
        ciclo = (ciclo or "").lower()
        if ciclo not in {"mensual", "anual"}:
            raise ErrorSuscripcion("El ciclo debe ser mensual o anual")
        plan = db.session.scalar(
            db.select(PlanSaaS).where(
                PlanSaaS.codigo == (plan_codigo or "").lower(), PlanSaaS.activo.is_(True)
            )
        )
        if not plan or plan.codigo == "prueba":
            raise ErrorSuscripcion("Plan comercial no disponible")
        actual = self.usuario.empresa.suscripcion_actual
        if actual and actual.plan_id == plan.id and actual.ciclo == ciclo:
            raise ErrorSuscripcion("La empresa ya utiliza ese plan y ciclo")
        pendiente = db.session.scalar(
            db.select(SolicitudCambioPlan).where(
                SolicitudCambioPlan.empresa_id == self.usuario.empresa_id,
                SolicitudCambioPlan.estado == "pendiente",
            )
        )
        if pendiente:
            raise ErrorSuscripcion("Ya existe una solicitud de cambio pendiente")
        monto = Decimal(plan.precio_mensual if ciclo == "mensual" else plan.precio_anual).quantize(
            DOS
        )
        try:
            solicitud = SolicitudCambioPlan(
                empresa_id=self.usuario.empresa_id,
                plan_solicitado_id=plan.id,
                solicitada_por_id=self.usuario.id,
                estado="pendiente",
                ciclo=ciclo,
                monto_esperado=monto,
                moneda=plan.moneda,
            )
            db.session.add(solicitud)
            db.session.flush()
            self._auditar(
                "suscripcion.solicitada",
                "SolicitudCambioPlan",
                solicitud.id,
                {"plan": plan.codigo, "ciclo": ciclo, "monto": str(monto)},
            )
            db.session.commit()
            return solicitud
        except IntegrityError as exc:
            db.session.rollback()
            raise ErrorSuscripcion("Ya existe una solicitud pendiente") from exc

    def cancelar_solicitud(self, solicitud_id):
        self._exigir("suscripciones.solicitar")
        solicitud = self._solicitud(solicitud_id, bloquear=True)
        if solicitud.estado != "pendiente":
            raise ErrorSuscripcion("Solo se cancela una solicitud pendiente")
        if db.session.scalar(
            db.select(
                db.exists().where(
                    Pago.solicitud_id == solicitud.id, Pago.estado.in_(("procesando", "pagado"))
                )
            )
        ):
            raise ErrorSuscripcion("La solicitud tiene un pago en procesamiento o confirmado")
        solicitud.estado = "cancelada"
        solicitud.revisada_en = utcnow()
        self._auditar("suscripcion.cancelada", "SolicitudCambioPlan", solicitud.id, None)
        db.session.commit()
        return solicitud

    def iniciar_pago(self, solicitud_id, *, proveedor, referencia_externa):
        self._exigir("suscripciones.solicitar")
        proveedor = (proveedor or "").lower()
        referencia = (referencia_externa or "").strip()
        if proveedor not in PROVEEDORES:
            raise ErrorSuscripcion("Proveedor de pago no admitido")
        if not referencia or len(referencia) > 150:
            raise ErrorSuscripcion("Referencia externa inválida")
        solicitud = self._solicitud(solicitud_id, bloquear=True)
        if solicitud.estado != "pendiente":
            raise ErrorSuscripcion("La solicitud no está pendiente")
        suscripcion = self.usuario.empresa.suscripcion_actual
        try:
            pago = Pago(
                empresa_id=self.usuario.empresa_id,
                suscripcion_id=suscripcion.id,
                solicitud_id=solicitud.id,
                proveedor=proveedor,
                referencia_externa=referencia,
                estado="pendiente",
                monto=solicitud.monto_esperado,
                moneda=solicitud.moneda,
                datos_proveedor={},
            )
            db.session.add(pago)
            db.session.flush()
            self._auditar(
                "pago.iniciado", "Pago", pago.id, {"proveedor": proveedor, "referencia": referencia}
            )
            db.session.commit()
            return pago
        except IntegrityError as exc:
            db.session.rollback()
            raise ConflictoPago("La referencia de pago ya fue registrada") from exc

    def _solicitud(self, solicitud_id, bloquear=False):
        q = db.select(SolicitudCambioPlan).where(
            SolicitudCambioPlan.id == solicitud_id,
            SolicitudCambioPlan.empresa_id == self.usuario.empresa_id,
        )
        solicitud = db.session.scalar(q.with_for_update() if bloquear else q)
        if not solicitud:
            raise PermissionError("Solicitud no autorizada")
        return solicitud

    def _exigir(self, permiso):
        d = evaluar_permiso(self.usuario, permiso, empresa_id=self.usuario.empresa_id)
        if not d.permitido:
            raise PermissionError(d.mensaje)

    def _auditar(self, accion, tipo, id_, datos):
        registrar_auditoria(
            accion=accion,
            modulo="suscripciones",
            usuario_id=self.usuario.id,
            empresa_id=self.usuario.empresa_id,
            entidad_tipo=tipo,
            entidad_id=id_,
            datos_nuevos=datos,
        )


class ProcesadorWebhooksPago:
    TOLERANCIA_SEGUNDOS = 300

    def __init__(self, secreto):
        if not secreto or len(secreto) < 32:
            raise RuntimeError("Secreto de webhook de pagos no configurado")
        self.secreto = secreto.encode()

    def verificar(self, cuerpo: bytes, marca_tiempo: str, firma: str, *, ahora=None):
        try:
            instante = int(marca_tiempo)
        except (TypeError, ValueError) as exc:
            raise FirmaWebhookInvalida("Marca de tiempo inválida") from exc
        ahora = int(ahora if ahora is not None else time.time())
        if abs(ahora - instante) > self.TOLERANCIA_SEGUNDOS:
            raise FirmaWebhookInvalida("Webhook vencido")
        esperada = hmac.new(
            self.secreto, marca_tiempo.encode() + b"." + cuerpo, hashlib.sha256
        ).hexdigest()
        recibida = (firma or "").removeprefix("sha256=")
        if not hmac.compare_digest(esperada, recibida):
            raise FirmaWebhookInvalida("Firma de webhook inválida")

    def procesar(self, cuerpo: bytes, *, proveedor, marca_tiempo, firma):
        self.verificar(cuerpo, marca_tiempo, firma)
        proveedor = (proveedor or "").lower()
        if proveedor not in PROVEEDORES:
            raise ErrorSuscripcion("Proveedor de pago no admitido")
        try:
            datos = json.loads(cuerpo)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ErrorSuscripcion("JSON de webhook inválido") from exc
        referencia = str(datos.get("referencia_externa", "")).strip()
        estado = str(datos.get("estado", "")).lower()
        try:
            monto = Decimal(str(datos.get("monto"))).quantize(DOS, rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError) as exc:
            raise ErrorSuscripcion("Monto inválido") from exc
        moneda = str(datos.get("moneda", "")).upper()
        if not referencia or estado not in ESTADOS_PROVEEDOR:
            raise ErrorSuscripcion("Evento de pago inválido")
        pago = db.session.scalar(
            db.select(Pago)
            .where(Pago.proveedor == proveedor, Pago.referencia_externa == referencia)
            .with_for_update()
        )
        if not pago:
            raise ErrorSuscripcion("Pago no encontrado")
        if pago.estado == "pagado":
            if estado == "pagado" and monto == Decimal(pago.monto) and moneda == pago.moneda:
                return pago, False
            raise ConflictoPago("El pago ya fue confirmado con otros datos")
        if monto != Decimal(pago.monto) or moneda != pago.moneda:
            pago.estado = "rechazado"
            pago.datos_proveedor = {"motivo": "monto_o_moneda_no_coincide"}
            db.session.commit()
            raise ConflictoPago("El monto o la moneda no coincide con la solicitud")
        try:
            pago.datos_proveedor = {"estado_recibido": estado}
            if estado == "pendiente":
                pago.estado = "procesando"
            elif estado == "rechazado":
                pago.estado = "rechazado"
            else:
                self._confirmar(pago)
            registrar_auditoria(
                accion=f"pago.{pago.estado}",
                modulo="suscripciones",
                empresa_id=pago.empresa_id,
                entidad_tipo="Pago",
                entidad_id=pago.id,
                datos_nuevos={
                    "proveedor": proveedor,
                    "referencia": referencia,
                    "estado": pago.estado,
                },
            )
            db.session.commit()
            return pago, True
        except Exception:
            db.session.rollback()
            raise

    @staticmethod
    def _confirmar(pago):
        solicitud = db.session.scalar(
            db.select(SolicitudCambioPlan)
            .where(
                SolicitudCambioPlan.id == pago.solicitud_id,
                SolicitudCambioPlan.empresa_id == pago.empresa_id,
            )
            .with_for_update()
        )
        suscripcion = db.session.scalar(
            db.select(Suscripcion)
            .where(Suscripcion.id == pago.suscripcion_id, Suscripcion.empresa_id == pago.empresa_id)
            .with_for_update()
        )
        if not solicitud or solicitud.estado != "pendiente" or not suscripcion:
            raise ConflictoPago("Solicitud o suscripción no disponible")
        ahora = utcnow()
        duracion = timedelta(days=30 if solicitud.ciclo == "mensual" else 365)
        suscripcion.plan_id = solicitud.plan_solicitado_id
        suscripcion.estado = "activa"
        suscripcion.ciclo = solicitud.ciclo
        suscripcion.fecha_inicio = ahora
        suscripcion.fecha_fin = ahora + duracion
        suscripcion.cancelada_en = None
        suscripcion.motivo_cancelacion = None
        solicitud.estado = "aprobada"
        solicitud.revisada_en = ahora
        pago.estado = "pagado"
        pago.fecha_pago = ahora
        pago.fecha_confirmacion = ahora

    @staticmethod
    def suspender_por_reembolso(pago):
        posterior = db.session.scalar(
            db.select(
                db.exists().where(
                    Pago.suscripcion_id == pago.suscripcion_id,
                    Pago.estado == "pagado",
                    Pago.id != pago.id,
                    Pago.fecha_confirmacion > pago.fecha_confirmacion,
                )
            )
        )
        if posterior:
            return False
        suscripcion = db.session.scalar(
            db.select(Suscripcion)
            .where(
                Suscripcion.id == pago.suscripcion_id,
                Suscripcion.empresa_id == pago.empresa_id,
            )
            .with_for_update()
        )
        if suscripcion and suscripcion.estado in {"activa", "prueba"}:
            suscripcion.estado = "suspendida"
            suscripcion.fecha_fin = utcnow()
            suscripcion.motivo_cancelacion = "Pago reembolsado o contracargado"
            return True
        return False


def suscripcion_facturable(empresa_id):
    return db.session.scalar(
        db.select(Suscripcion)
        .where(Suscripcion.empresa_id == empresa_id)
        .order_by(Suscripcion.fecha_inicio.desc(), Suscripcion.id.desc())
        .limit(1)
    )
