from flask import Blueprint, current_app, jsonify, redirect, request, url_for
from flask_login import current_user, login_required

from ...extensions import csrf
from ...permisos import requerir_permiso
from ...services.planes import (
    CATALOGO_CAPACIDADES,
    capacidades_del_plan,
)
from ...services.conciliacion_pagos import conciliar_antes_de_cancelar
from ...services.pagos_webpay import (
    ErrorCheckoutWebpay,
    ErrorProveedorWebpay,
    TokenWebpayInvalido,
    WebpayNoConfigurado,
    cancelar_checkout_webpay,
    confirmar_checkout_webpay,
    iniciar_checkout_webpay,
    obtener_transaccion_webpay,
)
from ...services.pagos_mercadopago import (
    ErrorCheckoutMercadoPago,
    ErrorProveedorMercadoPago,
    FirmaMercadoPagoInvalida,
    MercadoPagoNoConfigurado,
    iniciar_checkout_mercadopago,
    obtener_cliente_mercadopago,
    procesar_webhook_mercadopago,
    verificar_firma_mercadopago,
)
from ...services.suscripciones import (
    ConflictoPago,
    ErrorSuscripcion,
    FirmaWebhookInvalida,
    ProcesadorWebhooksPago,
    ServicioSuscripciones,
)

suscripciones_bp = Blueprint("suscripciones", __name__, url_prefix="/api/suscripciones")
webhooks_pago_bp = Blueprint("webhooks_pago", __name__, url_prefix="/webhooks/pagos")


def _limites(plan):
    return {
        "productos": plan.limite_productos,
        "usuarios": plan.limite_usuarios,
        "movimientos_mes": plan.limite_movimientos_mes,
        "sucursales": plan.limite_sucursales,
        "bodegas": plan.limite_bodegas,
        "almacenamiento_mb": plan.almacenamiento_mb,
    }


def _plan(plan):
    return {
        "id": plan.id,
        "codigo": plan.codigo,
        "nombre": plan.nombre,
        "descripcion": plan.descripcion,
        "precio_mensual": str(plan.precio_mensual),
        "precio_anual": str(plan.precio_anual),
        "moneda": plan.moneda,
        "limites": _limites(plan),
        "funciones": dict(plan.funciones or {}),
        "capacidades": capacidades_del_plan(plan.funciones),
    }


def _solicitud(s):
    return {
        "id": s.id,
        "plan_solicitado_id": s.plan_solicitado_id,
        "ciclo": s.ciclo,
        "monto_esperado": str(s.monto_esperado),
        "moneda": s.moneda,
        "estado": s.estado,
    }


def _error(exc, estado=400):
    return (
        jsonify({"codigo": getattr(exc, "codigo", "suscripcion_invalida"), "mensaje": str(exc)}),
        estado,
    )


@suscripciones_bp.get("")
@login_required
@requerir_permiso("suscripciones.ver")
def resumen():
    servicio = ServicioSuscripciones(current_user)
    suscripcion, solicitudes = servicio.resumen()
    plan_actual = suscripcion.plan

    return jsonify(
        {
            "suscripcion": {
                # Contrato histórico conservado.
                "plan": plan_actual.codigo,
                "estado": suscripcion.estado,
                "ciclo": suscripcion.ciclo,
                "fecha_inicio": suscripcion.fecha_inicio.isoformat(),
                "fecha_fin": (suscripcion.fecha_fin.isoformat() if suscripcion.fecha_fin else None),
                # Contrato empresarial ampliado.
                "plan_nombre": plan_actual.nombre,
                "limites": _limites(plan_actual),
                "funciones": dict(plan_actual.funciones or {}),
                "capacidades": capacidades_del_plan(plan_actual.funciones),
            },
            "catalogo_capacidades": [dict(capacidad) for capacidad in CATALOGO_CAPACIDADES],
            "planes_disponibles": [_plan(plan) for plan in servicio.planes_disponibles()],
            "solicitudes": [_solicitud(solicitud) for solicitud in solicitudes],
        }
    )


@suscripciones_bp.post("/solicitudes")
@login_required
@requerir_permiso("suscripciones.solicitar")
def solicitar():
    try:
        datos = request.get_json(silent=True) or {}
        return (
            jsonify(
                _solicitud(
                    ServicioSuscripciones(current_user).solicitar_cambio(
                        plan_codigo=datos.get("plan_codigo"), ciclo=datos.get("ciclo")
                    )
                )
            ),
            201,
        )
    except ErrorSuscripcion as exc:
        return _error(exc, 409 if isinstance(exc, ConflictoPago) else 400)


@suscripciones_bp.post("/solicitudes/<int:solicitud_id>/cancelar")
@login_required
@requerir_permiso("suscripciones.solicitar")
def cancelar(solicitud_id):
    try:
        conciliar_antes_de_cancelar(
            usuario=current_user,
            solicitud_id=solicitud_id,
            configuracion=current_app.config,
        )
        return jsonify(
            _solicitud(ServicioSuscripciones(current_user).cancelar_solicitud(solicitud_id))
        )
    except ErrorSuscripcion as exc:
        return _error(exc, 409 if isinstance(exc, ConflictoPago) else 400)


@suscripciones_bp.post("/solicitudes/<int:solicitud_id>/pagos")
@login_required
@requerir_permiso("suscripciones.solicitar")
def iniciar_pago(solicitud_id):
    try:
        datos = request.get_json(silent=True) or {}
        pago = ServicioSuscripciones(current_user).iniciar_pago(
            solicitud_id,
            proveedor=datos.get("proveedor"),
            referencia_externa=datos.get("referencia_externa"),
        )
        return (
            jsonify(
                {
                    "id": pago.id,
                    "proveedor": pago.proveedor,
                    "referencia_externa": pago.referencia_externa,
                    "estado": pago.estado,
                    "monto": str(pago.monto),
                    "moneda": pago.moneda,
                }
            ),
            201,
        )
    except ErrorSuscripcion as exc:
        return _error(exc, 409 if isinstance(exc, ConflictoPago) else 400)


def _pago_webpay(pago):
    datos = dict(pago.datos_proveedor or {})

    return {
        "id": pago.id,
        "proveedor": pago.proveedor,
        "referencia_externa": pago.referencia_externa,
        "estado": pago.estado,
        "monto": str(pago.monto),
        "moneda": pago.moneda,
        "token": datos.get("token"),
        "url_redireccion": datos.get("url_redireccion"),
    }


def _pago_mercadopago(pago):
    datos = dict(pago.datos_proveedor or {})
    return {
        "id": pago.id,
        "proveedor": pago.proveedor,
        "referencia_externa": pago.referencia_externa,
        "estado": pago.estado,
        "monto": str(pago.monto),
        "moneda": pago.moneda,
        "preferencia_id": datos.get("preferencia_id"),
        "url_redireccion": datos.get("init_point"),
    }


@suscripciones_bp.post("/solicitudes/<int:solicitud_id>" "/checkout/webpay")
@login_required
@requerir_permiso("suscripciones.solicitar")
def iniciar_checkout_webpay_route(
    solicitud_id,
):
    try:
        transaccion = obtener_transaccion_webpay(current_app.config)

        base_url = (current_app.config.get("BASE_URL") or "").rstrip("/")

        return_url = (
            base_url + "/webhooks/pagos/webpay/retorno"
            if base_url
            else url_for(
                "webhooks_pago.retorno_webpay",
                _external=True,
            )
        )

        resultado = iniciar_checkout_webpay(
            usuario=current_user,
            solicitud_id=solicitud_id,
            transaccion=transaccion,
            return_url=return_url,
        )

        return jsonify(_pago_webpay(resultado.pago)), (200 if resultado.reutilizado else 201)

    except WebpayNoConfigurado as exc:
        return _error(exc, 503)

    except ErrorProveedorWebpay as exc:
        return _error(exc, 502)

    except ConflictoPago as exc:
        return _error(exc, 409)

    except ErrorCheckoutWebpay as exc:
        return _error(exc, 400)


@suscripciones_bp.post("/solicitudes/<int:solicitud_id>/checkout/mercadopago")
@login_required
@requerir_permiso("suscripciones.solicitar")
def iniciar_checkout_mercadopago_route(solicitud_id):
    try:
        cliente = obtener_cliente_mercadopago(current_app.config)
        resultado = iniciar_checkout_mercadopago(
            usuario=current_user,
            solicitud_id=solicitud_id,
            cliente=cliente,
            base_url=current_app.config.get("BASE_URL"),
            ambiente=current_app.config.get("MERCADOPAGO_ENV", "production"),
        )
        return jsonify(_pago_mercadopago(resultado.pago)), (200 if resultado.reutilizado else 201)
    except MercadoPagoNoConfigurado as exc:
        return _error(exc, 503)
    except ErrorProveedorMercadoPago as exc:
        return _error(exc, 502)
    except ConflictoPago as exc:
        return _error(exc, 409)
    except ErrorCheckoutMercadoPago as exc:
        return _error(exc, 400)


@webhooks_pago_bp.route(
    "/webpay/retorno",
    methods=["GET", "POST"],
)
@csrf.exempt
def retorno_webpay():
    token = request.values.get("token_ws")
    token_cancelado = request.values.get("TBK_TOKEN")
    orden_cancelada = request.values.get("TBK_ORDEN_COMPRA")
    sesion_cancelada = request.values.get("TBK_ID_SESION")

    try:
        if token_cancelado:
            cancelar_checkout_webpay(
                token=token_cancelado,
                referencia=orden_cancelada,
                sesion=sesion_cancelada,
            )

            return redirect(
                url_for(
                    "panel.inicio",
                    checkout="cancelado",
                )
            )

        if not token:
            raise TokenWebpayInvalido(
                "El token Webpay no es válido"
            )

        transaccion = obtener_transaccion_webpay(
            current_app.config
        )

        confirmar_checkout_webpay(
            token=token,
            transaccion=transaccion,
        )

        return redirect(
            url_for(
                "panel.administracion_planes",
                checkout="exito",
            )
        )

    except TokenWebpayInvalido as exc:
        return _error(exc, 400)

    except ConflictoPago as exc:
        return _error(exc, 409)

    except WebpayNoConfigurado as exc:
        return _error(exc, 503)

    except ErrorProveedorWebpay as exc:
        return _error(exc, 502)

    except ErrorCheckoutWebpay as exc:
        return _error(exc, 400)


@webhooks_pago_bp.get("/mercadopago/retorno")
def retorno_mercadopago():
    resultado = str(
        request.args.get("resultado") or "pendiente"
    ).strip().lower()

    if resultado not in {"exito", "error", "pendiente"}:
        resultado = "pendiente"

    if current_user.is_authenticated:
        if current_user.rol == "super_admin":
            destino = url_for(
                "panel_superadministracion.inicio"
            )
        else:
            destino = url_for(
                "panel.inicio",
                checkout=resultado,
                proveedor="mercadopago",
            )
    else:
        destino = url_for(
            "autenticacion.ingresar",
            checkout=resultado,
            proveedor="mercadopago",
        )

    return redirect(destino)


@webhooks_pago_bp.post("/mercadopago")
@csrf.exempt
def webhook_mercadopago():
    datos = request.get_json(silent=True) or {}
    data_id = str(request.args.get("data.id") or (datos.get("data") or {}).get("id") or "").strip()
    try:
        verificar_firma_mercadopago(
            secreto=current_app.config.get("MERCADOPAGO_WEBHOOK_SECRET"),
            firma=request.headers.get("X-Signature"),
            request_id=request.headers.get("X-Request-Id"),
            data_id=data_id,
        )
        pago, procesado = procesar_webhook_mercadopago(
            cliente=obtener_cliente_mercadopago(current_app.config),
            pago_proveedor_id=data_id,
        )
        return jsonify(
            {
                "recibido": True,
                "procesado": procesado,
                "pago_id": pago.id,
                "estado": pago.estado,
            }
        )
    except FirmaMercadoPagoInvalida as exc:
        return _error(exc, 401)
    except MercadoPagoNoConfigurado as exc:
        return _error(exc, 503)
    except ConflictoPago as exc:
        return _error(exc, 409)
    except ErrorProveedorMercadoPago as exc:
        return _error(exc, 502)
    except ErrorCheckoutMercadoPago as exc:
        return _error(exc, 400)


@webhooks_pago_bp.post("/<proveedor>")
@csrf.exempt
def webhook(proveedor):
    try:
        pago, procesado = ProcesadorWebhooksPago(
            current_app.config.get("WEBHOOK_PAGOS_SECRET")
        ).procesar(
            request.get_data(cache=True),
            proveedor=proveedor,
            marca_tiempo=request.headers.get("X-NexuStock-Timestamp"),
            firma=request.headers.get("X-NexuStock-Signature"),
        )
        return jsonify(
            {"recibido": True, "procesado": procesado, "pago_id": pago.id, "estado": pago.estado}
        )
    except FirmaWebhookInvalida as exc:
        return _error(exc, 401)
    except ConflictoPago as exc:
        return _error(exc, 409)
    except ErrorSuscripcion as exc:
        return _error(exc, 400)
