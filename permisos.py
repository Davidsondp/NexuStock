"""
NexuStock
Sistema central de permisos y límites por plan.
"""

from flask import flash

from models import (
    Empresa,
    Producto,
    Usuario,
    Movimiento
)


# ==================================================
# OBTENER PLAN
# ==================================================

def obtener_plan(empresa):

    if not empresa:
        return None

    return empresa.plan


# ==================================================
# FUNCIONES
# ==================================================

def tiene_funcion(
    empresa,
    funcion
):

    plan = obtener_plan(empresa)

    if not plan:
        return False

    return plan.tiene_funcion(funcion)


# ==================================================
# PRODUCTOS
# ==================================================

def puede_crear_producto(empresa):

    plan = obtener_plan(empresa)

    if not plan:
        return False

    if plan.limite_productos is None:
        return True

    total = Producto.query.filter_by(
        empresa_id=empresa.id
    ).count()

    return total < plan.limite_productos


# ==================================================
# USUARIOS
# ==================================================

def puede_crear_usuario(empresa):

    plan = obtener_plan(empresa)

    if not plan:
        return False

    if plan.limite_usuarios is None:
        return True

    total = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).count()

    return total < plan.limite_usuarios


# ==================================================
# MOVIMIENTOS
# ==================================================

def puede_registrar_movimiento(empresa):

    plan = obtener_plan(empresa)

    if not plan:
        return False

    if plan.limite_movimientos is None:
        return True

    total = Movimiento.query.filter_by(
        empresa_id=empresa.id
    ).count()

    return total < plan.limite_movimientos


# ==================================================
# SUCURSALES
# ==================================================

def puede_crear_sucursal(empresa):

    plan = obtener_plan(empresa)

    if not plan:
        return False

    if plan.limite_sucursales is None:
        return True

    return empresa.cantidad_sucursales < plan.limite_sucursales