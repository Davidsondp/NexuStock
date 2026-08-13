from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ...permisos import requerir_permiso
from ...services.compras import ErrorCompra, ServicioCompras

compras_bp = Blueprint("compras", __name__, url_prefix="/api/compras")


def _orden(orden):
    return {
        "id": orden.id, "numero": orden.numero, "estado": orden.estado,
        "proveedor_id": orden.proveedor_id, "bodega_destino_id": orden.bodega_destino_id,
        "moneda": orden.moneda, "subtotal": str(orden.subtotal),
        "descuento": str(orden.descuento), "impuesto": str(orden.impuesto),
        "total": str(orden.total),
        "items": [{"id": i.id, "producto_id": i.producto_id,
                   "cantidad": str(i.cantidad), "cantidad_recibida": str(i.cantidad_recibida),
                   "precio_unitario": str(i.precio_unitario), "total": str(i.total)}
                  for i in orden.items],
    }


def _error(exc):
    return jsonify({"codigo": getattr(exc, "codigo", "compra_invalida"), "mensaje": str(exc)}), 400


@compras_bp.get("")
@login_required
@requerir_permiso("compras.ver")
def listar():
    ordenes = ServicioCompras(current_user).listar(estado=request.args.get("estado"))
    return jsonify({"ordenes": [_orden(o) for o in ordenes]})


@compras_bp.get("/<int:orden_id>")
@login_required
@requerir_permiso("compras.ver")
def obtener(orden_id):
    return jsonify(_orden(ServicioCompras(current_user).obtener(orden_id)))


@compras_bp.post("")
@login_required
@requerir_permiso("compras.crear")
def crear():
    try:
        datos = request.get_json(silent=True) or {}
        permitidos = {k: datos[k] for k in ("numero", "proveedor_id", "bodega_destino_id",
                                             "items", "moneda", "fecha_entrega_esperada",
                                             "observaciones") if k in datos}
        return jsonify(_orden(ServicioCompras(current_user).crear(**permitidos))), 201
    except (ErrorCompra, TypeError, KeyError, ValueError) as exc:
        return _error(exc)


@compras_bp.post("/<int:orden_id>/confirmar")
@login_required
@requerir_permiso("compras.crear")
def confirmar(orden_id):
    try: return jsonify(_orden(ServicioCompras(current_user).confirmar(orden_id)))
    except ErrorCompra as exc: return _error(exc)


@compras_bp.post("/<int:orden_id>/enviar")
@login_required
@requerir_permiso("compras.enviar")
def enviar(orden_id):
    try: return jsonify(_orden(ServicioCompras(current_user).enviar(orden_id)))
    except ErrorCompra as exc: return _error(exc)


@compras_bp.post("/<int:orden_id>/cancelar")
@login_required
@requerir_permiso("compras.cancelar")
def cancelar(orden_id):
    try:
        orden = ServicioCompras(current_user).cancelar(
            orden_id, (request.get_json(silent=True) or {}).get("motivo"))
        return jsonify(_orden(orden))
    except ErrorCompra as exc: return _error(exc)


@compras_bp.post("/<int:orden_id>/recepciones")
@login_required
@requerir_permiso("compras.recibir")
def recibir(orden_id):
    try:
        datos = request.get_json(silent=True) or {}
        permitidos = {k: datos[k] for k in ("numero", "items", "documento_referencia",
                                             "observaciones") if k in datos}
        recepcion = ServicioCompras(current_user).recibir(orden_id, **permitidos)
        return jsonify({"id": recepcion.id, "numero": recepcion.numero,
                        "estado": recepcion.estado, "orden": _orden(recepcion.orden)}), 201
    except (ErrorCompra, TypeError, KeyError, ValueError) as exc:
        return _error(exc)