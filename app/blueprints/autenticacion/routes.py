from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_user, logout_user

from ...models import Usuario, db
from ...services.auditoria import registrar_auditoria
from ...services.registro import ErrorRegistro, registrar_empresa
from ...services.restablecimiento import (
    buscar_usuario_por_token,
    restablecer_password,
    solicitar_restablecimiento,
)
from .forms import (
    LoginForm,
    RegistroForm,
    RestablecerPasswordForm,
    SolicitarRestablecimientoForm,
)

autenticacion_bp = Blueprint(
    "autenticacion",
    __name__,
    url_prefix="/autenticacion",
)


def _destino_seguro(destino: str | None) -> str | None:
    if destino and destino.startswith("/") and not destino.startswith("//"):
        return destino
    return None


def _destino_usuario(usuario: Usuario) -> str:
    """Obtiene el destino inicial según el ámbito del usuario."""

    if usuario.rol == "super_admin" and usuario.empresa_id is None:
        return url_for("panel_superadministracion.inicio")

    return url_for("estado.estado")


@autenticacion_bp.route("/registro", methods=["GET", "POST"])
def registro():
    if current_user.is_authenticated:
        return redirect(_destino_usuario(current_user))

    formulario = RegistroForm()

    if formulario.validate_on_submit():
        try:
            usuario = registrar_empresa(
                empresa_nombre=formulario.empresa_nombre.data,
                identificacion_fiscal=formulario.identificacion_fiscal.data,
                nombre=formulario.nombre.data,
                apellido=formulario.apellido.data,
                email=formulario.email.data,
                password=formulario.password.data,
            )

            login_user(usuario)
            flash("Tu empresa fue creada correctamente.", "exito")

            return redirect(_destino_usuario(usuario))

        except ErrorRegistro as excepcion:
            flash(str(excepcion), "peligro")

    return render_template(
        "autenticacion/registro.html",
        form=formulario,
    )


@autenticacion_bp.route("/ingresar", methods=["GET", "POST"])
def ingresar():
    if current_user.is_authenticated:
        return redirect(_destino_usuario(current_user))

    formulario = LoginForm()

    if formulario.validate_on_submit():
        email = formulario.email.data.strip().lower()

        usuario = db.session.scalar(
            db.select(Usuario).where(Usuario.email == email)
        )

        if usuario and usuario.esta_bloqueado():
            flash(
                "Cuenta temporalmente bloqueada. Intenta más tarde.",
                "peligro",
            )

        elif not usuario or not usuario.check_password(
            formulario.password.data
        ):
            if usuario:
                usuario.registrar_intento_fallido()
                db.session.commit()

            flash("Credenciales inválidas.", "peligro")

        elif not usuario.is_active or (
            usuario.empresa and not usuario.empresa.esta_activa()
        ):
            flash("La cuenta no está habilitada.", "peligro")

        else:
            usuario.registrar_acceso()

            registrar_auditoria(
                accion="usuario.ingreso",
                modulo="autenticacion",
                usuario_id=usuario.id,
                empresa_id=usuario.empresa_id,
                entidad_tipo="Usuario",
                entidad_id=usuario.id,
            )

            db.session.commit()

            login_user(
                usuario,
                remember=formulario.recordar.data,
            )

            destino_solicitado = _destino_seguro(
                request.args.get("siguiente")
            )

            # Un Super Admin siempre entra en su panel global.
            # Nunca se redirige hacia módulos empresariales.
            if usuario.rol == "super_admin":
                destino_solicitado = None

            return redirect(
                destino_solicitado or _destino_usuario(usuario)
            )

    return render_template(
        "autenticacion/ingresar.html",
        form=formulario,
    )


@autenticacion_bp.post("/salir")
def salir():
    if current_user.is_authenticated:
        registrar_auditoria(
            accion="usuario.salida",
            modulo="autenticacion",
            usuario_id=current_user.id,
            empresa_id=current_user.empresa_id,
            entidad_tipo="Usuario",
            entidad_id=current_user.id,
        )

        db.session.commit()
        logout_user()

    return redirect(url_for("autenticacion.ingresar"))


@autenticacion_bp.route(
    "/olvide-password",
    methods=["GET", "POST"],
)
def olvide_password():
    if current_user.is_authenticated:
        return redirect(_destino_usuario(current_user))

    formulario = SolicitarRestablecimientoForm()

    if formulario.validate_on_submit():
        solicitar_restablecimiento(formulario.email.data)

        flash(
            "Si el correo está registrado, recibirás instrucciones "
            "para restablecer tu contraseña.",
            "exito",
        )

        return redirect(url_for("autenticacion.ingresar"))

    return render_template(
        "autenticacion/olvide_password.html",
        form=formulario,
    )


@autenticacion_bp.route(
    "/restablecer-password/<token>",
    methods=["GET", "POST"],
)
def restablecer_password_route(token: str):
    if current_user.is_authenticated:
        return redirect(_destino_usuario(current_user))

    usuario = buscar_usuario_por_token(token)

    if not usuario:
        flash(
            "El enlace es inválido o ha expirado.",
            "peligro",
        )
        return redirect(url_for("autenticacion.olvide_password"))

    formulario = RestablecerPasswordForm()

    if formulario.validate_on_submit():
        actualizado = restablecer_password(
            usuario,
            token,
            formulario.password.data,
        )

        if actualizado:
            flash(
                "Tu contraseña fue actualizada. Ya puedes ingresar.",
                "exito",
            )
            return redirect(url_for("autenticacion.ingresar"))

        flash(
            "El enlace es inválido o ha expirado.",
            "peligro",
        )
        return redirect(url_for("autenticacion.olvide_password"))

    return render_template(
        "autenticacion/restablecer_password.html",
        form=formulario,
    )