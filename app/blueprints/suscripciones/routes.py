from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

from ...extensions import csrf
from ...permisos import requerir_permiso
from ...services.suscripciones import (ConflictoPago, ErrorSuscripcion,
    FirmaWebhookInvalida, ProcesadorWebhooksPago, ServicioSuscripciones)

suscripciones_bp = Blueprint("suscripciones", __name__, url_prefix="/api/suscripciones")
webhooks_pago_bp = Blueprint("webhooks_pago", __name__, url_prefix="/webhooks/pagos")


def _solicitud(s):
    return {"id": s.id, "plan_solicitado_id": s.plan_solicitado_id, "ciclo": s.ciclo,
            "monto_esperado": str(s.monto_esperado), "moneda": s.moneda, "estado": s.estado}


def _error(exc, estado=400):
    return jsonify({"codigo": getattr(exc, "codigo", "suscripcion_invalida"), "mensaje": str(exc)}), estado


@suscripciones_bp.get("")
@login_required
@requerir_permiso("suscripciones.ver")
def resumen():
    suscripcion, solicitudes = ServicioSuscripciones(current_user).resumen()
    return jsonify({"suscripcion": {"plan": suscripcion.plan.codigo, "estado": suscripcion.estado,
        "ciclo": suscripcion.ciclo, "fecha_inicio": suscripcion.fecha_inicio.isoformat(),
        "fecha_fin": suscripcion.fecha_fin.isoformat() if suscripcion.fecha_fin else None},
        "solicitudes": [_solicitud(s) for s in solicitudes]})


@suscripciones_bp.post("/solicitudes")
@login_required
@requerir_permiso("suscripciones.solicitar")
def solicitar():
    try:
        datos = request.get_json(silent=True) or {}
        return jsonify(_solicitud(ServicioSuscripciones(current_user).solicitar_cambio(
            plan_codigo=datos.get("plan_codigo"), ciclo=datos.get("ciclo")))), 201
    except ErrorSuscripcion as exc: return _error(exc)


@suscripciones_bp.post("/solicitudes/<int:solicitud_id>/cancelar")
@login_required
@requerir_permiso("suscripciones.solicitar")
def cancelar(solicitud_id):
    try: return jsonify(_solicitud(ServicioSuscripciones(current_user).cancelar_solicitud(solicitud_id)))
    except ErrorSuscripcion as exc: return _error(exc)


@suscripciones_bp.post("/solicitudes/<int:solicitud_id>/pagos")
@login_required
@requerir_permiso("suscripciones.solicitar")
def iniciar_pago(solicitud_id):
    try:
        datos = request.get_json(silent=True) or {}
        pago = ServicioSuscripciones(current_user).iniciar_pago(solicitud_id,
            proveedor=datos.get("proveedor"), referencia_externa=datos.get("referencia_externa"))
        return jsonify({"id": pago.id, "proveedor": pago.proveedor,
            "referencia_externa": pago.referencia_externa, "estado": pago.estado,
            "monto": str(pago.monto), "moneda": pago.moneda}), 201
    except ErrorSuscripcion as exc: return _error(exc, 409 if isinstance(exc, ConflictoPago) else 400)


@webhooks_pago_bp.post("/<proveedor>")
@csrf.exempt
def webhook(proveedor):
    try:
        pago, procesado = ProcesadorWebhooksPago(
            current_app.config.get("WEBHOOK_PAGOS_SECRET")).procesar(
            request.get_data(cache=True), proveedor=proveedor,
            marca_tiempo=request.headers.get("X-NexuStock-Timestamp"),
            firma=request.headers.get("X-NexuStock-Signature"))
        return jsonify({"recibido": True, "procesado": procesado,
                        "pago_id": pago.id, "estado": pago.estado})
    except FirmaWebhookInvalida as exc: return _error(exc, 401)
    except ConflictoPago as exc: return _error(exc, 409)
    except ErrorSuscripcion as exc: return _error(exc, 400)