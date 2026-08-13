from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ...permisos import requerir_permiso
from ...services.ventas import ErrorVenta, ServicioVentas

ventas_bp = Blueprint("ventas", __name__, url_prefix="/api/ventas")


def _serializar(v):
    return {"id":v.id,"numero":v.numero,"estado":v.estado,"cliente_id":v.cliente_id,
            "bodega_id":v.bodega_id,"moneda":v.moneda,"subtotal":str(v.subtotal),"descuento":str(v.descuento),
            "impuesto":str(v.impuesto),"total":str(v.total),"items":[{"id":i.id,"producto_id":i.producto_id,
            "cantidad":str(i.cantidad),"precio_unitario":str(i.precio_unitario),"total":str(i.total)} for i in v.items]}


def _error(e): return jsonify({"codigo":getattr(e,"codigo","venta_invalida"),"mensaje":str(e)}),400


@ventas_bp.get("")
@login_required
@requerir_permiso("ventas.ver")
def listar(): return jsonify({"ventas":[_serializar(v) for v in ServicioVentas(current_user).listar(request.args.get("estado"))]})


@ventas_bp.get("/<int:venta_id>")
@login_required
@requerir_permiso("ventas.ver")
def obtener(venta_id): return jsonify(_serializar(ServicioVentas(current_user).obtener(venta_id)))


@ventas_bp.post("")
@login_required
@requerir_permiso("ventas.crear")
def crear():
    try:
        d=request.get_json(silent=True) or {}; permitidos={k:d[k] for k in ("numero","bodega_id","items","cliente_id","moneda","observaciones") if k in d}
        return jsonify(_serializar(ServicioVentas(current_user).crear(**permitidos))),201
    except (ErrorVenta,TypeError,KeyError,ValueError) as e: return _error(e)


@ventas_bp.post("/<int:venta_id>/reservar")
@login_required
@requerir_permiso("ventas.reservar")
def reservar(venta_id):
    try: return jsonify(_serializar(ServicioVentas(current_user).reservar(venta_id)))
    except ErrorVenta as e: return _error(e)


@ventas_bp.post("/<int:venta_id>/confirmar")
@login_required
@requerir_permiso("ventas.confirmar")
def confirmar(venta_id):
    try: return jsonify(_serializar(ServicioVentas(current_user).confirmar(venta_id)))
    except ErrorVenta as e: return _error(e)


@ventas_bp.post("/<int:venta_id>/cancelar")
@login_required
@requerir_permiso("ventas.cancelar")
def cancelar(venta_id):
    try: return jsonify(_serializar(ServicioVentas(current_user).cancelar(venta_id,(request.get_json(silent=True) or {}).get("motivo"))))
    except ErrorVenta as e: return _error(e)