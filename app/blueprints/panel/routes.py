"""Panel visual de usuarios empresariales."""

from flask import Blueprint, g, render_template
from flask_login import current_user, login_required

from ...permisos import requerir_permiso
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