import os

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    session,
    url_for,
)
from flask_login import current_user

from config import CONFIGURACIONES
from .extensions import correo, csrf, login_manager, migrate
from .models import PlanSaaS, Usuario, db


def crear_aplicacion(nombre_configuracion: str | None = None) -> Flask:
    entorno = nombre_configuracion or os.getenv("FLASK_ENV", "desarrollo")
    clase_configuracion = CONFIGURACIONES.get(entorno, CONFIGURACIONES["desarrollo"])
    if entorno == "produccion":
        clase_configuracion.validar()

    app = Flask(__name__)
    app.config.from_object(clase_configuracion)
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    login_manager.init_app(app)
    correo.init_app(app)
    from .seguridad import registrar_seguridad

    registrar_seguridad(app)
    login_manager.login_view = "autenticacion.ingresar"

    from .blueprints.estado.routes import estado_bp
    from .blueprints.autenticacion.routes import autenticacion_bp
    from .blueprints.contexto.routes import contexto_bp
    from .blueprints.productos.routes import productos_bp
    from .blueprints.inventario.routes import inventario_bp
    from .blueprints.proveedores.routes import proveedores_bp
    from .blueprints.ubicaciones.routes import ubicaciones_bp
    from .blueprints.compras.routes import compras_bp
    from .blueprints.ventas.routes import ventas_bp
    from .blueprints.transferencias.routes import transferencias_bp
    from .blueprints.seriales.routes import seriales_bp
    from .blueprints.auditoria.routes import auditoria_bp
    from .blueprints.claves_api.routes import claves_api_bp
    from .blueprints.api_publica.routes import api_publica_bp
    from .blueprints.notificaciones.routes import notificaciones_bp
    from .blueprints.reportes_personalizados.routes import reportes_personalizados_bp
    from .blueprints.asistente_ia.routes import asistente_ia_bp
    from .blueprints.importaciones.routes import importaciones_bp
    from .blueprints.ayuda.routes import ayuda_bp
    from .blueprints.clientes.routes import clientes_bp
    from .blueprints.alertas.routes import alertas_bp
    from .blueprints.reportes.routes import reportes_bp
    from .blueprints.usuarios.routes import usuarios_bp
    from .blueprints.configuracion.routes import configuracion_bp
    from .blueprints.suscripciones.routes import suscripciones_bp, webhooks_pago_bp
    from .blueprints.superadministracion.routes import superadministracion_bp
    from .blueprints.superadministracion.panel import panel_superadministracion_bp
    from .blueprints.panel.routes import panel_bp

    app.register_blueprint(estado_bp)
    app.register_blueprint(autenticacion_bp)
    app.register_blueprint(contexto_bp)
    app.register_blueprint(productos_bp)
    app.register_blueprint(inventario_bp)
    app.register_blueprint(proveedores_bp)
    app.register_blueprint(ubicaciones_bp)
    app.register_blueprint(compras_bp)
    app.register_blueprint(ventas_bp)
    app.register_blueprint(transferencias_bp)
    app.register_blueprint(seriales_bp)
    app.register_blueprint(auditoria_bp)
    app.register_blueprint(claves_api_bp)
    app.register_blueprint(api_publica_bp)
    app.register_blueprint(notificaciones_bp)
    app.register_blueprint(reportes_personalizados_bp)
    app.register_blueprint(asistente_ia_bp)
    app.register_blueprint(importaciones_bp)
    app.register_blueprint(ayuda_bp)
    app.register_blueprint(clientes_bp)
    app.register_blueprint(alertas_bp)
    app.register_blueprint(reportes_bp)
    app.register_blueprint(usuarios_bp)
    app.register_blueprint(configuracion_bp)
    app.register_blueprint(suscripciones_bp)
    app.register_blueprint(webhooks_pago_bp)
    app.register_blueprint(superadministracion_bp)
    app.register_blueprint(panel_superadministracion_bp)
    app.register_blueprint(panel_bp)

    def contexto_portada():
        planes = list(
            db.session.scalars(
                db.select(PlanSaaS)
                .where(PlanSaaS.activo.is_(True), PlanSaaS.codigo != "prueba")
                .order_by(PlanSaaS.orden, PlanSaaS.id)
            )
        )
        return {
            "planes_publicos": planes,
            "formatear_clp": lambda valor: "$" + f"{int(valor):,}".replace(",", "."),
        }

    # Compatibilidad con las URLs históricas publicadas e indexadas. Se enlaza
    # directamente la misma vista para conservar también formularios POST.
    app.add_url_rule(
        "/login",
        endpoint="login_compatibilidad",
        view_func=app.view_functions["autenticacion.ingresar"],
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/registro",
        endpoint="registro_compatibilidad",
        view_func=app.view_functions["autenticacion.registro"],
        methods=["GET", "POST"],
    )

    @app.get("/")
    def inicio_publico():
        if not current_user.is_authenticated:
            return render_template("planes_publicos.html", **contexto_portada())

        if current_user.rol == "super_admin" and current_user.empresa_id is None:
            return redirect(url_for(("panel_superadministracion" ".inicio")))

        return redirect(url_for("panel.inicio"))

    @app.get("/planes")
    def planes_publicos():
        return render_template("planes_publicos.html", **contexto_portada())

    from .commands import registrar_comandos

    registrar_comandos(app)

    @app.before_request
    def revalidar_contexto_guardado():
        from .services.contexto import CLAVE_BODEGA, CLAVE_SUCURSAL, obtener_contexto

        if (
            current_user.is_authenticated
            and current_user.rol != "super_admin"
            and (CLAVE_SUCURSAL in session or CLAVE_BODEGA in session)
        ):
            obtener_contexto(current_user, crear_automaticamente=False)

    @app.errorhandler(403)
    def acceso_denegado(excepcion):
        return jsonify({"codigo": "acceso_denegado", "mensaje": excepcion.description}), 403

    @app.errorhandler(PermissionError)
    def operacion_fuera_de_ambito(excepcion):
        return jsonify({"codigo": "acceso_denegado", "mensaje": str(excepcion)}), 403

    return app


@login_manager.user_loader
def cargar_usuario(usuario_id: str):
    partes = usuario_id.split(":", 1)
    if len(partes) != 2 or not all(parte.isdigit() for parte in partes):
        return None
    usuario = db.session.get(Usuario, int(partes[0]))
    return usuario if usuario and usuario.version_sesion == int(partes[1]) else None
