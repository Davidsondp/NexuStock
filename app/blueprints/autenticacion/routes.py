from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from ...models import Usuario, db
from ...services.auditoria import registrar_auditoria
from ...services.registro import ErrorRegistro, registrar_empresa
from ...services.restablecimiento import (buscar_usuario_por_token, restablecer_password,
                                          solicitar_restablecimiento)
from .forms import (LoginForm, RegistroForm, RestablecerPasswordForm,
                    SolicitarRestablecimientoForm)

autenticacion_bp = Blueprint("autenticacion", __name__, url_prefix="/autenticacion")


def _destino_seguro(destino: str | None) -> str | None:
    return destino if destino and destino.startswith("/") and not destino.startswith("//") else None


@autenticacion_bp.route("/registro", methods=["GET", "POST"])
def registro():
    if current_user.is_authenticated:
        return redirect(url_for("estado.estado"))
    form = RegistroForm()
    if form.validate_on_submit():
        try:
            usuario = registrar_empresa(
                empresa_nombre=form.empresa_nombre.data,
                identificacion_fiscal=form.identificacion_fiscal.data,
                nombre=form.nombre.data, apellido=form.apellido.data,
                email=form.email.data, password=form.password.data,
            )
            login_user(usuario)
            flash("Tu empresa fue creada correctamente.", "exito")
            return redirect(url_for("estado.estado"))
        except ErrorRegistro as exc:
            flash(str(exc), "peligro")
    return render_template("autenticacion/registro.html", form=form)


@autenticacion_bp.route("/ingresar", methods=["GET", "POST"])
def ingresar():
    if current_user.is_authenticated:
        return redirect(url_for("estado.estado"))
    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        usuario = db.session.scalar(db.select(Usuario).where(Usuario.email == email))
        if usuario and usuario.esta_bloqueado():
            flash("Cuenta temporalmente bloqueada. Intenta más tarde.", "peligro")
        elif not usuario or not usuario.check_password(form.password.data):
            if usuario:
                usuario.registrar_intento_fallido()
                db.session.commit()
            flash("Credenciales inválidas.", "peligro")
        elif not usuario.is_active or (usuario.empresa and not usuario.empresa.esta_activa()):
            flash("La cuenta no está habilitada.", "peligro")
        else:
            usuario.registrar_acceso()
            registrar_auditoria(accion="usuario.ingreso", modulo="autenticacion",
                                usuario_id=usuario.id, empresa_id=usuario.empresa_id,
                                entidad_tipo="Usuario", entidad_id=usuario.id)
            db.session.commit()
            login_user(usuario, remember=form.recordar.data)
            return redirect(_destino_seguro(request.args.get("siguiente")) or url_for("estado.estado"))
    return render_template("autenticacion/ingresar.html", form=form)


@autenticacion_bp.post("/salir")
def salir():
    if current_user.is_authenticated:
        registrar_auditoria(accion="usuario.salida", modulo="autenticacion",
                            usuario_id=current_user.id, empresa_id=current_user.empresa_id,
                            entidad_tipo="Usuario", entidad_id=current_user.id)
        db.session.commit()
        logout_user()
    return redirect(url_for("autenticacion.ingresar"))


@autenticacion_bp.route("/olvide-password", methods=["GET", "POST"])
def olvide_password():
    if current_user.is_authenticated:
        return redirect(url_for("estado.estado"))
    formulario = SolicitarRestablecimientoForm()
    if formulario.validate_on_submit():
        solicitar_restablecimiento(formulario.email.data)
        flash("Si el correo está registrado, recibirás instrucciones para restablecer tu contraseña.", "exito")
        return redirect(url_for("autenticacion.ingresar"))
    return render_template("autenticacion/olvide_password.html", form=formulario)


@autenticacion_bp.route("/restablecer-password/<token>", methods=["GET", "POST"])
def restablecer_password_route(token: str):
    if current_user.is_authenticated:
        return redirect(url_for("estado.estado"))
    usuario = buscar_usuario_por_token(token)
    if not usuario:
        flash("El enlace es inválido o ha expirado.", "peligro")
        return redirect(url_for("autenticacion.olvide_password"))
    formulario = RestablecerPasswordForm()
    if formulario.validate_on_submit():
        if restablecer_password(usuario, token, formulario.password.data):
            flash("Tu contraseña fue actualizada. Ya puedes ingresar.", "exito")
            return redirect(url_for("autenticacion.ingresar"))
        flash("El enlace es inválido o ha expirado.", "peligro")
        return redirect(url_for("autenticacion.olvide_password"))
    return render_template("autenticacion/restablecer_password.html", form=formulario)
