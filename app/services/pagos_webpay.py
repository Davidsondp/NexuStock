"""Inicio seguro de transacciones Webpay Plus."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import requests
from sqlalchemy.exc import IntegrityError

from ..models import (
    Pago,
    SolicitudCambioPlan,
    db,
    utcnow,
)
from ..permisos import evaluar_permiso
from .auditoria import registrar_auditoria
from .suscripciones import (
    ConflictoPago,
    ProcesadorWebhooksPago,
    suscripcion_facturable,
)


class ErrorCheckoutWebpay(ValueError):
    codigo = "checkout_webpay_invalido"


class WebpayNoConfigurado(ErrorCheckoutWebpay):
    codigo = "webpay_no_configurado"


class ErrorProveedorWebpay(ErrorCheckoutWebpay):
    codigo = "webpay_no_disponible"


@dataclass(frozen=True)
class ResultadoCheckoutWebpay:
    pago: Pago
    reutilizado: bool


class ClienteWebpayPlus:
    """Cliente REST mínimo para las operaciones Webpay Plus utilizadas."""

    _RUTA = "/rswebpaytransaction/api/webpay/v1.2/transactions"

    def __init__(
        self,
        *,
        base_url: str,
        codigo_comercio: str,
        api_key: str,
        timeout: tuple[int, int] = (5, 20),
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {
            "Tbk-Api-Key-Id": codigo_comercio,
            "Tbk-Api-Key-Secret": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _solicitar(self, metodo: str, url: str, **kwargs) -> dict:
        respuesta = requests.request(
            metodo,
            url,
            headers=self.headers,
            timeout=self.timeout,
            **kwargs,
        )
        respuesta.raise_for_status()
        datos = respuesta.json()

        if not isinstance(datos, dict):
            raise ValueError("Webpay devolvió una respuesta inválida")

        return datos

    def create(self, buy_order, session_id, amount, return_url) -> dict:
        monto = Decimal(amount)
        monto_json: int | float = int(monto) if monto == monto.to_integral_value() else float(monto)
        return self._solicitar(
            "POST",
            f"{self.base_url}{self._RUTA}",
            json={
                "buy_order": str(buy_order),
                "session_id": str(session_id),
                "amount": monto_json,
                "return_url": str(return_url),
            },
        )

    def commit(self, token) -> dict:
        token_seguro = quote(str(token), safe="")
        return self._solicitar(
            "PUT",
            f"{self.base_url}{self._RUTA}/{token_seguro}",
        )


def obtener_transaccion_webpay(
    configuracion,
):
    fabrica = configuracion.get("WEBPAY_TRANSACCION_FACTORY")

    if callable(fabrica):
        return fabrica()

    codigo_comercio = str(configuracion.get("WEBPAY_COMMERCE_CODE") or "").strip()
    api_key = str(configuracion.get("WEBPAY_API_KEY") or "").strip()
    ambiente = str(configuracion.get("WEBPAY_ENV") or "").strip().lower()

    if ambiente not in {
        "integration",
        "production",
    }:
        raise WebpayNoConfigurado("El ambiente Webpay debe ser " "integration o production")

    if not codigo_comercio or not api_key:
        raise WebpayNoConfigurado("Webpay todavía no está configurado")

    if ambiente == "integration":
        base_url = "https://webpay3gint.transbank.cl"
    else:
        base_url = "https://webpay3g.transbank.cl"

    return ClienteWebpayPlus(
        base_url=base_url,
        codigo_comercio=codigo_comercio,
        api_key=api_key,
    )


def _referencia_pago(
    empresa_id: int,
    solicitud_id: int,
) -> str:
    aleatorio = uuid4().hex[:12].upper()

    return (f"NS-{empresa_id}-" f"{solicitud_id}-" f"{aleatorio}")[:26]


def _sesion_webpay(
    usuario_id: int,
) -> str:
    return (f"usuario-{usuario_id}-" f"{uuid4().hex}")[:61]


def _dato_respuesta(
    respuesta: Any,
    nombre: str,
):
    if isinstance(respuesta, dict):
        return respuesta.get(nombre)

    return getattr(
        respuesta,
        nombre,
        None,
    )


def _pago_reutilizable(
    *,
    empresa_id: int,
    solicitud_id: int,
) -> Pago | None:
    pagos = db.session.scalars(
        db.select(Pago)
        .where(
            Pago.empresa_id == empresa_id,
            Pago.solicitud_id == solicitud_id,
            Pago.proveedor == "webpay",
            Pago.estado.in_(
                {
                    "pendiente",
                    "procesando",
                }
            ),
        )
        .order_by(Pago.id.desc())
    )

    for pago in pagos:
        datos = dict(pago.datos_proveedor or {})

        if datos.get("token") and datos.get("url_redireccion"):
            return pago

    return None


def iniciar_checkout_webpay(
    *,
    usuario,
    solicitud_id: int,
    transaccion,
    return_url: str,
) -> ResultadoCheckoutWebpay:
    decision = evaluar_permiso(
        usuario,
        "suscripciones.solicitar",
        empresa_id=usuario.empresa_id,
    )

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
        raise ErrorCheckoutWebpay("La solicitud no está pendiente")

    existente = _pago_reutilizable(
        empresa_id=usuario.empresa_id,
        solicitud_id=solicitud.id,
    )

    if existente:
        return ResultadoCheckoutWebpay(
            pago=existente,
            reutilizado=True,
        )

    otro_checkout = db.session.scalar(
        db.select(Pago)
        .where(
            Pago.empresa_id == usuario.empresa_id,
            Pago.solicitud_id == solicitud.id,
            Pago.proveedor != "webpay",
            Pago.estado.in_(
                {
                    "pendiente",
                    "procesando",
                    "pagado",
                }
            ),
        )
        .with_for_update()
    )

    if otro_checkout:
        raise ConflictoPago("La solicitud ya tiene un pago " "activo con otro proveedor")

    suscripcion = suscripcion_facturable(usuario.empresa_id)

    if not suscripcion:
        raise ErrorCheckoutWebpay("La empresa no tiene una " "suscripción vigente")

    referencia = _referencia_pago(
        usuario.empresa_id,
        solicitud.id,
    )
    sesion = _sesion_webpay(usuario.id)
    monto = Decimal(solicitud.monto_esperado).quantize(Decimal("0.01"))

    try:
        pago = Pago(
            empresa_id=usuario.empresa_id,
            suscripcion_id=suscripcion.id,
            solicitud_id=solicitud.id,
            proveedor="webpay",
            referencia_externa=referencia,
            estado="pendiente",
            monto=monto,
            moneda=solicitud.moneda,
            metodo="webpay_plus",
            datos_proveedor={
                "session_id": sesion,
                "return_url": return_url,
            },
        )

        db.session.add(pago)
        db.session.flush()

        respuesta = transaccion.create(
            referencia,
            sesion,
            monto,
            return_url,
        )

        token = _dato_respuesta(
            respuesta,
            "token",
        )
        url_redireccion = _dato_respuesta(
            respuesta,
            "url",
        )

        if not token or not url_redireccion:
            raise ErrorProveedorWebpay("Webpay no entregó una " "transacción válida")

        pago.estado = "procesando"
        pago.datos_proveedor = {
            "session_id": sesion,
            "return_url": return_url,
            "token": str(token),
            "url_redireccion": str(url_redireccion),
            "iniciado_en": (utcnow().isoformat()),
        }

        registrar_auditoria(
            accion="pago.webpay_iniciado",
            modulo="suscripciones",
            usuario_id=usuario.id,
            empresa_id=usuario.empresa_id,
            entidad_tipo="Pago",
            entidad_id=pago.id,
            datos_nuevos={
                "proveedor": "webpay",
                "referencia": referencia,
                "solicitud_id": solicitud.id,
                "monto": str(monto),
                "moneda": solicitud.moneda,
            },
        )

        db.session.commit()

        return ResultadoCheckoutWebpay(
            pago=pago,
            reutilizado=False,
        )

    except IntegrityError as exc:
        db.session.rollback()
        raise ErrorCheckoutWebpay("No fue posible registrar " "el pago") from exc

    except ErrorCheckoutWebpay:
        db.session.rollback()
        raise

    except Exception as exc:
        db.session.rollback()
        raise ErrorProveedorWebpay("No fue posible comunicarse " "con Webpay") from exc


class TokenWebpayInvalido(ErrorCheckoutWebpay):
    codigo = "token_webpay_invalido"


@dataclass(frozen=True)
class ResultadoConfirmacionWebpay:
    pago: Pago
    reutilizado: bool


def _buscar_pago_por_token(
    token: str,
) -> Pago | None:
    return db.session.scalar(
        db.select(Pago)
        .where(
            Pago.proveedor == "webpay",
            Pago.datos_proveedor["token"].as_string() == token,
        )
        .with_for_update()
    )


def cancelar_checkout_webpay(
    *,
    token: str,
    referencia: str | None = None,
    sesion: str | None = None,
) -> Pago:
    """Registra una cancelaci?n desde el formulario de Webpay sin ejecutar commit."""

    token = str(token or "").strip()
    referencia = str(referencia or "").strip()
    sesion = str(sesion or "").strip()

    if not token:
        raise TokenWebpayInvalido("El token Webpay no es v?lido")

    pago = _buscar_pago_por_token(token)

    if not pago:
        raise TokenWebpayInvalido(
            "El token Webpay no corresponde a un pago"
        )

    datos = dict(pago.datos_proveedor or {})

    if referencia and pago.referencia_externa != referencia:
        raise TokenWebpayInvalido(
            "La orden de compra no corresponde al pago"
        )

    sesion_registrada = str(datos.get("session_id") or "").strip()

    if sesion and sesion_registrada and sesion != sesion_registrada:
        raise TokenWebpayInvalido(
            "La sesi?n Webpay no corresponde al pago"
        )

    if pago.estado == "pagado":
        raise ConflictoPago(
            "El pago ya fue confirmado y no puede cancelarse"
        )

    if pago.estado in {"rechazado", "anulado", "reembolsado"}:
        return pago

    pago.estado = "rechazado"
    pago.datos_proveedor = {
        **datos,
        "cancelado_por_usuario": True,
        "cancelado_en": utcnow().isoformat(),
        "tbk_orden_compra": referencia or None,
        "tbk_id_sesion": sesion or None,
        "motivo": "Cancelado por el usuario en Webpay",
    }

    registrar_auditoria(
        accion="pago.webpay_cancelado_usuario",
        modulo="suscripciones",
        empresa_id=pago.empresa_id,
        entidad_tipo="Pago",
        entidad_id=pago.id,
        datos_nuevos={
            "proveedor": "webpay",
            "referencia": pago.referencia_externa,
            "estado": pago.estado,
            "motivo": "Cancelado por el usuario en Webpay",
        },
    )

    db.session.commit()
    return pago


def _respuesta_webpay_segura(
    respuesta: Any,
) -> dict:
    tarjeta = _dato_respuesta(
        respuesta,
        "card_detail",
    )

    if not isinstance(tarjeta, dict):
        tarjeta = {}

    return {
        "status": _dato_respuesta(
            respuesta,
            "status",
        ),
        "response_code": _dato_respuesta(
            respuesta,
            "response_code",
        ),
        "buy_order": _dato_respuesta(
            respuesta,
            "buy_order",
        ),
        "session_id": _dato_respuesta(
            respuesta,
            "session_id",
        ),
        "amount": str(
            _dato_respuesta(
                respuesta,
                "amount",
            )
        ),
        "authorization_code": _dato_respuesta(
            respuesta,
            "authorization_code",
        ),
        "payment_type_code": _dato_respuesta(
            respuesta,
            "payment_type_code",
        ),
        "installments_number": _dato_respuesta(
            respuesta,
            "installments_number",
        ),
        "transaction_date": _dato_respuesta(
            respuesta,
            "transaction_date",
        ),
        "accounting_date": _dato_respuesta(
            respuesta,
            "accounting_date",
        ),
        "vci": _dato_respuesta(
            respuesta,
            "vci",
        ),
        "card_number": tarjeta.get("card_number"),
    }


def _rechazar_confirmacion(
    *,
    pago: Pago,
    datos: dict,
    motivo: str,
) -> None:
    anteriores = dict(pago.datos_proveedor or {})
    pago.estado = "rechazado"
    pago.datos_proveedor = {
        **anteriores,
        **datos,
        "motivo": motivo,
        "confirmado_en": (utcnow().isoformat()),
    }

    registrar_auditoria(
        accion="pago.webpay_rechazado",
        modulo="suscripciones",
        empresa_id=pago.empresa_id,
        entidad_tipo="Pago",
        entidad_id=pago.id,
        datos_nuevos={
            "proveedor": "webpay",
            "referencia": pago.referencia_externa,
            "motivo": motivo,
        },
    )

    db.session.commit()


def confirmar_checkout_webpay(
    *,
    token: str,
    transaccion,
) -> ResultadoConfirmacionWebpay:
    token = str(token or "").strip()

    if not token or len(token) > 128:
        raise TokenWebpayInvalido("El token Webpay no es válido")

    pago = _buscar_pago_por_token(token)

    if not pago:
        raise TokenWebpayInvalido("El token Webpay no corresponde " "a un pago")

    if pago.estado == "pagado":
        return ResultadoConfirmacionWebpay(
            pago=pago,
            reutilizado=True,
        )

    if pago.estado not in {
        "pendiente",
        "procesando",
    }:
        raise ConflictoPago("El pago ya no puede confirmarse")

    try:
        respuesta = transaccion.commit(token)
    except Exception as exc:
        db.session.rollback()
        raise ErrorProveedorWebpay("No fue posible confirmar " "el pago con Webpay") from exc

    datos = _respuesta_webpay_segura(respuesta)
    anteriores = dict(pago.datos_proveedor or {})

    try:
        monto_recibido = Decimal(datos["amount"]).quantize(Decimal("0.01"))
    except Exception:
        _rechazar_confirmacion(
            pago=pago,
            datos=datos,
            motivo="monto_invalido",
        )
        raise ConflictoPago("Webpay devolvió un monto inválido")

    validaciones = (
        (
            datos["status"] == "AUTHORIZED",
            "transaccion_no_autorizada",
        ),
        (
            datos["response_code"] == 0,
            "codigo_respuesta_rechazado",
        ),
        (
            datos["buy_order"] == pago.referencia_externa,
            "orden_no_coincide",
        ),
        (
            datos["session_id"] == anteriores.get("session_id"),
            "sesion_no_coincide",
        ),
        (
            monto_recibido == Decimal(pago.monto),
            "monto_no_coincide",
        ),
        (
            pago.moneda == "CLP",
            "moneda_no_admitida",
        ),
    )

    motivo = next(
        (codigo for valido, codigo in validaciones if not valido),
        None,
    )

    if motivo:
        _rechazar_confirmacion(
            pago=pago,
            datos=datos,
            motivo=motivo,
        )
        raise ConflictoPago("La confirmación Webpay " "no coincide con el pago")

    try:
        pago.datos_proveedor = {
            **anteriores,
            **datos,
            "confirmado_en": (utcnow().isoformat()),
        }

        # Única transición existente para:
        # pago, solicitud y suscripción.
        ProcesadorWebhooksPago._confirmar(pago)

        registrar_auditoria(
            accion="pago.webpay_pagado",
            modulo="suscripciones",
            empresa_id=pago.empresa_id,
            entidad_tipo="Pago",
            entidad_id=pago.id,
            datos_nuevos={
                "proveedor": "webpay",
                "referencia": pago.referencia_externa,
                "authorization_code": (datos["authorization_code"]),
                "estado": pago.estado,
            },
        )

        db.session.commit()

        return ResultadoConfirmacionWebpay(
            pago=pago,
            reutilizado=False,
        )

    except Exception:
        db.session.rollback()
        raise
