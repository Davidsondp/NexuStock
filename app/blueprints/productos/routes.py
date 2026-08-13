from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ...permisos import requerir_permiso
from ...services.productos import ErrorProducto, ServicioProductos

productos_bp = Blueprint("productos", __name__, url_prefix="/api/productos")


def _serializar(producto):
    return {"id": producto.id, "codigo": producto.codigo, "codigo_barras": producto.codigo_barras,
            "nombre": producto.nombre, "categoria": producto.categoria, "marca": producto.marca,
            "precio_venta": str(producto.precio_venta), "activo": producto.activo,
            "proveedor_principal_id": producto.proveedor_principal_id}


@productos_bp.get("")
@login_required
@requerir_permiso("productos.ver")
def listar():
    productos = ServicioProductos(current_user).listar(busqueda=request.args.get("buscar"))
    return jsonify({"productos": [_serializar(p) for p in productos]})


@productos_bp.post("")
@login_required
@requerir_permiso("productos.crear")
def crear():
    try:
        producto = ServicioProductos(current_user).crear(**(request.get_json(silent=True) or {}))
        return jsonify(_serializar(producto)), 201
    except ErrorProducto as exc:
        return jsonify({"codigo": "producto_invalido", "mensaje": str(exc)}), 400


@productos_bp.patch("/<int:producto_id>")
@login_required
@requerir_permiso("productos.editar")
def editar(producto_id):
    try:
        producto = ServicioProductos(current_user).editar(producto_id, **(request.get_json(silent=True) or {}))
        return jsonify(_serializar(producto))
    except ErrorProducto as exc:
        return jsonify({"codigo": "producto_invalido", "mensaje": str(exc)}), 400


@productos_bp.delete("/<int:producto_id>")
@login_required
@requerir_permiso("productos.eliminar")
def eliminar(producto_id):
    try:
        ServicioProductos(current_user).eliminar_logicamente(producto_id)
        return "", 204
    except ErrorProducto as exc:
        return jsonify({"codigo": "producto_con_historial", "mensaje": str(exc)}), 409

