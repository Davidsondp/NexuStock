"""Conciliación conservadora antes de cancelar un cambio de plan."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..models import Pago, db, utcnow
from .auditoria import registrar_auditoria
from .pagos_mercadopago import (
    obtener_cliente_mercadopago,
    procesar_webhook_mercadopago,
)
from .pagos_webpay import (
    conciliar_checkout_webpay_autorizado,
    obtener_transaccion_webpay,
)
from .suscripciones import ConflictoPago, ErrorSuscripcion


class ConciliacionPagoNoDisponible(ErrorSuscripcion):
    codigo = "conciliacion_pago_no_disponible"


def _fecha_proveedor(valor) -> datetime | None:
    try:
        fecha = datetime.fromisoformat(str(valor or ""))
    except (TypeError, ValueError):
        return None
    if fecha.tzinfo is not None:
        fecha = fecha.astimezone(timezone.utc).replace(tzinfo=None)
    return fecha


def _rechazar(pago: Pago, *, motivo: str, estado_proveedor: str | None = None) -> None:
    anteriores = dict(pago.datos_proveedor or {})
    pago.estado = "rechazado"
    pago.datos_proveedor = {
        **anteriores,
        "motivo": motivo,
        "estado_consultado": estado_proveedor,
        "conciliado_en": utcnow().isoformat(),
    }
    registrar_auditoria(
        accion="pago.conciliado_rechazado",
        modulo="suscripciones",
        empresa_id=pago.empresa_id,
        entidad_tipo="Pago",
        entidad_id=pago.id,
        datos_nuevos={
            "proveedor": pago.proveedor,
            "referencia": pago.referencia_externa,
            "motivo": motivo,
            "estado_proveedor": estado_proveedor,
        },
    )


def _conciliar_webpay(pago: Pago, configuracion) -> None:
    datos = dict(pago.datos_proveedor or {})
    token = str(datos.get("token") or "").strip()
    iniciado_en = _fecha_proveedor(datos.get("iniciado_en"))
    if not token:
        _rechazar(pago, motivo="token_webpay_ausente")
        return

    try:
        respuesta = obtener_transaccion_webpay(configuracion).status(token)
    except Exception as exc:
        raise ConciliacionPagoNoDisponible(
            "No fue posible verificar el pago con Webpay. Intenta nuevamente en unos minutos."
        ) from exc

    estado = str((respuesta or {}).get("status") or "").upper()
    if estado in {"AUTHORIZED", "CAPTURED"}:
        if estado == "AUTHORIZED":
            conciliar_checkout_webpay_autorizado(pago=pago, respuesta=respuesta)
        raise ConflictoPago(
            "Webpay confirmó el pago y el plan fue actualizado."
        )
    if estado in {"FAILED", "REVERSED", "NULLIFIED"}:
        _rechazar(
            pago,
            motivo=f"estado_webpay_{estado.lower()}",
            estado_proveedor=estado,
        )
        return
    if estado == "INITIALIZED":
        if iniciado_en and utcnow() - iniciado_en >= timedelta(minutes=10):
            _rechazar(
                pago,
                motivo="token_webpay_vencido",
                estado_proveedor=estado,
            )
            return
        raise ConciliacionPagoNoDisponible(
            "El pago Webpay todavía puede completarse. Cancélalo en Webpay o espera su vencimiento."
        )
    raise ConciliacionPagoNoDisponible(
        "Webpay devolvió un estado que todavía requiere revisión."
    )


def _conciliar_mercadopago(pago: Pago, configuracion) -> None:
    cliente = obtener_cliente_mercadopago(configuracion)
    if not callable(getattr(cliente, "buscar_pagos", None)):
        raise ConciliacionPagoNoDisponible(
            "El cliente de Mercado Pago no permite consultar la conciliación."
        )
    try:
        resultados = cliente.buscar_pagos(pago.referencia_externa)
    except Exception as exc:
        raise ConciliacionPagoNoDisponible(
            "No fue posible verificar el pago con Mercado Pago. Intenta nuevamente en unos minutos."
        ) from exc

    for resultado in resultados:
        pago_proveedor_id = str(resultado.get("id") or "").strip()
        estado = str(resultado.get("status") or "").lower()
        if not pago_proveedor_id:
            continue
        if estado in {"approved", "pending", "in_process", "in_mediation"}:
            procesar_webhook_mercadopago(
                cliente=cliente,
                pago_proveedor_id=pago_proveedor_id,
            )
            if estado == "approved":
                raise ConflictoPago(
                    "Mercado Pago confirmó el pago y el plan fue actualizado."
                )
            raise ConciliacionPagoNoDisponible(
                "Mercado Pago todavía está procesando el pago."
            )
        if estado in {"rejected", "cancelled", "refunded", "charged_back"}:
            procesar_webhook_mercadopago(
                cliente=cliente,
                pago_proveedor_id=pago_proveedor_id,
            )

    if pago.estado not in {"pendiente", "procesando"}:
        return

    preferencia_id = str((pago.datos_proveedor or {}).get("preferencia_id") or "").strip()
    if not preferencia_id or not callable(getattr(cliente, "expirar_preferencia", None)):
        raise ConciliacionPagoNoDisponible(
            "No fue posible invalidar la preferencia pendiente de Mercado Pago."
        )
    try:
        cliente.expirar_preferencia(preferencia_id)
    except Exception as exc:
        raise ConciliacionPagoNoDisponible(
            "Mercado Pago no confirmó la cancelación de la preferencia."
        ) from exc
    _rechazar(pago, motivo="preferencia_mercadopago_expirada")


def conciliar_antes_de_cancelar(*, usuario, solicitud_id: int, configuracion) -> None:
    pagos = list(
        db.session.scalars(
            db.select(Pago)
            .where(
                Pago.empresa_id == usuario.empresa_id,
                Pago.solicitud_id == solicitud_id,
                Pago.estado.in_({"pendiente", "procesando", "pagado"}),
            )
            .order_by(Pago.id)
            .with_for_update()
        )
    )
    if any(pago.estado == "pagado" for pago in pagos):
        raise ConflictoPago("La solicitud ya tiene un pago confirmado")

    try:
        for pago in pagos:
            if pago.estado not in {"pendiente", "procesando"}:
                continue
            if pago.proveedor == "webpay":
                _conciliar_webpay(pago, configuracion)
            elif pago.proveedor == "mercadopago":
                _conciliar_mercadopago(pago, configuracion)
            else:
                raise ConciliacionPagoNoDisponible(
                    "Existe un proveedor de pago que requiere revisión manual."
                )
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
