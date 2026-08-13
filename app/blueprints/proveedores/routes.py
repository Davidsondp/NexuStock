from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ...permisos import requerir_permiso
from ...services.proveedores import ErrorProveedor, ServicioProveedores

proveedores_bp = Blueprint("proveedores", __name__, url_prefix="/api/proveedores")


def _serializar(proveedor):
    return {"id": proveedor.id, "nombre": proveedor.nombre,
            "identificacion_fiscal": proveedor.identificacion_fiscal,
            "email": proveedor.email, "telefono": proveedor.telefono,
            "dias_entrega": proveedor.dias_entrega,
            "compra_minima": str(proveedor.compra_minima), "activo": proveedor.activo}


@proveedores_bp.get("")
@login_required
@requerir_permiso("proveedores.ver")
def listar():
    return jsonify({"proveedores": [_serializar(p) for p in ServicioProveedores(current_user).listar()]})


@proveedores_bp.post("")
@login_required
@requerir_permiso("proveedores.crear")
def crear():
    try:
        proveedor = ServicioProveedores(current_user).crear(**(request.get_json(silent=True) or {}))
        return jsonify(_serializar(proveedor)), 201
    except ErrorProveedor as exc:
        return jsonify({"codigo": "proveedor_invalido", "mensaje": str(exc)}), 400


@proveedores_bp.patch("/<int:proveedor_id>")
@login_required
@requerir_permiso("proveedores.editar")
def editar(proveedor_id):
    try:
        proveedor = ServicioProveedores(current_user).editar(proveedor_id, **(request.get_json(silent=True) or {}))
        return jsonify(_serializar(proveedor))
    except ErrorProveedor as exc:
        return jsonify({"codigo": "proveedor_invalido", "mensaje": str(exc)}), 400


@proveedores_bp.delete("/<int:proveedor_id>")
@login_required
@requerir_permiso("proveedores.eliminar")
def eliminar(proveedor_id):
    try:
        ServicioProveedores(current_user).eliminar_logicamente(proveedor_id)
        return "", 204
    except ErrorProveedor as exc:
        return jsonify({"codigo": "proveedor_con_historial", "mensaje": str(exc)}), 409

