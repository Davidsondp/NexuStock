"""Panel visual de usuarios empresariales."""

from flask import Blueprint, g, render_template
from flask_login import current_user, login_required

from ...permisos import evaluar_permiso, requerir_permiso
from ...services.contexto import requerir_contexto


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

    return render_template(
        "panel/productos.html",
        empresa=current_user.empresa,
        contexto=g.contexto_operacion,
        permisos=permisos,
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