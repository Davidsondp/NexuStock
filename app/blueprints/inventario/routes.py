from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ...models import (
    Inventario,
    Movimiento,
    Producto,
    db,
)
from ...permisos import requerir_permiso
from ...services.contexto import (
    obtener_contexto,
    requerir_contexto,
)
from ...services.inventario import (
    ErrorInventario,
    ServicioInventario,
)


inventario_bp = Blueprint(
    "inventario",
    __name__,
    url_prefix="/api/inventario",
)


def _serializar_resultado(resultado, tipo):
    return {
        "tipo": tipo,
        "inventario_id": resultado.inventario_id,
        "movimiento_id": resultado.movimiento_id,
        "stock_anterior": format(
            resultado.stock_anterior,
            ".3f",
        ),
        "stock_nuevo": format(
            resultado.stock_nuevo,
            ".3f",
        ),
        "costo_promedio": format(
            resultado.costo_promedio,
            ".4f",
        ),
    }


def _error(exc, codigo=None):
    return jsonify(
        {
            "codigo": (
                codigo
                or getattr(
                    exc,
                    "codigo",
                    "error_inventario",
                )
            ),
            "mensaje": str(exc),
        }
    ), 400



def _serializar_stock(
    inventario,
    producto,
    bodega,
):
    cantidad = inventario.cantidad
    reservada = inventario.cantidad_reservada
    disponible = inventario.cantidad_disponible
    costo_promedio = inventario.costo_promedio
    valor = cantidad * costo_promedio

    return {
        "inventario_id": inventario.id,
        "producto_id": producto.id,
        "producto_codigo": producto.codigo,
        "producto_nombre": producto.nombre,
        "bodega_id": bodega.id,
        "bodega_nombre": bodega.nombre,
        "cantidad": format(cantidad, ".3f"),
        "reservada": format(reservada, ".3f"),
        "disponible": format(
            disponible,
            ".3f",
        ),
        "costo_promedio": format(
            costo_promedio,
            ".4f",
        ),
        "valor": format(valor, ".2f"),
    }


def _serializar_movimiento(
    movimiento,
    producto,
):
    return {
        "id": movimiento.id,
        "producto_id": producto.id,
        "producto_codigo": producto.codigo,
        "producto_nombre": producto.nombre,
        "bodega_id": movimiento.bodega_id,
        "tipo": movimiento.tipo,
        "subtipo": movimiento.subtipo,
        "cantidad": format(
            movimiento.cantidad,
            ".3f",
        ),
        "stock_anterior": format(
            movimiento.stock_anterior,
            ".3f",
        ),
        "stock_nuevo": format(
            movimiento.stock_nuevo,
            ".3f",
        ),
        "costo_unitario": (
            format(
                movimiento.costo_unitario,
                ".4f",
            )
            if movimiento.costo_unitario
            is not None
            else None
        ),
        "precio_unitario": (
            format(
                movimiento.precio_unitario,
                ".2f",
            )
            if movimiento.precio_unitario
            is not None
            else None
        ),
        "referencia_tipo":
            movimiento.referencia_tipo,
        "referencia_id":
            movimiento.referencia_id,
        "motivo": movimiento.motivo,
        "fecha": movimiento.fecha.isoformat(),
    }


def _contexto_actual():
    contexto = obtener_contexto(
        current_user,
        crear_automaticamente=False,
    )

    if not contexto:
        raise ValueError(
            "No existe un contexto operativo v?lido"
        )

    return contexto


@inventario_bp.get("/stock")
@login_required
@requerir_permiso("stock.ver")
@requerir_contexto
def listar_stock():
    try:
        contexto = _contexto_actual()

        filas = db.session.execute(
            db.select(
                Inventario,
                Producto,
            )
            .join(
                Producto,
                db.and_(
                    Producto.id
                    == Inventario.producto_id,
                    Producto.empresa_id
                    == Inventario.empresa_id,
                ),
            )
            .where(
                Inventario.empresa_id
                == current_user.empresa_id,
                Inventario.bodega_id
                == contexto.bodega.id,
                Producto.eliminado.is_(False),
            )
            .order_by(
                Producto.nombre,
                Producto.codigo,
            )
        ).all()

        return jsonify(
            {
                "bodega_id": contexto.bodega.id,
                "bodega_nombre":
                    contexto.bodega.nombre,
                "stock": [
                    _serializar_stock(
                        inventario,
                        producto,
                        contexto.bodega,
                    )
                    for inventario, producto
                    in filas
                ],
            }
        )
    except ValueError as exc:
        return _error(
            exc,
            "contexto_invalido",
        )


@inventario_bp.get("/movimientos")
@login_required
@requerir_permiso("movimientos.ver")
@requerir_contexto
def listar_movimientos():
    try:
        contexto = _contexto_actual()

        try:
            limite = int(
                request.args.get("limite", 100)
            )
        except (TypeError, ValueError):
            limite = 100

        limite = min(
            max(limite, 1),
            500,
        )

        filas = db.session.execute(
            db.select(
                Movimiento,
                Producto,
            )
            .join(
                Producto,
                db.and_(
                    Producto.id
                    == Movimiento.producto_id,
                    Producto.empresa_id
                    == Movimiento.empresa_id,
                ),
            )
            .where(
                Movimiento.empresa_id
                == current_user.empresa_id,
                Movimiento.bodega_id
                == contexto.bodega.id,
                Producto.eliminado.is_(False),
            )
            .order_by(
                Movimiento.fecha.desc(),
                Movimiento.id.desc(),
            )
            .limit(limite)
        ).all()

        return jsonify(
            {
                "bodega_id": contexto.bodega.id,
                "bodega_nombre":
                    contexto.bodega.nombre,
                "movimientos": [
                    _serializar_movimiento(
                        movimiento,
                        producto,
                    )
                    for movimiento, producto
                    in filas
                ],
            }
        )
    except ValueError as exc:
        return _error(
            exc,
            "contexto_invalido",
        )


@inventario_bp.post("/movimientos")
@login_required
@requerir_permiso("stock.ver")
@requerir_contexto
def registrar_movimiento():
    datos = request.get_json(silent=True) or {}

    tipo = (
        datos.get("tipo")
        or ""
    ).strip().lower()

    operaciones = {
        "entrada",
        "salida",
        "ajuste",
        "devolucion",
    }

    if tipo not in operaciones:
        return _error(
            ValueError(
                "El tipo de movimiento no es v?lido"
            ),
            "movimiento_invalido",
        )

    contexto = obtener_contexto(
        current_user,
        crear_automaticamente=False,
    )

    if not contexto:
        return _error(
            ValueError(
                "No existe un contexto operativo v?lido"
            ),
            "contexto_invalido",
        )

    servicio = ServicioInventario(
        current_user,
        contexto,
    )

    try:
        producto_id = int(datos["producto_id"])
        motivo = datos.get("motivo")

        if tipo == "entrada":
            resultado = servicio.entrada(
                producto_id=producto_id,
                cantidad=datos.get("cantidad"),
                costo_unitario=datos.get(
                    "costo_unitario"
                ),
                motivo=motivo,
            )
        elif tipo == "salida":
            resultado = servicio.salida(
                producto_id=producto_id,
                cantidad=datos.get("cantidad"),
                precio_unitario=datos.get(
                    "precio_unitario"
                ),
                motivo=motivo,
            )
        elif tipo == "devolucion":
            resultado = servicio.devolucion(
                producto_id=producto_id,
                cantidad=datos.get("cantidad"),
                costo_unitario=datos.get(
                    "costo_unitario"
                ),
                motivo=motivo,
            )
        else:
            resultado = servicio.ajuste(
                producto_id=producto_id,
                stock_final=datos.get(
                    "stock_final"
                ),
                motivo=motivo,
            )

        return jsonify(
            _serializar_resultado(
                resultado,
                tipo,
            )
        ), 201
    except ErrorInventario as exc:
        return _error(exc)
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        return _error(
            exc,
            "movimiento_invalido",
        )
