from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ...permisos import requerir_permiso
from ...services.usuarios import ErrorUsuario, ServicioUsuarios

usuarios_bp = Blueprint("usuarios", __name__, url_prefix="/api/usuarios")


def _serializar(usuario):
    return {"id": usuario.id, "nombre": usuario.nombre, "apellido": usuario.apellido,
            "email": usuario.email, "rol": usuario.rol, "activo": usuario.activo,
            "permisos_especiales": usuario.permisos_especiales,
            "sucursales": [{"id": a.sucursal_id, "es_principal": a.es_principal}
                            for a in usuario.asignaciones]}


def _error(exc):
    return jsonify({"codigo": getattr(exc, "codigo", "usuario_invalido"), "mensaje": str(exc)}), 400


@usuarios_bp.get("")
@login_required
@requerir_permiso("usuarios.ver")
def listar():
    incluir = request.args.get("incluir_inactivos", "false").lower() == "true"
    return jsonify({"usuarios": [_serializar(u) for u in ServicioUsuarios(current_user).listar(
        incluir_inactivos=incluir)]})


@usuarios_bp.get("/<int:usuario_id>")
@login_required
@requerir_permiso("usuarios.ver")
def obtener(usuario_id):
    return jsonify(_serializar(ServicioUsuarios(current_user).obtener(usuario_id)))


@usuarios_bp.post("")
@login_required
@requerir_permiso("usuarios.crear")
def crear():
    try:
        datos = request.get_json(silent=True) or {}
        permitidos = {k: datos[k] for k in ("nombre", "apellido", "email", "password",
            "rol", "sucursales_ids", "permisos_especiales") if k in datos}
        return jsonify(_serializar(ServicioUsuarios(current_user).crear(**permitidos))), 201
    except (ErrorUsuario, TypeError, ValueError) as exc: return _error(exc)


@usuarios_bp.patch("/<int:usuario_id>")
@login_required
@requerir_permiso("usuarios.editar")
def editar(usuario_id):
    try:
        datos = request.get_json(silent=True) or {}
        permitidos = {k: datos[k] for k in ("nombre", "apellido", "email", "rol",
            "sucursales_ids", "permisos_especiales") if k in datos}
        return jsonify(_serializar(ServicioUsuarios(current_user).editar(usuario_id, **permitidos)))
    except (ErrorUsuario, TypeError, ValueError) as exc: return _error(exc)


@usuarios_bp.post("/<int:usuario_id>/cambiar-password")
@login_required
@requerir_permiso("usuarios.editar")
def cambiar_password(usuario_id):
    try:
        usuario = ServicioUsuarios(current_user).cambiar_password(
            usuario_id, (request.get_json(silent=True) or {}).get("password"))
        return jsonify(_serializar(usuario))
    except (ErrorUsuario, ValueError) as exc: return _error(exc)


@usuarios_bp.post("/<int:usuario_id>/desactivar")
@login_required
@requerir_permiso("usuarios.desactivar")
def desactivar(usuario_id):
    try: return jsonify(_serializar(ServicioUsuarios(current_user).desactivar(usuario_id)))
    except ErrorUsuario as exc: return _error(exc)


@usuarios_bp.post("/<int:usuario_id>/reactivar")
@login_required
@requerir_permiso("usuarios.editar")
def reactivar(usuario_id):
    try: return jsonify(_serializar(ServicioUsuarios(current_user).reactivar(usuario_id)))
    except ErrorUsuario as exc: return _error(exc)


@usuarios_bp.post("/<int:usuario_id>/revocar-sesiones")
@login_required
@requerir_permiso("usuarios.editar")
def revocar_sesiones(usuario_id):
    return jsonify(_serializar(ServicioUsuarios(current_user).revocar_sesiones(usuario_id)))