"""Checkout Pro de Mercado Pago con confirmación consultada al proveedor."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import hmac
import time
from typing import Any
from uuid import uuid4

import requests
from sqlalchemy.exc import IntegrityError

from ..models import Pago, PlanSaaS, SolicitudCambioPlan, db, utcnow
from ..permisos import evaluar_permiso
from .auditoria import registrar_auditoria
from .suscripciones import ConflictoPago, ProcesadorWebhooksPago, suscripcion_facturable


class ErrorCheckoutMercadoPago(ValueError):
    codigo = "checkout_mercadopago_invalido"


class MercadoPagoNoConfigurado(ErrorCheckoutMercadoPago):
    codigo = "mercadopago_no_configurado"


class ErrorProveedorMercadoPago(ErrorCheckoutMercadoPago):
    codigo = "mercadopago_no_disponible"


class FirmaMercadoPagoInvalida(ErrorCheckoutMercadoPago):
    codigo = "firma_mercadopago_invalida"


@dataclass(frozen=True)
class ResultadoCheckoutMercadoPago:
    pago: Pago
    reutilizado: bool


class ClienteMercadoPago:
    API_URL = "https://api.mercadopago.com"

    def __init__(self, access_token: str, *, timeout: int = 15):
        self.access_token = access_token
        self.timeout = timeout

    def _solicitar(self, metodo: str, ruta: str, **kwargs) -> dict:
        encabezados = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            **kwargs.pop("headers", {}),
        }
        try:
            respuesta = requests.request(
                metodo,
                self.API_URL + ruta,
                headers=encabezados,
                timeout=self.timeout,
                **kwargs,
            )
            respuesta.raise_for_status()
            datos = respuesta.json()
        except (requests.RequestException, ValueError) as exc:
            raise ErrorProveedorMercadoPago("No fue posible comunicarse con Mercado Pago") from exc
        if not isinstance(datos, dict):
            raise ErrorProveedorMercadoPago("Mercado Pago devolvió una respuesta inválida")
        return datos

    def crear_preferencia(self, datos: dict, clave_idempotencia: str) -> dict:
        return self._solicitar(
            "POST",
            "/checkout/preferences",
            json=datos,
            headers={"X-Idempotency-Key": clave_idempotencia},
        )

    def obtener_pago(self, pago_id: str) -> dict:
        return self._solicitar("GET", f"/v1/payments/{pago_id}")


def obtener_cliente_mercadopago(configuracion):
    fabrica = configuracion.get("MERCADOPAGO_CLIENTE_FACTORY")
    if callable(fabrica):
        return fabrica()
    token = str(configuracion.get("MERCADOPAGO_ACCESS_TOKEN") or "").strip()
    if not token:
        raise MercadoPagoNoConfigurado("Mercado Pago todavía no está configurado")
    return ClienteMercadoPago(token)


def _referencia(empresa_id: int, solicitud_id: int) -> str:
    return f"NS-MP-{empresa_id}-{solicitud_id}-{uuid4().hex[:16].upper()}"


def _pago_reutilizable(empresa_id: int, solicitud_id: int) -> Pago | None:
    pagos = db.session.scalars(
        db.select(Pago)
        .where(
            Pago.empresa_id == empresa_id,
            Pago.solicitud_id == solicitud_id,
            Pago.proveedor == "mercadopago",
            Pago.estado.in_({"pendiente", "procesando"}),
        )
        .order_by(Pago.id.desc())
    )
    return next((p for p in pagos if (p.datos_proveedor or {}).get("init_point")), None)


def iniciar_checkout_mercadopago(
    *, usuario, solicitud_id: int, cliente, base_url: str, ambiente: str
) -> ResultadoCheckoutMercadoPago:
    decision = evaluar_permiso(usuario, "suscripciones.solicitar", empresa_id=usuario.empresa_id)
    if not decision.permitido:
        raise PermissionError(decision.mensaje)
    solicitud = db.session.scalar(
        db.select(SolicitudCambioPlan)
        .where(
            SolicitudCambioPlan.id == solicitud_id,
            SolicitudCambioPlan.empresa_id == usuario.empresa_id,
        )
        .with_for_update()
    )
    if not solicitud:
        raise PermissionError("Solicitud no autorizada")
    if solicitud.estado != "pendiente":
        raise ErrorCheckoutMercadoPago("La solicitud no está pendiente")
    existente = _pago_reutilizable(usuario.empresa_id, solicitud.id)
    if existente:
        return ResultadoCheckoutMercadoPago(existente, True)
    otro_checkout = db.session.scalar(
        db.select(Pago)
        .where(
            Pago.empresa_id == usuario.empresa_id,
            Pago.solicitud_id == solicitud.id,
            Pago.proveedor != "mercadopago",
            Pago.estado.in_({"pendiente", "procesando", "pagado"}),
        )
        .with_for_update()
    )
    if otro_checkout:
        raise ConflictoPago("La solicitud ya tiene un pago activo con otro proveedor")
    suscripcion = suscripcion_facturable(usuario.empresa_id)
    if not suscripcion:
        raise ErrorCheckoutMercadoPago("La empresa no tiene una suscripción vigente")
    base_url = str(base_url or "").strip().rstrip("/")
    if not base_url.startswith("https://"):
        raise MercadoPagoNoConfigurado("BASE_URL HTTPS es obligatoria para Mercado Pago")
    referencia = _referencia(usuario.empresa_id, solicitud.id)
    monto = Decimal(solicitud.monto_esperado).quantize(Decimal("0.01"))
    plan = db.session.get(PlanSaaS, solicitud.plan_solicitado_id)
    if not plan:
        raise ErrorCheckoutMercadoPago("El plan solicitado no está disponible")
    try:
        pago = Pago(
            empresa_id=usuario.empresa_id,
            suscripcion_id=suscripcion.id,
            solicitud_id=solicitud.id,
            proveedor="mercadopago",
            referencia_externa=referencia,
            estado="pendiente",
            monto=monto,
            moneda=solicitud.moneda,
            metodo="checkout_pro",
            datos_proveedor={},
        )
        db.session.add(pago)
        db.session.flush()
        preferencia = cliente.crear_preferencia(
            {
                "items": [
                    {
                        "id": str(plan.id),
                        "title": f"NexuStock - Plan {plan.nombre}",
                        "description": f"Suscripción {solicitud.ciclo}",
                        "quantity": 1,
                        "currency_id": solicitud.moneda,
                        "unit_price": float(monto),
                    }
                ],
                "external_reference": referencia,
                "metadata": {
                    "pago_id": str(pago.id),
                    "empresa_id": str(usuario.empresa_id),
                    "solicitud_id": str(solicitud.id),
                },
                "payer": {"email": usuario.email},
                "back_urls": {
                    "success": base_url + "/panel/administracion/planes?checkout=exito",
                    "failure": base_url + "/panel/administracion/planes?checkout=error",
                    "pending": base_url + "/panel/administracion/planes?checkout=pendiente",
                },
                "auto_return": "approved",
                "notification_url": base_url + "/webhooks/pagos/mercadopago",
            },
            referencia,
        )
        preferencia_id = str(preferencia.get("id") or "").strip()
        campo_url = "sandbox_init_point" if ambiente == "sandbox" else "init_point"
        init_point = str(preferencia.get(campo_url) or preferencia.get("init_point") or "").strip()
        if not preferencia_id or not init_point.startswith("https://"):
            raise ErrorProveedorMercadoPago("Mercado Pago no entregó una preferencia válida")
        pago.estado = "procesando"
        pago.datos_proveedor = {
            "preferencia_id": preferencia_id,
            "init_point": init_point,
            "iniciado_en": utcnow().isoformat(),
        }
        registrar_auditoria(
            accion="pago.mercadopago_iniciado",
            modulo="suscripciones",
            usuario_id=usuario.id,
            empresa_id=usuario.empresa_id,
            entidad_tipo="Pago",
            entidad_id=pago.id,
            datos_nuevos={
                "referencia": referencia,
                "monto": str(monto),
                "moneda": solicitud.moneda,
                "solicitud_id": solicitud.id,
            },
        )
        db.session.commit()
        return ResultadoCheckoutMercadoPago(pago, False)
    except IntegrityError as exc:
        db.session.rollback()
        raise ErrorCheckoutMercadoPago("No fue posible registrar el pago") from exc
    except ErrorCheckoutMercadoPago:
        db.session.rollback()
        raise
    except Exception as exc:
        db.session.rollback()
        raise ErrorProveedorMercadoPago("No fue posible iniciar Mercado Pago") from exc


def verificar_firma_mercadopago(*, secreto: str, firma: str, request_id: str, data_id: str) -> None:
    if not secreto:
        raise MercadoPagoNoConfigurado("Secreto de webhook de Mercado Pago no configurado")
    partes = {}
    for componente in str(firma or "").split(","):
        clave, separador, valor = componente.strip().partition("=")
        if separador:
            partes[clave] = valor
    ts, recibida = partes.get("ts"), partes.get("v1")
    if not ts or not recibida or not request_id or not data_id:
        raise FirmaMercadoPagoInvalida("Firma de Mercado Pago incompleta")
    try:
        marca_tiempo = int(ts)
    except (TypeError, ValueError) as exc:
        raise FirmaMercadoPagoInvalida("Marca de tiempo de Mercado Pago inválida") from exc
    ahora_ms = int(time.time() * 1000)
    marca_ms = marca_tiempo if marca_tiempo > 10_000_000_000 else marca_tiempo * 1000
    if abs(ahora_ms - marca_ms) > 5 * 60 * 1000:
        raise FirmaMercadoPagoInvalida("Firma de Mercado Pago vencida")
    manifiesto = f"id:{data_id};request-id:{request_id};ts:{ts};"
    esperada = hmac.new(secreto.encode(), manifiesto.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(esperada, recibida):
        raise FirmaMercadoPagoInvalida("Firma de Mercado Pago inválida")


def procesar_webhook_mercadopago(*, cliente, pago_proveedor_id: str) -> tuple[Pago, bool]:
    datos = cliente.obtener_pago(str(pago_proveedor_id))
    referencia = str(datos.get("external_reference") or "").strip()
    pago = db.session.scalar(
        db.select(Pago)
        .where(
            Pago.proveedor == "mercadopago",
            Pago.referencia_externa == referencia,
        )
        .with_for_update()
    )
    if not pago:
        raise ErrorCheckoutMercadoPago("Pago de Mercado Pago no encontrado")
    estado = str(datos.get("status") or "").lower()
    try:
        monto = Decimal(str(datos.get("transaction_amount"))).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError) as exc:
        raise ConflictoPago("Mercado Pago devolvió un monto inválido") from exc
    moneda = str(datos.get("currency_id") or "").upper()
    if monto != Decimal(pago.monto) or moneda != pago.moneda:
        pago.estado = "rechazado"
        pago.datos_proveedor = {
            **(pago.datos_proveedor or {}),
            "motivo": "monto_o_moneda_no_coincide",
        }
        db.session.commit()
        raise ConflictoPago("El monto o la moneda no coincide con la solicitud")
    if pago.estado == "pagado" and estado == "approved":
        return pago, False
    anteriores = dict(pago.datos_proveedor or {})
    pago.datos_proveedor = {
        **anteriores,
        "pago_proveedor_id": str(datos.get("id") or pago_proveedor_id),
        "estado_recibido": estado,
        "payment_type_id": datos.get("payment_type_id"),
        "confirmado_en": utcnow().isoformat(),
    }
    if estado == "approved":
        ProcesadorWebhooksPago._confirmar(pago)
    elif estado in {"rejected", "cancelled", "refunded", "charged_back"}:
        pago.estado = "rechazado" if estado in {"rejected", "cancelled"} else "reembolsado"
        if estado in {"refunded", "charged_back"}:
            ProcesadorWebhooksPago.suspender_por_reembolso(pago)
    else:
        pago.estado = "procesando"
    registrar_auditoria(
        accion=f"pago.mercadopago_{pago.estado}",
        modulo="suscripciones",
        empresa_id=pago.empresa_id,
        entidad_tipo="Pago",
        entidad_id=pago.id,
        datos_nuevos={"referencia": referencia, "estado_proveedor": estado},
    )
    db.session.commit()
    return pago, True
