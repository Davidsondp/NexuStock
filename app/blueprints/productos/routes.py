from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ...permisos import requerir_permiso
from ...services.productos import ErrorProducto, ServicioProductos

productos_bp = Blueprint("productos", __name__, url_prefix="/api/productos")


def _serializar(producto):
    return {
        "id": producto.id,
        "codigo": producto.codigo,
        "codigo_barras": producto.codigo_barras,
        "nombre": producto.nombre,
        "descripcion": producto.descripcion,
        "categoria": producto.categoria,
        "subcategoria": producto.subcategoria,
        "marca": producto.marca,
        "unidad_medida": producto.unidad_medida,
        "unidades_por_caja": str(producto.unidades_por_caja),
        "costo_referencia": str(producto.costo_referencia),
        "precio_venta": str(producto.precio_venta),
        "incluye_iva": producto.incluye_iva,
        "tasa_impuesto": str(producto.tasa_impuesto),
        "stock_minimo": str(producto.stock_minimo),
        "punto_reorden": str(producto.punto_reorden),
        "stock_maximo": (
            str(producto.stock_maximo)
            if producto.stock_maximo is not None
            else None
        ),
        "requiere_serial": producto.requiere_serial,
        "controla_lotes": producto.controla_lotes,
        "controla_vencimiento": producto.controla_vencimiento,
        "activo": producto.activo,
        "proveedor_principal_id": producto.proveedor_principal_id,
    }


@productos_bp.get("")
@login_required
@requerir_permiso("productos.ver")
def listar():
    valor_inactivos = (
        request.args.get("incluir_inactivos", "")
        .strip()
        .lower()
    )

    incluir_inactivos = valor_inactivos in {
        "1",
        "true",
        "si",
        "yes",
    }

    productos = ServicioProductos(current_user).listar(
        busqueda=request.args.get("buscar"),
        incluir_inactivos=incluir_inactivos,
    )

    return jsonify(
        {
            "productos": [
                _serializar(producto)
                for producto in productos
            ]
        }
    )


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

@productos_bp.post("/<int:producto_id>/desactivar")
@login_required
@requerir_permiso("productos.eliminar")
def desactivar(producto_id):
    producto = ServicioProductos(current_user).desactivar(
        producto_id
    )

    return jsonify(_serializar(producto))

@productos_bp.post("/<int:producto_id>/reactivar")
@login_required
@requerir_permiso("productos.eliminar")
def reactivar(producto_id):
    producto = ServicioProductos(current_user).reactivar(
        producto_id
    )

    return jsonify(_serializar(producto))


@productos_bp.delete("/<int:producto_id>")
@login_required
@requerir_permiso("productos.eliminar")
def eliminar(producto_id):
    try:
        ServicioProductos(current_user).eliminar_logicamente(producto_id)
        return "", 204
    except ErrorProducto as exc:
        return jsonify({"codigo": "producto_con_historial", "mensaje": str(exc)}), 409

