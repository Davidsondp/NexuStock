"""Panel visual de usuarios empresariales."""

from flask import Blueprint, g, render_template
from flask_login import current_user, login_required

from ...permisos import evaluar_permiso, requerir_permiso
from ...services.contexto import requerir_contexto
from ...services.perfiles_empresa import capacidades_empresa
from ...services.unidades_medida import unidades_sugeridas


panel_bp = Blueprint(
    "panel",
    __name__,
    url_prefix="/panel",
)


@panel_bp.get("")
@login_required
@requerir_permiso("dashboard.ver")
@requerir_contexto
def inicio():
    return render_template(
        "panel/inicio.html",
        empresa=current_user.empresa,
        contexto=g.contexto_operacion,
    )

@panel_bp.get("/productos")
@login_required
@requerir_permiso("productos.ver")
@requerir_contexto
def productos():
    empresa_id = current_user.empresa_id

    permisos = {
        "crear": evaluar_permiso(
            current_user,
            "productos.crear",
            empresa_id=empresa_id,
        ).permitido,
        "editar": evaluar_permiso(
            current_user,
            "productos.editar",
            empresa_id=empresa_id,
        ).permitido,
        "eliminar": evaluar_permiso(
            current_user,
            "productos.eliminar",
            empresa_id=empresa_id,
        ).permitido,
    }

    capacidades = capacidades_empresa(
        current_user.empresa
    )

    unidades = unidades_sugeridas(
        capacidades["rubro"]
    )

    return render_template(
        "panel/productos.html",
        empresa=current_user.empresa,
        contexto=g.contexto_operacion,
        permisos=permisos,
        capacidades=capacidades,
        unidades_sugeridas=unidades,
    )

@panel_bp.get("/proveedores")
@login_required
@requerir_permiso("proveedores.ver")
@requerir_contexto
def proveedores():
    empresa_id = current_user.empresa_id

    permisos = {
        "crear": evaluar_permiso(
            current_user,
            "proveedores.crear",
            empresa_id=empresa_id,
        ).permitido,
        "editar": evaluar_permiso(
            current_user,
            "proveedores.editar",
            empresa_id=empresa_id,
        ).permitido,
        "eliminar": evaluar_permiso(
            current_user,
            "proveedores.eliminar",
            empresa_id=empresa_id,
        ).permitido,
    }

    return render_template(
        "panel/proveedores.html",
        empresa=current_user.empresa,
        contexto=g.contexto_operacion,
        permisos=permisos,
    )

@panel_bp.get("/compras")
@login_required
@requerir_permiso("compras.ver")
@requerir_contexto
def compras():
    empresa_id = current_user.empresa_id

    permisos = {
        "crear": evaluar_permiso(
            current_user,
            "compras.crear",
            empresa_id=empresa_id,
        ).permitido,
        "editar": evaluar_permiso(
            current_user,
            "compras.editar",
            empresa_id=empresa_id,
        ).permitido,
        "enviar": evaluar_permiso(
            current_user,
            "compras.enviar",
            empresa_id=empresa_id,
        ).permitido,
        "recibir": evaluar_permiso(
            current_user,
            "compras.recibir",
            empresa_id=empresa_id,
        ).permitido,
        "cancelar": evaluar_permiso(
            current_user,
            "compras.cancelar",
            empresa_id=empresa_id,
        ).permitido,
    }

    return render_template(
        "panel/compras.html",
        empresa=current_user.empresa,
        contexto=g.contexto_operacion,
        permisos=permisos,
    )

@panel_bp.get("/ventas")
@login_required
@requerir_permiso("ventas.ver")
@requerir_contexto
def ventas():
    empresa_id = current_user.empresa_id

    permisos = {
        "crear": evaluar_permiso(
            current_user,
            "ventas.crear",
            empresa_id=empresa_id,
        ).permitido,
        "reservar": evaluar_permiso(
            current_user,
            "ventas.reservar",
            empresa_id=empresa_id,
        ).permitido,
        "confirmar": evaluar_permiso(
            current_user,
            "ventas.confirmar",
            empresa_id=empresa_id,
        ).permitido,
        "cancelar": evaluar_permiso(
            current_user,
            "ventas.cancelar",
            empresa_id=empresa_id,
        ).permitido,
    }

    return render_template(
        "panel/ventas.html",
        empresa=current_user.empresa,
        contexto=g.contexto_operacion,
        permisos=permisos,
    )

@panel_bp.get("/clientes")
@login_required
@requerir_permiso("clientes.ver")
@requerir_contexto
def clientes():
    empresa_id = current_user.empresa_id

    permisos = {
        "crear": evaluar_permiso(
            current_user,
            "clientes.crear",
            empresa_id=empresa_id,
        ).permitido,
        "editar": evaluar_permiso(
            current_user,
            "clientes.editar",
            empresa_id=empresa_id,
        ).permitido,
        "eliminar": evaluar_permiso(
            current_user,
            "clientes.eliminar",
            empresa_id=empresa_id,
        ).permitido,
    }

    return render_template(
        "panel/clientes.html",
        empresa=current_user.empresa,
        contexto=g.contexto_operacion,
        permisos=permisos,
    )

@panel_bp.get("/inventario")
@login_required
@requerir_permiso("stock.ver")
@requerir_contexto
def inventario():
    empresa_id = current_user.empresa_id

    permisos = {
        "entrada": evaluar_permiso(
            current_user,
            "stock.entrada",
            empresa_id=empresa_id,
        ).permitido,
        "salida": evaluar_permiso(
            current_user,
            "stock.salida",
            empresa_id=empresa_id,
        ).permitido,
        "ajuste": evaluar_permiso(
            current_user,
            "stock.ajuste",
            empresa_id=empresa_id,
        ).permitido,
        "devolucion": evaluar_permiso(
            current_user,
            "stock.devolucion",
            empresa_id=empresa_id,
        ).permitido,
    }

    capacidades = capacidades_empresa(
        current_user.empresa
    )

    return render_template(
        "panel/inventario.html",
        empresa=current_user.empresa,
        contexto=g.contexto_operacion,
        permisos=permisos,
        capacidades=capacidades,
    )


@panel_bp.get("/alertas")
@login_required
@requerir_permiso("alertas.ver")
@requerir_contexto
def alertas():
    empresa_id = current_user.empresa_id

    permisos = {
        "gestionar": evaluar_permiso(
            current_user,
            "alertas.gestionar",
            empresa_id=empresa_id,
        ).permitido,
    }

    return render_template(
        "panel/alertas.html",
        empresa=current_user.empresa,
        contexto=g.contexto_operacion,
        permisos=permisos,
    )
