# ==================================================
# NEXUSTOCK ERP SaaS
# APP CONFIGURATION
# PRODUCCIÓN READY
# ==================================================


# ==================================================
# IMPORTS
# ==================================================

import os
import math
import mercadopago
import logging
logger = logging.getLogger(__name__)
from datetime import datetime, timedelta, UTC
from sqlalchemy.orm import joinedload
from transbank.webpay.webpay_plus.transaction import Transaction
from transbank.common.options import WebpayOptions
from transbank.common.integration_type import IntegrationType
from transbank.common.integration_commerce_codes import IntegrationCommerceCodes
from transbank.common.integration_api_keys import IntegrationApiKeys

WEBPAY_COMMERCE_CODE = os.getenv("WEBPAY_COMMERCE_CODE")
WEBPAY_API_KEY = os.getenv("WEBPAY_API_KEY")

print("=" * 60)
print("WEBPAY CONFIG")
print("Commerce Code:", WEBPAY_COMMERCE_CODE)
print("API Key:", WEBPAY_API_KEY)
print("=" * 60)

webpay_transaction = Transaction(
    WebpayOptions(
        WEBPAY_COMMERCE_CODE,
        WEBPAY_API_KEY,
        IntegrationType.TEST
    )
)
from io import BytesIO
from functools import wraps
from dotenv import load_dotenv
from flask import (Flask,render_template,request,redirect,url_for,
    session,
    flash,
    send_file,
    jsonify)

from flask_wtf.csrf import (CSRFProtect,CSRFError)
from flask_mail import (Mail,Message)
from itsdangerous import (URLSafeTimedSerializer,BadSignature,
                          SignatureExpired)
from openpyxl import Workbook
from werkzeug.security import (generate_password_hash,check_password_hash)
from models import (
    db,
    Empresa,
    Usuario,
    Producto,
    ProductoSerial,
    Proveedor,
    OrdenCompra,
    OrdenCompraItem,
    Movimiento,
    Pago,
    AuditoriaPago,
    PlanSaaS,
    SolicitudCambioPlan,
    AlertaInventario,
    ConfiguracionEmpresa,
    Notificacion,
    Auditoria
)

from flask_migrate import Migrate
from flask_mail import Mail, Message


# ==================================================
# VARIABLES ENTORNO
# ==================================================

load_dotenv()

# ==================================================
# CREACIÓN APP
# ==================================================

app = Flask(__name__)

# ==================================================
# SEGURIDAD GENERAL
# ==================================================

app.config["MAX_CONTENT_LENGTH"] = (16 * 1024 * 1024)
app.secret_key = os.getenv("SECRET_KEY")
if not app.secret_key: raise RuntimeError("SECRET_KEY no configurada")

# ==================================================
# SESIONES SEGURAS
# ==================================================

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = (timedelta(hours=8))
if os.getenv("FLASK_ENV") == "production": app.config["SESSION_COOKIE_SECURE"] = True
else: app.config["SESSION_COOKIE_SECURE"] = False

# ==================================================
# CSRF
# ==================================================

csrf = CSRFProtect(app)
# ==================================================
# SERIALIZADOR TOKENS
# ==================================================

serializer = URLSafeTimedSerializer(app.secret_key)

# ==================================================
# BASE DE DATOS
# ==================================================

database_url = os.getenv("DATABASE_URL")
if database_url and database_url.startswith("postgres://"): database_url = database_url.replace("postgres://","postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = (database_url or "sqlite:///nexustock.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
db.init_app(app)

migrate = Migrate(app, db)
# ==================================================
# CORREO
# ==================================================

app.config["MAIL_SERVER"] = ("smtp.gmail.com")
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
app.config["MAIL_DEFAULT_SENDER"] = (os.getenv("MAIL_USERNAME"))
mail = Mail(app)



if not app.config["MAIL_USERNAME"]:print("⚠️ MAIL_USERNAME no configurado")

# ==================================================
# MERCADO PAGO
# ==================================================

MERCADOPAGO_PUBLIC_KEY = os.getenv(
    "MERCADOPAGO_PUBLIC_KEY"
)

MERCADOPAGO_ACCESS_TOKEN = os.getenv(
    "MERCADOPAGO_ACCESS_TOKEN"
)

sdk_mp = mercadopago.SDK(
    MERCADOPAGO_ACCESS_TOKEN
)

# ==================================================
# CREAR TABLAS SOLO DESARROLLO
# ==================================================

if os.getenv("FLASK_ENV") != "production":

    with app.app_context():

        db.create_all()

        if PlanSaaS.query.count() == 0:

            db.session.add_all([
            PlanSaaS(
            nombre="Prueba",
            descripcion="Prueba gratuita con funciones profesionales limitadas",
            precio_mensual=0,
            precio_anual=0,
            limite_productos=100,
            limite_usuarios=2,
            limite_movimientos=500,
            almacenamiento_mb=500,
            dias_prueba=30,
            limite_sucursales=1,

            tiene_reportes_avanzados=True,
            tiene_analisis_ventas=True,
            tiene_prediccion_agotamiento=True,
            tiene_recomendacion_compra=True,

            tiene_exportacion_avanzada=False,
            tiene_api=False,

            activo=True,
            orden=1
        ),


            PlanSaaS(
            nombre="Básico",
            descripcion="Para almacenes pequeños y negocios que reemplazan Excel o papel",
            precio_mensual=9990,
            precio_anual=99900,

            limite_productos=500,
            limite_usuarios=2,
            limite_movimientos=5000,
            almacenamiento_mb=2000,

            limite_sucursales=1,

            tiene_productos=True,
            tiene_movimientos=True,
            tiene_proveedores=True,
            tiene_dashboard=True,
            tiene_alertas_basicas=True,

            tiene_reportes_avanzados=False,
            tiene_exportacion_avanzada=False,

            activo=True,
            orden=2
        ),


            PlanSaaS(
            nombre="Profesional",
            descripcion="Para negocios con operación diaria y mayor control",
            precio_mensual=19990,
            precio_anual=199900,

            limite_productos=5000,
            limite_usuarios=10,
            limite_movimientos=50000,
            almacenamiento_mb=5000,

            limite_sucursales=3,

            tiene_productos=True,
            tiene_movimientos=True,
            tiene_proveedores=True,
            tiene_dashboard=True,
            tiene_alertas_basicas=True,

            tiene_roles=True,
            tiene_reportes_avanzados=True,
            tiene_exportacion_avanzada=True,

            tiene_analisis_ventas=True,
            tiene_productos_sin_movimiento=True,
            tiene_sobrestock=True,
            tiene_valor_inventario=True,

            tiene_prediccion_agotamiento=True,
            tiene_recomendacion_compra=True,

            tiene_auditoria=True,

            activo=True,
            orden=3
        ),


            PlanSaaS(
            nombre="Empresa",
            descripcion="Control completo e inteligencia avanzada",
            precio_mensual=49990,
            precio_anual=499900,

            limite_productos=None,
            limite_usuarios=None,
            limite_movimientos=None,

            almacenamiento_mb=20000,
            limite_sucursales=None,

            tiene_productos=True,
            tiene_movimientos=True,
            tiene_proveedores=True,
            tiene_dashboard=True,

            tiene_roles=True,
            tiene_reportes_avanzados=True,
            tiene_exportacion_avanzada=True,

            tiene_analisis_ventas=True,
            tiene_productos_sin_movimiento=True,
            tiene_sobrestock=True,
            tiene_valor_inventario=True,

            tiene_prediccion_agotamiento=True,
            tiene_recomendacion_compra=True,
            tiene_ia_avanzada=True,

            tiene_auditoria=True,
            tiene_multisucursal=True,
            tiene_transferencias=True,

            tiene_dashboard_ejecutivo=True,
            tiene_indicadores_financieros=True,

            tiene_api=True,
            tiene_reportes_personalizados=True,
            tiene_soporte_prioritario=True,

            activo=True,
            destacado=True,
            orden=4
        )

    ])

            db.session.commit()

            print("✔ Planes SaaS creados.")

# ==================================================
# USUARIO ACTUAL DE SESIÓN
# ==================================================

def obtener_usuario_actual():

    usuario_id = session.get("usuario_id")

    if not usuario_id:

        return None


    return db.session.get(
        Usuario,
        usuario_id
    )
def obtener_empresa_actual_obj():

    usuario = obtener_usuario_actual()

    if not usuario:
        return None

    if not usuario.empresa_id:
        return None

    return Empresa.query.get(usuario.empresa_id)

# ==================================================
# ACTUALIZAR VALORIZACIÓN DEL PRODUCTO
# ==================================================

def actualizar_valorizacion_producto(producto):
    """
    Recalcula automáticamente los valores financieros
    del producto.

    - Valor inventario = Stock × Costo promedio
    - Margen de ganancia
    """

    stock = int(producto.stock or 0)

    costo = float(producto.costo_promedio or 0)

    precio = float(producto.precio_venta or 0)

    # Valor total del inventario

    producto.valor_inventario = round(
        stock * costo,
        2
    )

    # Margen de ganancia %

    if costo > 0:

        producto.margen_ganancia = round(
            ((precio - costo) / costo) * 100,
            2
        )

    else:

        producto.margen_ganancia = 0

# ==================================================
# REGISTRAR AUDITORÍA
# ==================================================

def registrar_auditoria(
    accion,
    modulo,
    descripcion,
    empresa=None,
    usuario=None,
    datos_anteriores=None,
    datos_nuevos=None):
    """
    Registra un evento del sistema.
    """
    try:
        if usuario is None:
            usuario = obtener_usuario_actual()
            auditoria = Auditoria(
                accion=accion,
                modulo=modulo,
                descripcion=descripcion,
                empresa_id=(
                empresa.id
                if empresa
                else (
                    usuario.empresa_id
                    if usuario
                    else None
                    )),
                    usuario_id=(
                        usuario.id
                        if usuario
                        else None
                        ),

            datos_anteriores=datos_anteriores,

            datos_nuevos=datos_nuevos,

            ip_usuario=request.remote_addr,

            user_agent=request.user_agent.string

        )

        db.session.add(auditoria)

        db.session.commit()

    except Exception as e:

        db.session.rollback()

        print(
            "Error registrando auditoría:",
            e
        )


# ==================================================
# CONTEXTO GLOBAL PARA PLANTILLAS
# ==================================================

@app.context_processor
def contexto_global():

    usuario = obtener_usuario_actual()

    return {

        "usuario_actual": usuario,

        "es_super_admin": (
            usuario is not None
            and usuario.rol == "super_admin"
        ),

        "es_admin_empresa": (
            usuario is not None
            and usuario.rol == "admin_empresa"
        )

    }

# ==================================================
# REGISTRO NUEVA EMPRESA SaaS
# ==================================================

@app.route("/registro", methods=["GET", "POST"])
def registro():

    if "usuario_id" in session:

        return redirect(
            url_for("dashboard")
        )


    if request.method == "POST":

        try:

# ======================================
# DATOS FORMULARIO
# ======================================

            nombre_empresa = request.form.get(
                "empresa",
                ""
            ).strip()


            nombre_usuario = request.form.get(
                "nombre",
                ""
            ).strip()


            email = request.form.get(
                "email",
                ""
            ).lower().strip()


            password = request.form.get(
                "password",
                ""
            )


            confirm_password = request.form.get(
                "confirm_password",
                ""
            )



# ======================================
# VALIDACIONES
# ======================================

            if not nombre_empresa:

                flash(
                    "Debe ingresar nombre de empresa.",
                    "danger"
                )

                return redirect(
                    url_for("registro")
                )



            if not nombre_usuario:

                flash(
                    "Debe ingresar nombre del administrador.",
                    "danger"
                )

                return redirect(
                    url_for("registro")
                )



            if not email:

                flash(
                    "Debe ingresar correo electrónico.",
                    "danger"
                )

                return redirect(
                    url_for("registro")
                )



            if len(password) < 8:

                flash(
                    "La contraseña debe tener mínimo 8 caracteres.",
                    "danger"
                )

                return redirect(
                    url_for("registro")
                )



            if password != confirm_password:

                flash(
                    "Las contraseñas no coinciden.",
                    "danger"
                )

                return redirect(
                    url_for("registro")
                )


# ======================================
# VALIDAR EXISTENCIA
# ======================================


            usuario_existente = Usuario.query.filter_by(
                email=email
            ).first()



            if usuario_existente:

                flash(
                    "El correo ya está registrado.",
                    "warning"
                )

                return redirect(
                    url_for("registro")
                )



            empresa_existente = Empresa.query.filter_by(
                email=email
            ).first()



            if empresa_existente:

                flash(
                    "Ya existe una empresa registrada con ese correo.",
                    "warning"
                )

                return redirect(
                    url_for("registro")
                )


# ======================================
# CREAR EMPRESA
# ======================================


            hoy = datetime.now(UTC).date()



            empresa = Empresa(

                nombre=nombre_empresa,

                email=email,

                plan="prueba",

                estado="activo",

                fecha_inicio_plan=hoy,

                fecha_vencimiento=(
                    hoy +
                    timedelta(days=30)
                )

            )



            db.session.add(
                empresa
            )


            db.session.flush()


# ======================================
# CREAR ADMIN EMPRESA
# ======================================


            usuario = Usuario(

                nombre=nombre_usuario,

                email=email,

                rol="admin_empresa",

                empresa_id=empresa.id,

                activo=True,

                email_verificado=False

            )


            usuario.password = generate_password_hash(password)

            db.session.add(
                usuario
            )


            db.session.flush()


# ======================================
# CONFIGURACIÓN INICIAL
# ======================================


            configuracion = ConfiguracionEmpresa(

    empresa_id=empresa.id,

    moneda="CLP",

    idioma="es",

    zona_horaria="America/Santiago",

    alerta_stock_bajo=True,

    alerta_sobre_stock=True)



            db.session.add(
                configuracion
            )


# ======================================
# GUARDAR
# ======================================


            db.session.commit()


# ======================================
# LOGIN AUTOMATICO
# ======================================


            session.clear()


            session["usuario_id"] = usuario.id

            db.session.commi

            registrar_auditoria(
                accion="LOGIN",
                modulo="Autenticación",
                descripcion=f"Inicio de sesión de {usuario.nombre}",
                usuario=usuario
                )

            session["empresa_id"] = empresa.id

            session["rol"] = usuario.rol

            session.permanent = True


            flash(
                "Cuenta creada correctamente. Bienvenido a NexuStock.",
                "success"
            )



            return redirect(
                url_for("dashboard")
            )


        except Exception as e:


            db.session.rollback()
            
            app.logger.exception(
                "Error creando empresa"
            )


            flash(
                "Error interno creando la cuenta.",
                "danger"
            )


            return redirect(
                url_for("registro")
            )




    return render_template(
        "registro.html"
    )


# ==================================================
# LOGIN REQUERIDO
# ==================================================

def login_requerido(func):

    @wraps(func)
    def decorador(*args, **kwargs):

        if "usuario_id" not in session:

            flash(
                "Debe iniciar sesión.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        usuario = obtener_usuario_actual()

        if not usuario:

            session.clear()

            flash(
                "Sesión inválida.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        if not usuario.activo:

            session.clear()

            flash(
                "La cuenta está desactivada.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        return func(*args, **kwargs)

    return decorador

# ==================================================
# LANDING PAGE
# ==================================================

@app.route("/")
def inicio():

    return render_template(
        "landing.html"
    )

# ----------------------------------
# LOGIN
# ----------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        usuario = Usuario.query.filter_by(email=email).first()

        # ----------------------------------
        # USUARIO NO EXISTE
        # ----------------------------------
        if not usuario:
            flash("Correo o contraseña incorrectos.", "danger")
            return redirect(url_for("login"))

        # ----------------------------------
        # CUENTA DESACTIVADA
        # ----------------------------------
        if not usuario.activo:
            flash("Esta cuenta se encuentra desactivada.", "danger")
            return redirect(url_for("login"))

        # ----------------------------------
        # CUENTA BLOQUEADA
        # ----------------------------------
        if usuario.esta_bloqueado():
            flash(
                "Cuenta bloqueada temporalmente por seguridad.",
                "danger",
            )
            return redirect(url_for("login"))

        # ----------------------------------
        # VALIDAR PASSWORD
        # ----------------------------------
        if not check_password_hash(usuario.password, password):
            usuario.incrementar_intentos()
            db.session.commit()

            flash("Correo o contraseña incorrectos.", "danger")
            return redirect(url_for("login"))

        # ----------------------------------
        # LOGIN CORRECTO
        # ----------------------------------
        usuario.reset_login()
        usuario.registrar_acceso(
            ip=request.remote_addr,
            user_agent=request.headers.get("User-Agent"),
        )

        # ----------------------------------
        # VALIDACIÓN EMPRESA (SUPER ADMIN IGNORA ESTO)
        # ----------------------------------
        if usuario.rol != "super_admin":
            if usuario.empresa:
                if usuario.empresa.estado != "activo":
                    flash("Su empresa se encuentra suspendida.", "danger")
                    db.session.commit()
                    return redirect(url_for("login"))

                if empresa_vencida(usuario.empresa):
                    flash("El plan de su empresa ha vencido.", "danger")
                    db.session.commit()
                    return redirect(url_for("login"))

        # Guardar sesión
        session.clear()
        session["usuario_id"] = usuario.id
        session.permanent = True

        # ----------------------------------
        # AUDITORÍA CON PROTECCIÓN ANTI-FALLO
        # ----------------------------------
        try:
            registrar_auditoria(
                accion="LOGIN",
                modulo="Autenticación",
                descripcion=f"Inicio de sesión de {usuario.nombre}",
                usuario=usuario,
            )
        except Exception as e:
            logger.exception("Error registrando auditoría en login: %s", str(e))

        db.session.commit()

        flash(f"Bienvenido a NexuStock, {usuario.nombre}.", "success")
        return redirect(url_for("dashboard"))

    return render_template("login.html")

# ==================================================
# RESTABLECER PASSWORD CON TOKEN
# ==================================================

@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):

    try:

        usuario = Usuario.query.filter_by(
            token_reset_password_hash=token
        ).first()

        if not usuario:

            flash(
                "El enlace de recuperación no es válido.",
                "danger"
            )

            return redirect(
                url_for("login")
            )

        # ----------------------------------
        # VALIDAR EXPIRACIÓN
        # ----------------------------------

        if (
            usuario.token_expiracion
            and usuario.token_expiracion < datetime.now(UTC)
        ):

            usuario.token_reset_password_hash = None
            usuario.token_expiracion = None

            db.session.commit()

            flash(
                "El enlace de recuperación expiró.",
                "warning"
            )

            return redirect(
                url_for("login")
            )

        # ----------------------------------
        # CAMBIAR PASSWORD
        # ----------------------------------

        if request.method == "POST":

            password = request.form.get(
                "password",
                ""
            )

            confirm_password = request.form.get(
                "confirm_password",
                ""
            )

            if len(password) < 8:

                flash(
                    "La contraseña debe tener mínimo 8 caracteres.",
                    "danger"
                )

                return redirect(
                    request.url
                )

            if password != confirm_password:

                flash(
                    "Las contraseñas no coinciden.",
                    "danger"
                )

                return redirect(
                    request.url
                )

            usuario.password = generate_password_hash(password)

            usuario.token_reset_password_hash = None
            usuario.token_expiracion = None

            usuario.ultimo_cambio_password = datetime.now(UTC)
            usuario.password_expirada = False

            db.session.commit()

            flash(
                "Contraseña actualizada correctamente.",
                "success"
            )

            return redirect(
                url_for("login")
            )

        return render_template(
            "reset_password.html"
        )

    except Exception:

        db.session.rollback()

        logger.exception(
            "Error restableciendo contraseña"
        )

        flash(
            "Error interno.",
            "danger"
        )

        return redirect(
            url_for("login")
        )

# ==================================================
# SOLICITAR RECUPERACIÓN PASSWORD
# ==================================================

@app.route("/olvide-password", methods=["GET", "POST"])
def olvide_password():

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).lower().strip()

        usuario = Usuario.query.filter_by(
            email=email
        ).first()

        if usuario:

            token = serializer.dumps(
                usuario.email,
                salt="reset-password"
            )

            usuario.token_reset_password_hash = token

            usuario.token_expiracion = (
                datetime.now(UTC)
                + timedelta(hours=1)
            )

            db.session.commit()

            enlace = url_for(
                "reset_password",
                token=token,
                _external=True
            )

            mensaje = Message(
                subject="Recuperación de contraseña - NexuStock",
                recipients=[usuario.email]
            )

            mensaje.body = f"""
Hola,

Recibimos una solicitud para restablecer la contraseña de tu cuenta de NexuStock.

Para crear una nueva contraseña, haz clic en el siguiente enlace:

{enlace}

Este enlace expirará en 1 hora.

Si no solicitaste este cambio, puedes ignorar este correo de forma segura.

Equipo NexuStock
"""

            mail.send(mensaje)

        flash(
            "Si el correo existe, recibirás un enlace para restablecer tu contraseña.",
            "info"
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "olvide_password.html"
    )

# ==================================================
# LOGOUT / CERRAR SESIÓN
# ==================================================

@app.route("/logout")
def logout():

    try:

        usuario = obtener_usuario_actual()


        if usuario:

            usuario.cerrar_sesion()

            usuario = obtener_usuario_actual()


            if usuario:
                registrar_auditoria(
                    accion="LOGOUT",
                    modulo="Autenticación",
                    descripcion=f"Cierre de sesión de {usuario.nombre}",
                    usuario=usuario
                    )

            db.session.commit()


        session.clear()


        flash(
            "Sesión cerrada correctamente.",
            "success"
        )


    except Exception:
        db.session.rollback()
        app.logger.exception(
            "Error cerrando sesión"
        )


        session.clear()


        flash(
            "Sesión finalizada.",
            "success"
        )


    return redirect(
        url_for("login")
    )

# ==================================================
# USUARIOS
# ==================================================

@app.route("/usuarios")
@login_requerido
def usuarios():

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(url_for("logout"))

    if usuario_actual.rol not in [
        "admin_empresa",
        "super_admin"
    ]:

        flash(
            "No posee permisos para acceder a esta sección.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    if usuario_actual.rol == "super_admin":

        usuarios = Usuario.query.order_by(
            Usuario.nombre.asc()
        ).all()

    else:

        usuarios = Usuario.query.filter_by(
            empresa_id=usuario_actual.empresa_id
        ).order_by(
            Usuario.nombre.asc()
        ).all()

    return render_template(

        "usuarios.html",

        usuarios=usuarios

    )


# ==================================================
# CREAR NUEVO USUARIO
# ==================================================

@app.route("/nuevo-usuario", methods=["GET", "POST"])
@login_requerido
def nuevo_usuario():

    usuario_actual = obtener_usuario_actual()


    if not usuario_actual:

        return redirect(
            url_for("login")
        )


    # ======================================
    # VALIDAR PERMISOS
    # ======================================

    if usuario_actual.rol not in [
        "admin_empresa",
        "super_admin"
    ]:

        flash(
            "No tienes permisos para crear usuarios.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )



    empresa_actual = obtener_empresa_actual_obj()



    if not empresa_actual:

        flash(
            "Empresa no encontrada.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )


# ======================================
# CREAR USUARIO
# ======================================

    if request.method == "POST":


        try:


            nombre = request.form.get(
                "nombre",
                ""
            ).strip()



            email = request.form.get(
                "email",
                ""
            ).lower().strip()



            password = request.form.get(
                "password",
                ""
            )



            rol = request.form.get(
                "rol",
                "empleado"
            )



# -------------------------------
# VALIDACIONES
# -------------------------------


            if not nombre or not email or not password:

                flash(
                    "Todos los campos son obligatorios.",
                    "danger"
                )

                return redirect(
                    url_for("nuevo_usuario")
                )



            if len(password) < 8:

                flash(
                    "La contraseña debe tener mínimo 8 caracteres.",
                    "danger"
                )

                return redirect(
                    url_for("nuevo_usuario")
                )



            usuario_existente = Usuario.query.filter_by(
                email=email
            ).first()



            if usuario_existente:

                flash(
                    "Ese correo ya está registrado.",
                    "warning"
                )

                return redirect(
                    url_for("nuevo_usuario")
                )



            # Seguridad de roles

            roles_permitidos = [

                "empleado",

                "supervisor",

                "admin_empresa"

            ]



            if rol not in roles_permitidos:

                rol = "empleado"



# -------------------------------
# CREAR USUARIO
# -------------------------------


            nuevo = Usuario(

                nombre=nombre,

                email=email,

                rol=rol,

                empresa_id=empresa_actual.id,

                activo=True,

                email_verificado=False

            )



            nuevo.set_password(
                password
            )



            db.session.add(
                nuevo
            )


            db.session.flush()



# -------------------------------
# AUDITORÍA
# -------------------------------


            auditoria = Auditoria.crear(

                accion="crear_usuario",

                modulo="usuarios",

                descripcion=(

                    f"Usuario creado: {nuevo.email}"

                ),

                empresa_id=empresa_actual.id,

                usuario_id=usuario_actual.id,

                ip=request.remote_addr,

                user_agent=request.headers.get(
                    "User-Agent"
                )

            )


            db.session.add(
                auditoria
            )


            db.session.commit()



            flash(
                "Usuario creado correctamente.",
                "success"
            )



            return redirect(
                url_for("usuarios")
            )



        except Exception:


            db.session.rollback()


            logger.exception(
                "Error creando usuario"
            )


            flash(
                "Error interno creando usuario.",
                "danger"
            )



    return render_template(
        "nuevo_usuario.html"
    )


# ==================================================
# DASHBOARD PRINCIPAL INTELIGENTE
# ==================================================
@app.route("/dashboard")
@login_requerido
def dashboard():

    usuario_actual = obtener_usuario_actual()


    if not usuario_actual:

        session.clear()

        flash(
            "Sesión inválida.",
            "danger"
        )

        return redirect(
            url_for("login")
        )



    # ===============================
    # SUPER ADMIN
    # ===============================

    if usuario_actual.rol == "super_admin":

        return redirect(
            url_for("super_admin")
        )



    empresa_actual = obtener_empresa_actual_obj()



    if not empresa_actual:

        flash(
            "Empresa no encontrada.",
            "danger"
        )

        return redirect(
            url_for("logout")
        )



    # ===============================
    # PRODUCTOS
    # ===============================

    productos = Producto.query.filter_by(
        empresa_id=empresa_actual.id
    ).all()



    total_productos = len(productos)



# ===============================
# MOVIMIENTOS
# ===============================

    movimientos = (
    Movimiento.query
    .options(joinedload(Movimiento.producto))
    .filter_by(
        empresa_id=empresa_actual.id
    )
    .all()
    )



    total_movimientos = len(movimientos)



    # ===============================
    # VALOR INVENTARIO
    # ===============================

    valor_inventario = 0
    for producto in productos:
        valor_inventario += float(
        producto.calcular_valor_inventario() or 0
        )



    # ===============================
    # STOCK BAJO
    # ===============================

    productos_stock_bajo = [

        p for p in productos

        if (p.stock or 0) <= (p.stock_minimo or 0)

    ]



    stock_bajo = len(
        productos_stock_bajo
    )



    # ===============================
    # SOBRE STOCK
    # ===============================

    productos_sobre_stock = [

    p for p in productos

    if (
        p.stock_maximo
        and
        (p.stock or 0) > p.stock_maximo
    )
    ]



    # ===============================
    # SIN MOVIMIENTO
    # ===============================

    productos_con_movimiento = set(

        m.producto_id

        for m in movimientos

        if m.producto_id

    )



    productos_sin_movimiento = [

        p for p in productos

        if p.id not in productos_con_movimiento

    ]



    total_sin_movimiento = len(
        productos_sin_movimiento
    )



# ===============================
# RECOMENDACIONES IA
# ===============================

    productos_recomendados = []

    for producto in productos:

        if not producto.activo:
            continue

        demanda = (

            producto.consumo_promedio_diario
            or
            producto.demanda_estimada
            or
            0

        )

        punto_reorden = (

            demanda *
            (producto.tiempo_reposicion_dias or 7)

        ) + (

            producto.stock_seguridad or 0

        )

        if (producto.stock or 0) <= punto_reorden:

            productos_recomendados.append(
                producto
            )

    riesgo_quiebre = sum(

        1

        for producto in productos

        if (producto.stock or 0) <= 0

    )

    # ===============================
    # CAPITAL INMOVILIZADO REAL
    # ===============================

    dinero_inmovilizado = sum(

        (producto.stock or 0) *
        float(producto.costo_promedio or 0)

        for producto in productos_sin_movimiento

    )


    # ===============================
    # SALUD INVENTARIO
    # ===============================

    salud_inventario = 100

    penalizacion = 0

    penalizacion += stock_bajo * 3

    penalizacion += total_sin_movimiento * 2

    penalizacion += len(productos_sobre_stock)

    penalizacion += riesgo_quiebre * 5

    salud_inventario = max(

        0,

        min(

            100,

            salud_inventario - penalizacion

        )

    )


    if salud_inventario >= 80:

        estado_salud = "Excelente"

        color_salud = "green"

    elif salud_inventario >= 50:

        estado_salud = "Regular"

        color_salud = "yellow"

    else:

        estado_salud = "Crítico"

        color_salud = "red"

    # ===============================
    # COPILOTO IA
    # ===============================

    acciones_hoy = []


    if riesgo_quiebre > 0:

        acciones_hoy.append(

            f"Existen {riesgo_quiebre} productos agotados. Prioriza su reposición."

        )


    if stock_bajo > 0:

        acciones_hoy.append(

            f"Revisar {stock_bajo} productos con stock bajo."

        )


    if total_sin_movimiento > 0:

        acciones_hoy.append(

            f"Analizar {total_sin_movimiento} productos sin movimiento para liberar capital."

        )


    if len(productos_sobre_stock) > 0:

        acciones_hoy.append(

            f"Reducir compras en {len(productos_sobre_stock)} productos con sobre stock."

        )


    if salud_inventario >= 80:

        acciones_hoy.append(

            "El inventario presenta un buen estado general."

        )


    if not acciones_hoy:

        acciones_hoy.append(

            "No existen acciones pendientes por hoy."

        )


    # ===============================
    # RANKING VENTAS
    # ===============================

    ventas = {}

    for movimiento in movimientos:

        if (
            movimiento.tipo == "salida"
            and movimiento.producto is not None
        ):

            producto = movimiento.producto

            ventas[producto.id] = {

                "nombre": producto.nombre,

                "ventas": ventas.get(

                    producto.id,

                    {
                        "nombre": producto.nombre,
                        "ventas": 0
                    }

                )["ventas"] + (movimiento.cantidad or 0)

            }

    ranking = list(
        ventas.values()
    )

    productos_mas_vendidos = sorted(

        ranking,

        key=lambda x: x["ventas"],

        reverse=True

    )[:5]

    productos_menos_vendidos = sorted(

        ranking,

        key=lambda x: x["ventas"]

    )[:5]


    return render_template(

        "dashboard.html",


        usuario_actual=usuario_actual,


        empresa_actual=empresa_actual,


        total_productos=total_productos,


        stock_bajo=stock_bajo,


        total_movimientos=total_movimientos,


        valor_inventario=valor_inventario,


        riesgo_quiebre=riesgo_quiebre,


        dinero_inmovilizado=dinero_inmovilizado,


        productos_recomendados=productos_recomendados,


        salud_inventario=salud_inventario,


        estado_salud=estado_salud,


        color_salud=color_salud,


        acciones_hoy=acciones_hoy,


        total_sin_movimiento=total_sin_movimiento,


        productos_sobre_stock=productos_sobre_stock,


        productos_sin_movimiento=productos_sin_movimiento,


        productos_stock_bajo=productos_stock_bajo,


        productos_mas_vendidos=productos_mas_vendidos,


        productos_menos_vendidos=productos_menos_vendidos

    )





##==============================================================
#SECCION PLANES
##==============================================================





# ==================================================
# MI PLAN SaaS
# ==================================================

@app.route("/mi-plan")
@login_requerido
def mi_plan():

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(url_for("login"))

    empresa = usuario_actual.empresa

    if not empresa:
        flash(
            "No existe una empresa asociada.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    return render_template(

    "mi_plan.html",

    usuario_actual=usuario_actual,

    empresa=empresa,

    total_productos=len(empresa.productos),

    total_usuarios=len(empresa.usuarios),

    total_movimientos=len(empresa.movimientos)

)

# ==================================================
# INGRESOS MENSUALES
# ==================================================

def calcular_ingresos_mensuales():
    """
    Calcula el total de pagos confirmados del mes actual.
    """

    hoy = datetime.utcnow()

    inicio_mes = datetime(
        hoy.year,
        hoy.month,
        1
    )

    pagos = Pago.query.filter(
        Pago.created_at >= inicio_mes
    ).all()

    total = 0

    for pago in pagos:

        if pago.estado != "pagado":
            continue
        total += float(pago.monto or 0)

        return total

#======================================================
#SOLICITAR PLAN
#======================================================
@app.route("/solicitar-plan/<plan>", methods=["POST"])
@login_requerido
def solicitar_plan(plan):

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(url_for("login"))

    empresa = usuario_actual.empresa

    if not empresa:

        flash(
            "Empresa no encontrada.",
            "danger"
        )

        return redirect(
            url_for("mi_plan")
        )

    plan = plan.lower()

    if plan == "basico":
        nombre_plan = "Básico"
    elif plan == "profesional":
        nombre_plan = "Profesional"
    elif plan == "premium":
        nombre_plan = "Premium"
    else:
        nombre_plan = None

    plan_db = PlanSaaS.query.filter_by(
            nombre=nombre_plan,
            activo=True
        ).first()

    if not plan_db:

        flash(
            "El plan seleccionado no existe.",
            "danger"
        )

        return redirect(
            url_for("mi_plan")
        )

    pago = Pago(

        empresa_id=empresa.id,

        plan_id=plan_db.id,

        monto=plan_db.precio_mensual,

        estado="pendiente"

    )

    db.session.add(pago)
    db.session.commit()
    print("Pago creado:", pago.id)

    return redirect(
        url_for(
            "checkout",
            pago_id=pago.id
        )
    )

#=========================================
# PAGAR PLAN
#=========================================

@app.route("/pagar/<plan>")
@login_requerido
def pagar_plan(plan):

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(url_for("login"))

    empresa = usuario_actual.empresa

    planes = PlanSaaS.query.filter_by(
        activo=True
    ).all()

    plan_obj = next(
        (p for p in planes if p.nombre.lower() == plan.lower()),
        None
    )

    if not plan_obj:

        flash(
            "Plan no encontrado.",
            "danger"
        )

        return redirect(
            url_for("mi_plan")
        )

    return render_template(
        "seleccionar_pago.html",
        empresa=empresa,
        plan=plan_obj
    )
#================================================
# PAGAR MERCADOPAGO
#================================================
@app.route("/pagar/mercadopago/<int:pago_id>")
@login_requerido
def pagar_mercadopago(pago_id):

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(url_for("login"))

    empresa = usuario_actual.empresa

    pago = Pago.query.get_or_404(pago_id)

    if pago.empresa_id != empresa.id:

        flash(
            "Pago no válido.",
            "danger"
        )

        return redirect(
            url_for("mi_plan")
        )

    plan_obj = PlanSaaS.query.get_or_404(
        pago.plan_id
    )

    preference_data = {

        "items": [

            {

                "title": f"NexuStock - Plan {plan_obj.nombre}",

                "quantity": 1,

                "currency_id": "CLP",

                "unit_price": float(
                    plan_obj.precio_mensual
                )

            }

        ],

        "external_reference": str(
            pago.id
        ),

        "back_urls": {

            "success": url_for(
                "mercadopago_success",
                _external=True
            ),

            "failure": url_for(
                "mercadopago_failure",
                _external=True
            ),

            "pending": url_for(
                "mercadopago_pending",
                _external=True
            )

        },

        "notification_url": url_for(
            "webhook_mercadopago",
            _external=True
        ),

        "auto_return": "approved"

    }

    print("=" * 60)
    print("PREFERENCE DATA")
    print(preference_data)
    print("=" * 60)

    try:

        print("Enviando preferencia a Mercado Pago...")

        respuesta = sdk_mp.preference().create(
            preference_data
        )

        print("RESPUESTA MP:")
        print(respuesta)

    except Exception as e:

        print("ERROR MERCADO PAGO:")
        print(e)

        flash(
            f"Error Mercado Pago: {e}",
            "danger"
        )

        return redirect(
            url_for("mi_plan")
        )

    if respuesta.get("status") != 201:

        print("Mercado Pago respondió con error:")
        print(respuesta)

        flash(
            "No fue posible generar el pago.",
            "danger"
        )

        return redirect(
            url_for("mi_plan")
        )

    # ----------------------------------------
    # Guardar datos devueltos por Mercado Pago
    # ----------------------------------------

    pago.preference_id = respuesta["response"]["id"]

    pago.url_pago = respuesta["response"]["init_point"]

    db.session.commit()

    print("PREFERENCE ID:")
    print(
        pago.preference_id
    )

    print("URL DE PAGO:")
    print(
        pago.url_pago
    )

    return redirect(
        pago.url_pago
    )


# ==================================================
# MERCADO PAGO - SUCCESS
# ==================================================

@app.route("/mercadopago/success")
def mercadopago_success():

    payment_id = request.args.get("payment_id")
    status = request.args.get("status")
    preference_id = request.args.get("preference_id")

    print("=" * 60)
    print("PAGO APROBADO")
    print("payment_id:", payment_id)
    print("status:", status)
    print("preference_id:", preference_id)
    print("=" * 60)

    pago = Pago.query.filter_by(
        preference_id=preference_id
    ).first()

    if not pago:

        flash(
            "No se encontró el pago.",
            "danger"
        )

        return redirect(
            url_for("mi_plan")
        )

    pago.estado = "pagado"

    pago.fecha_pago = datetime.utcnow()

    pago.codigo_transaccion = payment_id

# ----------------------------------------
# ACTIVAR PLAN
# ----------------------------------------

    empresa = pago.empresa
    plan = pago.plan
    empresa.plan = (
    plan.nombre
    .strip()
    .lower()
    .replace("á", "a")
    .replace("é", "e")
    .replace("í", "i")
    .replace("ó", "o")
    .replace("ú", "u")
    )  
    empresa.estado = "activo"
    empresa.fecha_inicio_plan = datetime.utcnow()
    empresa.fecha_vencimiento = (
        datetime.utcnow() + timedelta(days=30)
        )

    db.session.commit()

    flash(
        "Pago realizado correctamente.",
        "success"
    )

    return redirect(
        url_for("mi_plan")
    )


# ==================================================
# MERCADO PAGO - FAILURE
# ==================================================

@app.route("/mercadopago/failure")
def mercadopago_failure():

    return "FAILURE"


# ==================================================
# MERCADO PAGO - PENDING
# ==================================================

@app.route("/mercadopago/pending")
def mercadopago_pending():

    return "PENDING"

# =========================================
# WEBHOOK MERCADO PAGO
# =========================================

@app.route("/webhook/mercadopago", methods=["POST"])
def webhook_mercadopago():

    datos = request.get_json(silent=True)

    print("=" * 60)
    print("WEBHOOK MERCADO PAGO RECIBIDO")
    print(datos)
    print("=" * 60)

    if not datos:
        return "", 200

    tipo = datos.get("type")

    if tipo != "payment":
        return "", 200

    payment_id = (
        datos
        .get("data", {})
        .get("id")
    )

    if not payment_id:
        return "", 200


    try:

        respuesta = sdk_mp.payment().get(
            payment_id
        )

        print("=" * 60)
        print("RESPUESTA PAYMENT")
        print(respuesta)
        print("=" * 60)


    except Exception as e:

        print(
            "ERROR CONSULTANDO MERCADO PAGO:",
            e
        )

        return "", 200


    pago_mp = respuesta.get(
        "response",
        {}
    )


    estado_mp = pago_mp.get(
        "status"
    )


    external_reference = pago_mp.get(
        "external_reference"
    )


    print("ESTADO MP:", estado_mp)
    print(
        "EXTERNAL REFERENCE:",
        external_reference
    )


    if not external_reference:
        return "", 200


    try:

        pago_id = int(
            external_reference
        )

    except Exception:

        return "", 200


    pago = Pago.query.get(
        pago_id
    )


    if not pago:

        print(
            "Pago NexuStock no encontrado:",
            pago_id
        )

        return "", 200



    # =========================================
    # PAGO APROBADO
    # =========================================

    if estado_mp == "approved":


        # Evita duplicar confirmaciones

        if pago.estado == "pagado":

            return "", 200



        empresa = pago.empresa

        plan = PlanSaaS.query.get(
            pago.plan_id
        )


        if not plan:

            return "", 200



        pago.estado = "pagado"

        pago.fecha_pago = datetime.utcnow()

        pago.fecha_confirmacion = datetime.utcnow()

        pago.metodo_pago = "Mercado Pago"

        pago.proveedor_pago = "mercadopago"



        empresa.plan = (
            plan.nombre
            .strip()
            .lower()
        )


        empresa.fecha_inicio_plan = (
            datetime.utcnow()
        )


        empresa.fecha_vencimiento = (
            datetime.utcnow()
            +
            timedelta(days=30)
        )


        empresa.estado = "activo"

        empresa.activo = True


        db.session.commit()


        print(
            "Pago Mercado Pago aplicado correctamente"
        )


    elif estado_mp in [
        "rejected",
        "cancelled"
    ]:


        pago.estado = estado_mp

        db.session.commit()


        print(
            "Pago Mercado Pago rechazado/cancelado"
        )


    return "", 200


# ==================================================
# WEBPAY PLUS (PRUEBAS)
# ==================================================

webpay_options = WebpayOptions(
    commerce_code=IntegrationCommerceCodes.WEBPAY_PLUS,
    api_key=IntegrationApiKeys.WEBPAY,
    integration_type=IntegrationType.TEST
)

webpay_transaction = Transaction(webpay_options)

print("=" * 60)
print("WEBPAY TEST")
print("Commerce Code:", IntegrationCommerceCodes.WEBPAY_PLUS)
print("API Key:", IntegrationApiKeys.WEBPAY)
print("Integration:", IntegrationType.TEST)
print("=" * 60)

# ==================================================
# PAGAR WEBPAY
# ==================================================

@app.route("/pagar/webpay/<int:pago_id>")
@login_requerido
def pagar_webpay(pago_id):

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(url_for("login"))

    empresa = usuario_actual.empresa

    pago = Pago.query.get_or_404(pago_id)

    if pago.empresa_id != empresa.id:

        flash(
            "Pago no válido.",
            "danger"
        )

        return redirect(
            url_for("mi_plan")
        )

    plan = PlanSaaS.query.get_or_404(
        pago.plan_id
    )

    buy_order = f"NEXU-{pago.id}"

    session_id = str(
        empresa.id
    )

    return_url = url_for(
        "webpay_commit",
        _external=True
    )

    print("=" * 60)
    print("CREANDO TRANSACCIÓN WEBPAY")
    print("BUY ORDER:", buy_order)
    print("SESSION:", session_id)
    print("MONTO:", int(plan.precio_mensual))
    print("RETURN URL:", return_url)
    print("=" * 60)

    try:

        respuesta = webpay_transaction.create(
            buy_order=buy_order,
            session_id=session_id,
            amount=int(plan.precio_mensual),
            return_url=return_url
        )

        print("RESPUESTA WEBPAY")
        print(respuesta)

    except Exception as e:

        print("ERROR WEBPAY")
        print(e)

        flash(
            f"Error Webpay: {e}",
            "danger"
        )

        return redirect(
            url_for("mi_plan")
        )

    pago.codigo_transaccion = respuesta["token"]

    pago.proveedor_pago = "webpay"

    db.session.commit()

    return redirect(
        respuesta["url"] + "?token_ws=" + respuesta["token"]
    )

# ==================================================
# WEBPAY COMMIT
# ==================================================

@app.route("/webpay/commit", methods=["GET", "POST"])
@login_requerido
def webpay_commit():

    token = request.values.get("token_ws")

    if not token:

        flash(
            "No se recibió el token de Webpay.",
            "danger"
        )

        return redirect(
            url_for("mi_plan")
        )

    try:

        respuesta = webpay_transaction.commit(token)

        print("=" * 60)
        print("RESPUESTA COMMIT WEBPAY")
        print(respuesta)
        print("=" * 60)

    except Exception as e:

        print("ERROR COMMIT WEBPAY")
        print(e)

        flash(
            f"Error confirmando pago: {e}",
            "danger"
        )

        return redirect(
            url_for("mi_plan")
        )

    estado = respuesta.get("status")
    buy_order = respuesta.get("buy_order")

    if estado != "AUTHORIZED":

        flash(
            "El pago no fue autorizado.",
            "warning"
        )

        return redirect(
            url_for("mi_plan")
        )

    try:

        pago_id = int(
            buy_order.replace("NEXU-", "")
        )

    except Exception:

        flash(
            "Orden inválida.",
            "danger"
        )

        return redirect(
            url_for("mi_plan")
        )

    pago = Pago.query.get_or_404(
        pago_id
    )

    # Evitar confirmar el mismo pago dos veces
    if pago.estado == "pagado":

        flash(
            "Este pago ya fue confirmado.",
            "info"
        )

        return redirect(
            url_for("mi_plan")
        )

    empresa = pago.empresa

    plan = PlanSaaS.query.get_or_404(
        pago.plan_id
    )

    # ==========================================
    # ACTUALIZAR PAGO
    # ==========================================

    pago.estado = "pagado"

    pago.fecha_pago = datetime.utcnow()

    pago.fecha_confirmacion = datetime.utcnow()

    pago.codigo_transaccion = respuesta.get(
        "authorization_code"
    )

    pago.metodo_pago = "Webpay Plus"

    pago.proveedor_pago = "webpay"

    # ==========================================
    # ACTUALIZAR EMPRESA
    # ==========================================

    empresa.plan = plan.nombre.lower()

    empresa.fecha_inicio_plan = datetime.utcnow()

    empresa.fecha_vencimiento = (
        datetime.utcnow()
        +
        timedelta(days=30)
    )

    empresa.estado = "activo"

    empresa.activo = True

    db.session.commit()

    flash(
        "✅ Pago realizado correctamente. Su plan ha sido activado.",
        "success"
    )

    return redirect(
        url_for("mi_plan")
    )

# ==================================================
# CHECKOUT
# ==================================================

@app.route("/checkout/<int:pago_id>")
@login_requerido
def checkout(pago_id):

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(url_for("login"))

    pago = Pago.query.get_or_404(pago_id)

    if pago.empresa_id != usuario_actual.empresa_id:

        flash(
            "No tienes permisos para acceder a este pago.",
            "danger"
        )

        return redirect(
            url_for("mi_plan")
        )

    plan = PlanSaaS.query.get(
        pago.plan_id
    )

    return render_template(

        "checkout.html",

        usuario_actual=usuario_actual,

        empresa=usuario_actual.empresa,

        pago=pago,

        plan=plan

    )







##==================================================
# NEXUSTOCK SUPER ADMIN 
##==================================================





# ==================================================
# KPI SUPER ADMIN
# ==================================================

def calcular_ingresos_anuales():

    hoy = datetime.utcnow()

    inicio_anio = datetime(
        hoy.year,
        1,
        1
    )

    total = db.session.query(
        db.func.sum(Pago.monto)
    ).filter(
        Pago.estado == "pagado",
        Pago.fecha_pago >= inicio_anio
    ).scalar()

    return float(total or 0)



def calcular_mrr():

    total = db.session.query(
        db.func.sum(Pago.monto)
    ).filter(
        Pago.estado == "pagado"
    ).scalar()

    return float(total or 0)



def calcular_empresas_por_vencer():

    limite = datetime.utcnow() + timedelta(days=30)

    return Empresa.query.filter(
        Empresa.fecha_vencimiento <= limite,
        Empresa.fecha_vencimiento >= datetime.utcnow()
    ).count()



def calcular_usuarios_activos():

    return Usuario.query.filter_by(
        sesion_activa=True
    ).count()



def calcular_clientes_pagando():

    return Empresa.query.filter(
        Empresa.plan != "prueba"
    ).count()

# ==================================================
# EMPRESA VENCIDA
# ==================================================

def empresa_vencida(empresa):
    """
    Devuelve True si la empresa ya venció su fecha de expiración.
    """

    if not empresa:
        return False

    if not empresa.fecha_vencimiento:
        return False

    return empresa.fecha_vencimiento.date() < datetime.utcnow().date()

# ==================================================
# APROBAR CAMBIO DE PLAN
# ==================================================

@app.route("/super-admin/aprobar-cambio-plan/<int:solicitud_id>")
@login_requerido
def aprobar_cambio_plan(solicitud_id):

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual or usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    solicitud = SolicitudCambioPlan.query.get_or_404(
        solicitud_id
    )

    empresa = solicitud.empresa

    plan = PlanSaaS.query.filter(
    db.func.lower(PlanSaaS.nombre) ==
    solicitud.plan_solicitado.lower()
    ).first()

    if not plan:
        flash(
            "El plan solicitado no existe.",
            "danger"
            )
        return redirect(
            url_for("super_admin")
            )
    empresa.plan = (
    plan.nombre
    .strip()
    .lower()
    .replace("á", "a")
    .replace("é", "e")
    .replace("í", "i")
    .replace("ó", "o")
    .replace("ú", "u")
)
    empresa.limite_productos = plan.limite_productos
    empresa.limite_usuarios = plan.limite_usuarios
    empresa.limite_movimientos = plan.limite_movimientos
    empresa.almacenamiento_mb = plan.almacenamiento_mb

    empresa.limite_empresas = plan.limite_empresas
    empresa.limite_sucursales = plan.limite_sucursales

    solicitud.estado = "aprobada"

    solicitud.fecha_revision = datetime.utcnow()
    solicitud.revisado_por = current_user.id

    db.session.commit()

    flash(
        "Solicitud aprobada correctamente.",
        "success"
    )

    return redirect(
        url_for("super_admin")
    )

# ==================================================
# RECHAZAR CAMBIO DE PLAN
# ==================================================

@app.route("/super-admin/rechazar-cambio-plan/<int:solicitud_id>")
@login_requerido
def rechazar_cambio_plan(solicitud_id):

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual or usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    solicitud = SolicitudCambioPlan.query.get_or_404(
        solicitud_id
    )

    solicitud.estado = "rechazada"

    db.session.commit()

    flash(
        "Solicitud rechazada.",
        "success"
    )

    return redirect(
        url_for("super_admin")
    )



# ==================================================
# PANEL SUPER ADMIN
# ==================================================

@app.route("/super-admin")
@login_requerido
def super_admin():

    usuario_actual = obtener_usuario_actual()


    if not usuario_actual:

        return redirect(
            url_for("logout")
        )


    if usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )


    ahora = datetime.utcnow()



    # ==================================================
    # EMPRESAS
    # ==================================================

    total_empresas = Empresa.query.count()


    empresas_activas = Empresa.query.filter_by(
        estado="activo"
    ).count()


    empresas_suspendidas = Empresa.query.filter_by(
        estado="suspendido"
    ).count()
    


    empresas_prueba = Empresa.query.filter_by(
        plan="prueba"
    ).count()



    empresas_por_vencer = Empresa.query.filter(

        Empresa.fecha_vencimiento.isnot(None),

        Empresa.fecha_vencimiento >= ahora,

        Empresa.fecha_vencimiento <= (
            ahora + timedelta(days=30)
        )

    ).count()



    # ==================================================
    # USUARIOS
    # ==================================================

    total_usuarios = Usuario.query.count()

    usuarios_activos_hoy = Usuario.query.filter(

        Usuario.ultimo_acceso.isnot(None),

        Usuario.ultimo_acceso >= (
            ahora - timedelta(days=1)
        )

    ).count()

    usuarios_sesion_activa = Usuario.query.filter_by(
        sesion_activa=True
    ).count()

    administradores = Usuario.query.filter(

        Usuario.rol.in_(
            [
                "admin_empresa",
                "super_admin"
            ]
        )

    ).count()

    
    inicio_mes = datetime(
        ahora.year,
        ahora.month,
        1
    )



    nuevos_usuarios_mes = Usuario.query.filter(

        Usuario.created_at >= inicio_mes

    ).count()



    # ==================================================
    # FACTURACIÓN SaaS
    # ==================================================

    ingresos_mensuales = calcular_ingresos_mensuales()



    clientes_pagando = Empresa.query.filter(

        Empresa.estado=="activo",

        Empresa.plan!="prueba"

    ).count()



    clientes_gratis = Empresa.query.filter_by(

        plan="prueba"

    ).count()



    # MRR aproximado basado en pagos confirmados

    mrr = db.session.query(
        db.func.sum(Pago.monto)
    ).filter(

        Pago.estado=="pagado",

        Pago.fecha_pago >= inicio_mes

    ).scalar() or 0



    proximos_pagos = Empresa.query.filter(

        Empresa.fecha_vencimiento.isnot(None),

        Empresa.fecha_vencimiento >= ahora,

        Empresa.fecha_vencimiento <= (
            ahora + timedelta(days=30)
        )

    ).count()



    # ==================================================
    # PLANES
    # ==================================================

    plan_prueba = Empresa.query.filter_by(
        plan="prueba"
    ).count()


    plan_basico = Empresa.query.filter_by(
        plan="basico"
    ).count()


    plan_profesional = Empresa.query.filter_by(
        plan="profesional"
    ).count()


    plan_premium = Empresa.query.filter_by(
        plan="premium"
    ).count()



    # ==================================================
    # EMPRESAS DETALLE
    # ==================================================

    empresas_info = []


    empresas = Empresa.query.order_by(
        Empresa.nombre.asc()
    ).all()



    for empresa in empresas:


        cantidad_usuarios = Usuario.query.filter_by(
            empresa_id=empresa.id
        ).count()



        cantidad_productos = Producto.query.filter_by(
            empresa_id=empresa.id
        ).count()



        empresas_info.append({

            "empresa": empresa,

            "usuarios": cantidad_usuarios,

            "productos": cantidad_productos,

            "vencida": empresa_vencida(
                empresa
            )

        })

    # ==================================================
    # SOLICITUDES DE CAMBIO DE PLAN
    # ==================================================

    solicitudes_pendientes = (
        SolicitudCambioPlan.query
        .filter_by(estado="pendiente")
        .order_by(
            SolicitudCambioPlan.created_at.desc()
        )
        .all()
    )

    # ==================================================
    # RENDER
    # ==================================================

    return render_template(

        "super_admin.html",


        usuario_actual=usuario_actual,


        # EMPRESAS

        total_empresas=total_empresas,

        empresas_activas=empresas_activas,

        empresas_suspendidas=empresas_suspendidas,

        empresas_prueba=empresas_prueba,

        empresas_por_vencer=empresas_por_vencer,



        # USUARIOS

        total_usuarios=total_usuarios,

        usuarios_activos_hoy=usuarios_activos_hoy,

        usuarios_sesion_activa=usuarios_sesion_activa,

        administradores=administradores,

        nuevos_usuarios_mes=nuevos_usuarios_mes,



        # FACTURACIÓN

        ingresos_mensuales=ingresos_mensuales,

        mrr=mrr,

        clientes_pagando=clientes_pagando,

        clientes_gratis=clientes_gratis,

        proximos_pagos=proximos_pagos,



        # PLANES

        plan_prueba=plan_prueba,

        plan_basico=plan_basico,

        plan_profesional=plan_profesional,

        plan_premium=plan_premium,



        # EMPRESAS

empresas=empresas_info,

# SOLICITUDES

solicitudes_pendientes=solicitudes_pendientes

)

#=====================================
#SUPER_ADMIN_EMPRESAS
#=====================================
@app.route("/super-admin/empresas")
@login_requerido
def super_admin_empresas():

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(url_for("logout"))

    if usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    empresas = Empresa.query.order_by(
        Empresa.nombre.asc()
    ).all()

    empresas_info = []

    activas = 0
    suspendidas = 0
    prueba = 0
    por_vencer = 0

    hoy = datetime.now(UTC).date()

    for empresa in empresas:

        usuarios = Usuario.query.filter_by(
            empresa_id=empresa.id
        ).count()

        productos = Producto.query.filter_by(
            empresa_id=empresa.id
        ).count()

        vencida = empresa_vencida(
            empresa
        )

        if empresa.estado == "activo":
            activas += 1

        if empresa.estado == "suspendido":
            suspendidas += 1

        if empresa.plan.lower() == "prueba":
            prueba += 1

        if empresa.fecha_vencimiento:
            fecha_vencimiento = empresa.fecha_vencimiento.date()
            if (fecha_vencimiento >= hoy
                and
                (fecha_vencimiento - hoy).days <= 7):
                por_vencer += 1

        empresas_info.append({

            "empresa": empresa,

            "usuarios": usuarios,

            "productos": productos,

            "vencida": vencida

        })

        print("=" * 60)
        print(empresas)
        print(empresas_info)
        print("=" * 60)

    return render_template(

        "super_admin_empresas.html",

        usuario_actual=usuario_actual,

        empresas=empresas_info,

        total_empresas=len(empresas),

        empresas_activas=activas,

        empresas_suspendidas=suspendidas,

        empresas_prueba=prueba,

        empresas_por_vencer=por_vencer

    )

# ==================================================
# SUPER ADMIN - VER EMPRESA
# ==================================================

@app.route("/super-admin/empresas/<int:id>")
@login_requerido
def ver_empresa(id):

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(url_for("logout"))

    if usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    empresa = Empresa.query.get_or_404(id)

    total_usuarios = Usuario.query.filter_by(
        empresa_id=empresa.id
    ).count()

    total_productos = Producto.query.filter_by(
        empresa_id=empresa.id
    ).count()

    total_proveedores = Proveedor.query.filter_by(
        empresa_id=empresa.id
    ).count()

    total_movimientos = Movimiento.query.filter_by(
        empresa_id=empresa.id
    ).count()

    pagos = Pago.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Pago.fecha_pago.desc()
    ).limit(10).all()

    auditorias = Auditoria.query.filter_by(
        empresa_id=empresa.id
    ).order_by(
        Auditoria.fecha.desc()
    ).limit(10).all()

    return render_template(

        "ver_empresa.html",

        usuario_actual=usuario_actual,

        empresa=empresa,

        total_usuarios=total_usuarios,

        total_productos=total_productos,

        total_proveedores=total_proveedores,

        total_movimientos=total_movimientos,

        pagos=pagos,

        auditorias=auditorias

    )

# ==================================================
# SUPER ADMIN - EDITAR EMPRESA
# ==================================================

@app.route("/super-admin/empresa/<int:id>/editar",methods=["GET", "POST"])
@login_requerido
def super_admin_editar_empresa(id):

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:

        return redirect(
            url_for("logout")
        )

    if usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    empresa = Empresa.query.get_or_404(id)

    if request.method == "POST":

        empresa.nombre = request.form.get(
            "nombre"
        )

        empresa.email = request.form.get(
            "email"
        )

        empresa.telefono = request.form.get(
            "telefono"
        )

        empresa.direccion = request.form.get(
            "direccion"
        )

        empresa.ciudad = request.form.get(
            "ciudad"
        )

        empresa.pais = request.form.get(
            "pais"
        )

        empresa.plan = request.form.get(
            "plan"
        )

        empresa.estado = request.form.get(
            "estado"
        )

        fecha = request.form.get(
            "fecha_vencimiento"
        )

        if fecha:

            empresa.fecha_vencimiento = datetime.strptime(
                fecha,
                "%Y-%m-%d"
            )

        Auditoria.crear(

            accion="Editar empresa",

            empresa_id=empresa.id,

            usuario_id=usuario_actual.id,

            modulo="Empresas",

            descripcion=f"Se editó la empresa {empresa.nombre}"

        )

        db.session.commit()

        flash(

            "Empresa actualizada correctamente.",

            "success"

        )

        return redirect(

            url_for(
                "super_admin_empresas"
            )

        )

    return render_template(

        "editar_empresa.html",

        usuario_actual=usuario_actual,

        empresa=empresa,

        planes=PlanSaaS.query.filter_by(
            activo=True
        ).order_by(
            PlanSaaS.orden
        ).all()

    )

#=======================================================================
# SUPER ADMIN EMPRESA SUSPENDER
#=======================================================================

@app.route("/super-admin/empresa/<int:id>/suspender",methods=["POST"])
@login_requerido
def super_admin_suspender_empresa(id):

    if not es_super_admin():
        flash(
            "Acceso denegado.",
            "danger"
        )
        return redirect(url_for("dashboard"))

    empresa = Empresa.query.get_or_404(id)

    empresa.suspender(
        motivo="Suspendida por Super Admin"
    )

    registrar_auditoria(
        accion="Suspender empresa",
        modulo="Empresas",
        descripcion=f"Empresa '{empresa.nombre}' suspendida.",
        empresa=empresa
    )

    db.session.commit()

    flash(
        "Empresa suspendida correctamente.",
        "warning"
    )

    return redirect(
        url_for("super_admin_empresas")
    )

#=======================================================================
# SUPER ADMIN EMPRESA ELIMINAR
#=======================================================================

@app.route("/super-admin/empresa/<int:id>/eliminar",methods=["POST"])
@login_requerido
def super_admin_eliminar_empresa(id):

    if not es_super_admin():
        flash(
            "Acceso denegado.",
            "danger"
        )
        return redirect(url_for("dashboard"))

    empresa = Empresa.query.get_or_404(id)

    empresa.estado = "cancelado"
    empresa.activo = False
    empresa.bloqueada = True
    empresa.motivo_bloqueo = "Empresa desactivada por Super Admin"

    registrar_auditoria(
        accion="Desactivar empresa",
        modulo="Empresas",
        descripcion=f"Empresa '{empresa.nombre}' desactivada.",
        empresa=empresa
    )

    db.session.commit()

    flash(
        "Empresa desactivada correctamente.",
        "success"
    )

    return redirect(
        url_for("super_admin_empresas")
    )

# ==================================================
# SUPER ADMIN - NUEVA EMPRESA
# ==================================================

@app.route("/super-admin/empresa/nueva",methods=["GET", "POST"])
@login_requerido
def super_admin_nueva_empresa():

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:

        return redirect(
            url_for("logout")
        )

    if usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    planes = PlanSaaS.query.filter_by(
        activo=True
    ).order_by(
        PlanSaaS.orden
    ).all()

    if request.method == "POST":

        nombre = request.form.get(
            "nombre",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        telefono = request.form.get(
            "telefono",
            ""
        ).strip()

        direccion = request.form.get(
            "direccion",
            ""
        ).strip()

        ciudad = request.form.get(
            "ciudad",
            ""
        ).strip()

        pais = request.form.get(
            "pais",
            ""
        ).strip()

        plan = request.form.get(
            "plan",
            "prueba"
        )

        estado = request.form.get(
            "estado",
            "activo"
        )

        fecha = request.form.get(
            "fecha_vencimiento"
        )

        if not nombre:

            flash(
                "Debe ingresar el nombre de la empresa.",
                "warning"
            )

            return redirect(
                url_for(
                    "super_admin_nueva_empresa"
                )
            )

        empresa_existente = Empresa.query.filter_by(
            nombre=nombre
        ).first()

        if empresa_existente:

            flash(
                "Ya existe una empresa con ese nombre.",
                "warning"
            )

            return redirect(
                url_for(
                    "super_admin_nueva_empresa"
                )
            )

        empresa = Empresa(

            nombre=nombre,

            email=email,

            telefono=telefono,

            direccion=direccion,

            ciudad=ciudad,

            pais=pais,

            plan=plan,

            estado=estado

        )

        if fecha:

            empresa.fecha_vencimiento = datetime.strptime(
                fecha,
                "%Y-%m-%d"
            )

        db.session.add(
            empresa
        )

        db.session.commit()

        Auditoria.crear(

            accion="Crear empresa",

            empresa_id=empresa.id,

            usuario_id=usuario_actual.id,

            modulo="Empresas",

            descripcion=f"Se creó la empresa {empresa.nombre}"

        )

        flash(
            "Empresa creada correctamente.",
            "success"
        )

        return redirect(
            url_for(
                "super_admin_empresas"
            )
        )

    return render_template(

        "nueva_empresa.html",

        usuario_actual=usuario_actual,

        planes=planes

    )


# ==================================================
# SUPER ADMIN - PAGOS
# ==================================================

@app.route("/super-admin/pagos")
@login_requerido
def super_admin_pagos():

    usuario_actual = obtener_usuario_actual()


    if not usuario_actual:

        return redirect(
            url_for("logout")
        )


    if usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )


    # ==================================================
    # TABLA PAGOS
    # ==================================================

    pagos = Pago.query.order_by(
        Pago.fecha_pago.desc()
    ).limit(500).all()



    # ==================================================
    # KPI FINANCIEROS
    # ==================================================

    total_pagos = Pago.query.count()



    # ==================================================
    # INGRESOS HISTÓRICOS
    # ==================================================

    ingresos = db.session.query(
        db.func.sum(
            Pago.monto
        )
    ).filter(
        Pago.estado == "pagado"
    ).scalar() or 0



    # ==================================================
    # INGRESOS ÚLTIMOS 12 MESES
    # ==================================================

    fecha_inicio_anual = datetime.utcnow() - timedelta(
        days=365
    )


    ingresos_anuales = db.session.query(
        db.func.sum(
            Pago.monto
        )
    ).filter(

        Pago.estado == "pagado",

        Pago.fecha_pago >= fecha_inicio_anual

    ).scalar() or 0



    # ==================================================
    # INGRESOS MES ACTUAL
    # ==================================================

    fecha_inicio_mes = datetime.utcnow().replace(

        day=1,

        hour=0,

        minute=0,

        second=0,

        microsecond=0

    )


    ingresos_mensuales = db.session.query(
        db.func.sum(
            Pago.monto
        )
    ).filter(

        Pago.estado == "pagado",

        Pago.fecha_pago >= fecha_inicio_mes

    ).scalar() or 0



    # ==================================================
    # MRR SaaS
    # ==================================================

    mrr = db.session.query(
        db.func.sum(
            PlanSaaS.precio_mensual
        )
    ).join(

        Empresa,

        db.func.lower(Empresa.plan)
        ==
        db.func.lower(PlanSaaS.nombre)

    ).filter(

        Empresa.estado == "activo",

        PlanSaaS.activo == True

    ).scalar() or 0



    # ==================================================
    # EMPRESAS MOROSAS
    # ==================================================

    hoy = datetime.now(UTC).date()


    empresas_morosas = Empresa.query.filter(

        Empresa.fecha_vencimiento < hoy,

        Empresa.estado == "activo"

    ).count()



    return render_template(

        "super_admin_pagos.html",

        usuario_actual=usuario_actual,


        # Tabla

        pagos=pagos,


        # KPI

        total_pagos=total_pagos,

        ingresos=ingresos,

        ingresos_mensuales=ingresos_mensuales,

        ingresos_anuales=ingresos_anuales,

        mrr=mrr,

        empresas_morosas=empresas_morosas

    )

# ==================================================
# SUPER ADMIN - CREAR PAGO
# ==================================================

@app.route("/super-admin/pagos/nuevo",methods=["GET", "POST"])
@login_requerido
def crear_pago():

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:

        return redirect(
            url_for("logout")
        )

    if usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    empresas = Empresa.query.order_by(
        Empresa.nombre.asc()
    ).all()

    if request.method == "POST":

        empresa_id = request.form.get("empresa_id")

        monto = request.form.get(
            "monto",
            type=float
        )

        estado = request.form.get(
            "estado"
        )

        metodo_pago = request.form.get(
            "metodo_pago"
        )

        observaciones = request.form.get(
            "observaciones"
        )

        empresa = db.session.get(
            Empresa,
            empresa_id
        )

        if not empresa:

            flash(
                "Empresa no encontrada.",
                "danger"
            )

            return redirect(
                request.url
            )

        nuevo_pago = Pago(

            empresa_id=empresa.id,

            monto=monto,

            estado=estado,

            metodo_pago=metodo_pago,

            observaciones=observaciones,

            fecha_pago=datetime.utcnow()

        )

        db.session.add(
            nuevo_pago
        )

        db.session.commit()

        Auditoria.crear(

            accion="Crear pago",

            empresa_id=empresa.id,

            usuario_id=usuario_actual.id,

            modulo="Pagos",

            descripcion=f"Se registró un pago de ${monto:,.0f}"

        )

        db.session.add(

            Auditoria.crear(

                accion="Crear pago",

                empresa_id=empresa.id,

                usuario_id=usuario_actual.id,

                modulo="Pagos",

                descripcion=f"Se registró un pago de ${monto:,.0f}"

            )

        )

        db.session.commit()

        flash(
            "Pago registrado correctamente.",
            "success"
        )

        return redirect(
            url_for(
                "super_admin_pagos"
            )
        )

    return render_template(

        "crear_pago.html",

        usuario_actual=usuario_actual,

        empresas=empresas

    )

# ==================================================
# SUPER ADMIN - VER PAGO
# ==================================================

@app.route("/super-admin/pagos/<int:id>")
@login_requerido
def ver_pago(id):

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(url_for("logout"))

    if usuario_actual.rol != "super_admin":
        flash("Acceso denegado.", "danger")
        return redirect(url_for("dashboard"))

    pago = Pago.query.get_or_404(id)

    return render_template(
        "ver_pago.html",
        usuario_actual=usuario_actual,
        pago=pago
    )

# ==================================================
# SUPER ADMIN - EDITAR PAGO
# ==================================================

@app.route("/super-admin/pagos/<int:id>/editar",methods=["GET", "POST"])
@login_requerido
def editar_pago(id):

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(url_for("logout"))

    if usuario_actual.rol != "super_admin":
        flash("Acceso denegado.", "danger")
        return redirect(url_for("dashboard"))

    pago = Pago.query.get_or_404(id)

    if request.method == "POST":

        pago.estado = request.form.get("estado")

        pago.metodo_pago = request.form.get(
            "metodo_pago"
        )

        pago.observaciones = request.form.get(
            "observaciones"
        )

        try:

            pago.monto = float(
                request.form.get("monto", 0)
            )

        except ValueError:

            flash(
                "Monto inválido.",
                "danger"
            )

            return redirect(
                url_for(
                    "editar_pago",
                    id=id
                )
            )

        db.session.commit()

        registrar_auditoria(

            accion="EDITAR_PAGO",

            empresa_id=pago.empresa_id,

            usuario_id=usuario_actual.id,

            modulo="PAGOS",

            descripcion=f"Se editó el pago #{pago.id}"

        )

        flash(
            "Pago actualizado correctamente.",
            "success"
        )

        return redirect(
            url_for("super_admin_pagos")
        )

    return render_template(

        "editar_pago.html",

        usuario_actual=usuario_actual,

        pago=pago

    )

# ==================================================
# SUPER ADMIN - ELIMINAR PAGO
# ==================================================

@app.route("/super-admin/pagos/<int:id>/eliminar",methods=["POST"])
@login_requerido
def eliminar_pago(id):

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(url_for("logout"))

    if usuario_actual.rol != "super_admin":
        flash("Acceso denegado.", "danger")
        return redirect(url_for("dashboard"))

    pago = Pago.query.get_or_404(id)

    registrar_auditoria(

        accion="ELIMINAR_PAGO",

        empresa_id=pago.empresa_id,

        usuario_id=usuario_actual.id,

        modulo="PAGOS",

        descripcion=f"Se eliminó el pago #{pago.id}"

    )

    db.session.delete(pago)

    db.session.commit()

    flash(
        "Pago eliminado correctamente.",
        "success"
    )

    return redirect(
        url_for("super_admin_pagos")
    )


# ==================================================
# SUPER ADMIN - PLANES
# ==================================================

@app.route("/super-admin/planes")
@login_requerido
def super_admin_planes():

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:

        return redirect(
            url_for("logout")
        )

    if usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

# ==================================================
# PLANES SAAS
# ==================================================

    planes = PlanSaaS.query.order_by(
        PlanSaaS.orden.asc()
    ).all()

    # ==================================================
    # TOTAL EMPRESAS
    # ==================================================

    total_empresas = Empresa.query.count()

    empresas_por_plan = []

    ingresos_por_plan = []

    ingresos_totales_estimados = 0

    clientes_pagando = 0

    clientes_gratis = 0

    for plan in planes:

        cantidad_empresas = Empresa.query.filter(

            db.func.lower(Empresa.plan)
            ==
            db.func.lower(plan.nombre)

        ).count()

        porcentaje = 0

        if total_empresas > 0:

            porcentaje = round(

                (
                    cantidad_empresas
                    /
                    total_empresas
                )
                *
                100,

                2

            )

        ingresos_estimados = (

            cantidad_empresas
            *
            float(plan.precio_mensual)

        )

        ingresos_totales_estimados += ingresos_estimados

        if float(plan.precio_mensual) > 0:

            clientes_pagando += cantidad_empresas

        else:

            clientes_gratis += cantidad_empresas

        empresas_por_plan.append({

            "plan": plan.nombre,

            "cantidad": cantidad_empresas,

            "porcentaje": porcentaje

        })

        ingresos_por_plan.append({

            "plan": plan.nombre,

            "ingresos": ingresos_estimados

        })

# ==================================================
# CRECIMIENTO EMPRESAS
# ==================================================

    hoy = datetime.utcnow()

    inicio_mes_actual = hoy.replace(

        day=1,

        hour=0,

        minute=0,

        second=0,

        microsecond=0

    )

    empresas_nuevas_mes = Empresa.query.filter(

        Empresa.created_at >= inicio_mes_actual

    ).count()

    if inicio_mes_actual.month == 1:

        inicio_mes_anterior = inicio_mes_actual.replace(

            year=inicio_mes_actual.year - 1,

            month=12

        )

    else:

        inicio_mes_anterior = inicio_mes_actual.replace(

            month=inicio_mes_actual.month - 1

        )

    empresas_mes_anterior = Empresa.query.filter(

        Empresa.created_at >= inicio_mes_anterior,

        Empresa.created_at < inicio_mes_actual

    ).count()

    crecimiento = 0

    if empresas_mes_anterior > 0:

        crecimiento = round(

            (
                (
                    empresas_nuevas_mes
                    -
                    empresas_mes_anterior
                )
                /
                empresas_mes_anterior
            )
            *
            100,

            2

        )


# ==================================================
# PLANES ACTIVOS
# ==================================================

    planes_activos = PlanSaaS.query.filter_by(
        activo=True
    ).count()

# ==================================================
# RENDER
# ==================================================

    return render_template(

        "super_admin_planes.html",

        usuario_actual=usuario_actual,

        planes=planes,

        total_empresas=total_empresas,

        empresas_por_plan=empresas_por_plan,

        ingresos_por_plan=ingresos_por_plan,

        ingresos_totales_estimados=ingresos_totales_estimados,

        clientes_pagando=clientes_pagando,

        clientes_gratis=clientes_gratis,

        empresas_nuevas_mes=empresas_nuevas_mes,

        crecimiento=crecimiento,

        planes_activos=planes_activos

    )


# ==================================================
# SUPER ADMIN - AUDITORIA
# ==================================================

@app.route("/super-admin/auditoria")
@login_requerido
def super_admin_auditoria():

    usuario_actual = obtener_usuario_actual()


    if not usuario_actual:

        return redirect(
            url_for("logout")
        )


    if usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )


# ==================================================
# LISTADO DE AUDITORIAS
# ==================================================

    auditorias = Auditoria.query.order_by(
    Auditoria.fecha.desc()
    ).limit(500).all()


# ==================================================
# ESTADISTICAS SUPER ADMIN
# ==================================================

    total_eventos = Auditoria.query.count()


    total_empresas = Empresa.query.count()


    total_usuarios = Usuario.query.count()


    eventos_hoy = Auditoria.query.filter(
        db.func.date(
            Auditoria.created_at
        ) == db.func.current_date()
    ).count()


    return render_template(

        "super_admin_auditoria.html",

        usuario_actual=usuario_actual,

        auditorias=auditorias,

        total_eventos=total_eventos,

        total_empresas=total_empresas,

        total_usuarios=total_usuarios,

        eventos_hoy=eventos_hoy

    )

# ==================================================
# SUPER ADMIN - VER AUDITORÍA
# ==================================================

@app.route("/super-admin/auditoria/<int:id>")
@login_requerido
def ver_auditoria(id):

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(url_for("logout"))

    if usuario_actual.rol != "super_admin":
        flash(
            "Acceso denegado.",
            "danger"
        )
        return redirect(
            url_for("dashboard")
        )

    auditoria = Auditoria.query.get_or_404(id)

    return render_template(
        "ver_auditoria.html",
        usuario_actual=usuario_actual,
        auditoria=auditoria
    )

# ==================================================
# SUPER ADMIN - EDITAR PLAN
# ==================================================

@app.route("/super-admin/planes/<int:id>/editar",methods=["GET", "POST"])
@login_requerido
def editar_plan(id):

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:

        return redirect(
            url_for("logout")
        )

    if usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    plan = PlanSaaS.query.get_or_404(id)

    if request.method == "POST":

        plan.precio_mensual = float(
            request.form.get(
                "precio_mensual",
                plan.precio_mensual
            ) or 0
        )

        plan.precio_anual = float(
            request.form.get(
                "precio_anual",
                plan.precio_anual
            ) or 0
        )

        plan.limite_usuarios = int(
            request.form.get(
                "limite_usuarios",
                plan.limite_usuarios
            ) or 0
        )

        plan.limite_productos = int(
            request.form.get(
                "limite_productos",
                plan.limite_productos
            ) or 0
        )

        plan.limite_movimientos = int(
            request.form.get(
                "limite_movimientos",
                plan.limite_movimientos
            ) or 0
        )

        plan.limite_sucursales = int(
            request.form.get(
                "limite_sucursales",
                plan.limite_sucursales
            ) or 0
        )

        plan.activo = (
            request.form.get("activo") == "on"
        )

        db.session.commit()

        registrar_auditoria(

    accion="EDITAR",

    modulo="Planes SaaS",

    descripcion=f"Se modificó el plan {plan.nombre}",

    usuario=usuario_actual,

    datos_nuevos={

        "precio_mensual": float(plan.precio_mensual),

        "precio_anual": float(plan.precio_anual),

        "usuarios": plan.limite_usuarios,

        "productos": plan.limite_productos,

        "movimientos": plan.limite_movimientos,

        "sucursales": plan.limite_sucursales
        })

        flash(
            "Plan actualizado correctamente.",
            "success"
        )

        return redirect(
            url_for("super_admin_planes")
        )

    return render_template(
        "editar_plan.html",
        usuario_actual=usuario_actual,
        plan=plan
    )

# ==================================================
# SUPER ADMIN - USUARIOS GLOBALES
# ==================================================

@app.route("/super-admin/usuarios")
@login_requerido
def super_admin_usuarios():

    usuario_actual = obtener_usuario_actual()


    if not usuario_actual or usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )



    usuarios = Usuario.query.order_by(
        Usuario.id.desc()
    ).all()



    return render_template(

    "super_admin_usuarios.html",

    usuarios=usuarios,

    usuario_actual=usuario_actual
    )

# ==================================================
# SUPER ADMIN - EDITAR USUARIO
# ==================================================

@app.route("/super-admin/usuario/editar/<int:id>",methods=["GET","POST"])
@login_requerido
def super_admin_editar_usuario(id):


    usuario_actual = obtener_usuario_actual()


    if not usuario_actual or usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )



    usuario = Usuario.query.get_or_404(id)



    if request.method == "POST":


        usuario.nombre = request.form.get(
            "nombre"
        )


        usuario.email = request.form.get(
            "email"
        )


        nuevo_rol = request.form.get(
            "rol"
        )


        # evitar quitar permisos al super admin principal

        if usuario.rol != "super_admin":

            usuario.rol = nuevo_rol



        db.session.commit()



        flash(
            "Usuario actualizado correctamente.",
            "success"
        )


        return redirect(
            url_for("super_admin_usuarios")
        )



    return render_template(

        "editar_usuario.html",

        usuario=usuario

    )

# ==================================================
# SUPER ADMIN - ELIMINAR USUARIO
# ==================================================

@app.route("/super-admin/usuario/eliminar/<int:id>",methods=["POST"])
@login_requerido
def eliminar_usuario(id):


    usuario_actual = obtener_usuario_actual()


    if not usuario_actual or usuario_actual.rol != "super_admin":

        flash(
            "Acceso denegado.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )



    usuario = Usuario.query.get_or_404(id)



    if usuario.rol == "super_admin":

        flash(
            "No puedes eliminar un Super Administrador.",
            "danger"
        )

        return redirect(
            url_for("super_admin_usuarios")
        )



    db.session.delete(usuario)

    db.session.commit()



    flash(
        "Usuario eliminado correctamente.",
        "success"
    )


    return redirect(
        url_for("super_admin_usuarios")
    )




#===================================================
# NEXUSTOCK PARA CLIENTES
#===================================================
#===================================================





# ==================================================
# INTELIGENCIA DE INVENTARIO
# ==================================================

@app.route("/inteligencia-inventario")
@login_requerido
def inteligencia_inventario():


    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:

        session.clear()

        flash(
            "Sesión inválida.",
            "danger"
        )

        return redirect(
            url_for("login")
        )

    empresa_actual = obtener_empresa_actual_obj()



    if not empresa_actual:

        flash(
            "Empresa no encontrada.",
            "danger"
        )

        return redirect(
            url_for("logout")
        )

    productos = Producto.query.filter_by(
        empresa_id=empresa_actual.id
    ).all()


    alertas = []

    stock_bajo = 0

    sobre_stock = 0

    valor_inventario = 0



    for producto in productos:



        valor_inventario += (producto.stock *producto.precio)

# ------------------------------
# STOCK BAJO
# ------------------------------

        if producto.stock <= producto.stock_minimo:


            stock_bajo += 1


            alerta = AlertaInventario(

                empresa_id=empresa_actual.id,

                producto_id=producto.id,

                tipo="stock_bajo",

                mensaje=f"Comprar aproximadamente {producto.stock_minimo * 2} unidades de {producto.nombre}",

                prioridad="alta"

            )


            alerta.producto = producto


            alertas.append(alerta)

# ------------------------------
# SOBRE STOCK
# ------------------------------

        elif producto.stock > producto.stock_minimo * 3:



            sobre_stock += 1


            exceso = (
                producto.stock -
                (producto.stock_minimo * 3)
            )


            alerta = AlertaInventario(

                empresa_id=empresa_actual.id,

                producto_id=producto.id,

                tipo="sobre_stock",

                mensaje=f"Exceso de {exceso} unidades. Reducir nuevas compras.",

                prioridad="media"

            )


            alerta.producto = producto


            alertas.append(alerta)


    alertas_criticas = sum(

        1 for a in alertas

        if a.prioridad == "alta"

    )


    return render_template(

        "inteligencia_inventario.html",

        usuario_actual=usuario_actual,

        empresa_actual=empresa_actual,

        alertas=alertas,

        alertas_criticas=alertas_criticas,

        stock_bajo=stock_bajo,

        sobre_stock=sobre_stock,

        valor_inventario=valor_inventario

    )


# ==================================================
# ENTRADA DE STOCK
# ==================================================

@app.route("/movimientos/entrada", methods=["GET", "POST"])
@login_requerido
def entrada_stock():

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:

        session.clear()

        flash(
            "Sesión inválida.",
            "danger"
        )

        return redirect(
            url_for("login")
        )


    empresa_actual = obtener_empresa_actual_obj()

    if not empresa_actual:

        flash(
            "Empresa no encontrada.",
            "danger"
        )

        return redirect(
            url_for("logout")
        )


    productos = Producto.query.filter_by(
        empresa_id=empresa_actual.id
    ).order_by(
        Producto.nombre.asc()
    ).all()


    producto_preseleccionado = (
        request.args.get("producto_id")
        or request.args.get("producto")
    )


    if request.method == "POST":

        try:

            producto_id = int(
                request.form.get(
                    "producto_id",
                    0
                )
                or 0
            )


            cajas = int(
                request.form.get(
                    "cajas",
                    0
                )
                or 0
            )


            cantidad = int(
                request.form.get(
                    "cantidad",
                    0
                )
                or 0
            )


            producto = Producto.query.filter_by(
                id=producto_id,
                empresa_id=empresa_actual.id
            ).first()


            if not producto:

                flash(
                    "Producto no encontrado.",
                    "danger"
                )

                return redirect(
                    url_for("entrada_stock")
                )


            unidades_caja = int(
                producto.unidades_por_caja or 1
            )


            total_unidades = (
                cajas * unidades_caja
            ) + cantidad


            if total_unidades <= 0:

                flash(
                    "Debe ingresar una cantidad válida.",
                    "warning"
                )

                return redirect(
                    url_for("entrada_stock")
                )


            # ==========================================
            # ACTUALIZAR COSTO PROMEDIO
            # ==========================================

            stock_anterior = int(
                producto.stock or 0
            )


            costo_anterior = float(
                producto.costo_promedio or 0
            )


            costo_nuevo = float(
                producto.costo_compra or 0
            )


            nuevo_stock = (
                stock_anterior +
                total_unidades
            )


            if nuevo_stock > 0:

                producto.costo_promedio = (

                    (
                        stock_anterior *
                        costo_anterior
                    )
                    +
                    (
                        total_unidades *
                        costo_nuevo
                    )

                ) / nuevo_stock



            producto.stock = nuevo_stock


            producto.ultima_reposicion = datetime.utcnow()


            producto.calcular_valor_inventario()

            producto.calcular_margen()


            # ==========================================
            # MOVIMIENTO
            # ==========================================

            movimiento = Movimiento(

                empresa_id=empresa_actual.id,

                producto_id=producto.id,

                usuario_id=usuario_actual.id,

                tipo="entrada",

                cantidad=total_unidades,

                stock_anterior=stock_anterior,

                stock_nuevo=producto.stock,

                costo_unitario=producto.costo_promedio,

                costo_total=(

                    total_unidades *
                    float(producto.costo_promedio or 0)

                ),

                referencia_tipo="manual",

                referencia_id=producto.id,

                referencia="Entrada de Stock",

                ip_usuario=request.remote_addr,

                user_agent=request.headers.get(
                    "User-Agent"
                ),

                observacion=(

                    f"Entrada registrada por "
                    f"{usuario_actual.nombre}. "
                    f"Cajas: {cajas}. "
                    f"Unidades adicionales: {cantidad}. "
                    f"Total ingresado: {total_unidades}."

                )

            )


            db.session.add(
                movimiento
            )


            # ==========================================
            # AUDITORÍA
            # ==========================================

            auditoria = Auditoria.crear(

                accion="entrada_stock",

                modulo="inventario",

                descripcion=(

                    f"{usuario_actual.nombre} "
                    f"registró entrada de "
                    f"{total_unidades} unidades "
                    f"de {producto.nombre}."

                ),

                empresa_id=empresa_actual.id,

                usuario_id=usuario_actual.id

            )


            db.session.add(
                auditoria
            )


            db.session.commit()


            flash(
                "Entrada registrada correctamente.",
                "success"
            )


            return redirect(
                url_for("movimientos")
            )


        except Exception:

            db.session.rollback()


            logger.exception(
                "Error registrando entrada de stock."
            )


            flash(
                "Error al registrar entrada.",
                "danger"
            )


            return redirect(
                url_for("entrada_stock")
            )


    return render_template(

        "entrada_stock.html",

        productos=productos,

        producto_preseleccionado=producto_preseleccionado,

        usuario_actual=usuario_actual,

        empresa_actual=empresa_actual

    )


# ==================================================
# SALIDA DE STOCK
# ==================================================

@app.route("/movimientos/salida", methods=["GET", "POST"])
@login_requerido
def salida_stock():

    usuario_actual = obtener_usuario_actual()


    if not usuario_actual:

        session.clear()

        flash(
            "Sesión inválida.",
            "danger"
        )

        return redirect(
            url_for("login")
        )



    empresa_actual = obtener_empresa_actual_obj()


    if not empresa_actual:

        flash(
            "Empresa no encontrada.",
            "danger"
        )

        return redirect(
            url_for("logout")
        )



    productos = Producto.query.filter_by(

        empresa_id=empresa_actual.id

    ).order_by(

        Producto.nombre.asc()

    ).all()



    producto_preseleccionado = (

        request.args.get("producto_id")

        or

        request.args.get("producto")

    )



    if request.method == "POST":


        try:


            producto_id = int(

                request.form.get(

                    "producto_id",

                    0

                )

                or 0

            )



            cajas = int(

                request.form.get(

                    "cajas",

                    0

                )

                or 0

            )



            cantidad = int(

                request.form.get(

                    "cantidad",

                    0

                )

                or 0

            )




            producto = Producto.query.filter_by(

                id=producto_id,

                empresa_id=empresa_actual.id

            ).first()




            if not producto:


                flash(

                    "Producto no encontrado.",

                    "danger"

                )


                return redirect(

                    url_for("salida_stock")

                )





            unidades_por_caja = int(

                producto.unidades_por_caja or 1

            )




            total_unidades = (

                cajas * unidades_por_caja

            ) + cantidad





            if total_unidades <= 0:


                flash(

                    "Debe ingresar una cantidad válida.",

                    "warning"

                )


                return redirect(

                    url_for("salida_stock")

                )





            if total_unidades > producto.stock:


                flash(

                    "Stock insuficiente.",

                    "danger"

                )


                return redirect(

                    url_for("salida_stock")

                )






            # ==========================================
            # ACTUALIZAR STOCK
            # ==========================================


            stock_anterior = int(

                producto.stock or 0

            )



            producto.stock = (

                stock_anterior -

                total_unidades

            )






            # ==========================================
            # ACTUALIZAR INDICADORES
            # ==========================================


            producto.calcular_valor_inventario()


            producto.calcular_margen()





            # ==========================================
            # MOVIMIENTO
            # ==========================================


            movimiento = Movimiento(


                empresa_id=empresa_actual.id,


                producto_id=producto.id,


                usuario_id=usuario_actual.id,


                tipo="salida",


                cantidad=total_unidades,


                stock_anterior=stock_anterior,


                stock_nuevo=producto.stock,


                costo_unitario=(

                    producto.costo_promedio or 0

                ),



                costo_total=(

                    total_unidades *

                    (producto.costo_promedio or 0)

                ),



                referencia_tipo="manual",


                referencia_id=producto.id,


                referencia="Salida de Stock",



                ip_usuario=request.remote_addr,



                user_agent=request.headers.get(

                    "User-Agent"

                ),




                observacion=(


                    f"Salida registrada por "

                    f"{usuario_actual.nombre}. "

                    f"Cajas: {cajas}. "

                    f"Unidades adicionales: {cantidad}. "

                    f"Total retirado: {total_unidades}."

                )

            )




            db.session.add(

                movimiento

            )






            # ==========================================
            # AUDITORÍA
            # ==========================================


            auditoria = Auditoria.crear(


                accion="salida_stock",


                modulo="inventario",



                descripcion=(


                    f"{usuario_actual.nombre} "

                    f"registró una salida de "

                    f"{total_unidades} unidades "

                    f"del producto "

                    f"{producto.nombre}."

                ),



                empresa_id=empresa_actual.id,


                usuario_id=usuario_actual.id


            )




            db.session.add(

                auditoria

            )





            db.session.commit()





            flash(

                "Salida registrada correctamente.",

                "success"

            )





            return redirect(

                url_for("movimientos")

            )





        except Exception:


            db.session.rollback()



            logger.exception(

                "Error registrando salida de stock."

            )



            flash(

                "Error al registrar la salida.",

                "danger"

            )



            return redirect(

                url_for("salida_stock")

            )






    return render_template(


        "salida_stock.html",



        productos=productos,



        producto_preseleccionado=producto_preseleccionado,



        usuario_actual=usuario_actual,



        empresa_actual=empresa_actual


    )

# ==================================================
# REPORTES
# ==================================================

@app.route("/reportes")
@login_requerido
def reportes():

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:

        return redirect(
            url_for("logout")
        )

    empresa_actual = obtener_empresa_actual_obj()

    if not empresa_actual:

        flash(
            "Empresa no encontrada.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

# ======================================
# PRODUCTOS
# ======================================

    total_productos = Producto.query.filter_by(
        empresa_id=empresa_actual.id
    ).count()

    cantidad_stock_bajo = Producto.query.filter(

        Producto.empresa_id == empresa_actual.id,

        Producto.stock <= Producto.stock_minimo

    ).count()

    valor_inventario = db.session.query(

        db.func.sum(
            Producto.stock * Producto.costo_promedio
        )

    ).filter(

        Producto.empresa_id == empresa_actual.id

    ).scalar() or 0

    unidades_totales = db.session.query(

        db.func.sum(
            Producto.stock
        )

    ).filter(

        Producto.empresa_id == empresa_actual.id

    ).scalar() or 0

# ======================================
# ÚLTIMOS MOVIMIENTOS
# ======================================

    movimientos = Movimiento.query.filter_by(

        empresa_id=empresa_actual.id

    ).order_by(

        Movimiento.fecha.desc()

    ).limit(20).all()

    # ======================================
    # PRODUCTOS MÁS VENDIDOS
    # ======================================

    productos_mas_vendidos = db.session.query(

        Producto.nombre.label("nombre"),

        db.func.sum(
            Movimiento.cantidad
        ).label("salidas")

    ).join(

        Movimiento,
        Movimiento.producto_id == Producto.id

    ).filter(

        Producto.empresa_id == empresa_actual.id,

        Movimiento.tipo == "salida"

    ).group_by(

        Producto.id,
        Producto.nombre

    ).order_by(

        db.func.sum(
            Movimiento.cantidad
        ).desc()
        ).limit(10).all()

    return render_template("reportes.html",

        usuario_actual=usuario_actual,

        empresa_actual=empresa_actual,

        total_productos=total_productos,

        cantidad_stock_bajo=cantidad_stock_bajo,

        valor_inventario=valor_inventario,

        unidades_totales=unidades_totales,

        movimientos=movimientos,

        productos_mas_vendidos=productos_mas_vendidos

    )

# ==================================================
# ESCANER QR / CODIGO DE BARRAS
# ==================================================

@app.route("/escaner")
@login_requerido
def escaner():

    usuario_actual = obtener_usuario_actual()


    if not usuario_actual:

        return redirect(
            url_for("login")
        )


    return render_template("escaner.html",
        usuario_actual=usuario_actual
    )


# ==================================================
# PRODUCTOS
# ==================================================

@app.route("/productos")
@login_requerido
def productos():

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:

        return redirect(
            url_for("logout")
        )

    empresa_actual = obtener_empresa_actual_obj()

    if not empresa_actual:

        flash(
            "Empresa no encontrada.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

    busqueda = request.args.get(
        "buscar",
        ""
    ).strip()

    consulta = Producto.query.filter_by(
        empresa_id=empresa_actual.id
    )

    if busqueda:

        consulta = consulta.filter(

            db.or_(

                Producto.nombre.ilike(
                    f"%{busqueda}%"
                ),

                Producto.codigo.ilike(
                    f"%{busqueda}%"
                ),

                Producto.categoria.ilike(
                    f"%{busqueda}%"
                ),

                Producto.marca.ilike(
                    f"%{busqueda}%"
                )

            )

        )

    productos = consulta.order_by(
        Producto.nombre.asc()
    ).all()

    return render_template("productos.html",

    usuario_actual=usuario_actual,
    empresa_actual=empresa_actual,
    productos=productos,
    busqueda=busqueda
    )


@app.route("/productos-sobre-stock")
@login_requerido
def productos_sobre_stock():

    productos = Producto.query.filter(
        Producto.stock > Producto.stock_maximo,
        Producto.stock_maximo > 0
    ).all()


    unidades_exceso = 0
    valor_exceso = 0


    for producto in productos:

        # cantidad excedente
        producto.exceso = (
            producto.stock -
            producto.stock_maximo
        )


        # valor del exceso de inventario
        producto.valor_exceso = (
            producto.exceso *
            float(producto.costo_promedio or 0)
        )


        unidades_exceso += producto.exceso

        valor_exceso += producto.valor_exceso



    return render_template(
        "productos_sobre_stock.html",
        productos=productos,
        unidades_exceso=unidades_exceso,
        valor_exceso=valor_exceso
    )


@app.route("/productos-sin-movimiento")
@login_requerido
def productos_sin_movimiento():

    productos_sin_movimiento = Producto.query.filter(
        Producto.dias_sin_movimiento > 0
    ).order_by(
        Producto.dias_sin_movimiento.desc()
    ).all()


    return render_template(
        "productos_sin_movimiento.html",
        productos_sin_movimiento=productos_sin_movimiento
    )


# ==================================================
# EXPORTAR PRODUCTOS EXCEL
# ==================================================

@app.route("/exportar-excel")
@login_requerido
def exportar_excel():

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(url_for("login"))


    empresa = usuario_actual.empresa


    productos = Producto.query.filter_by(
        empresa_id=empresa.id
    ).all()


    import io
    import openpyxl

    from flask import send_file


    archivo = io.BytesIO()


    wb = openpyxl.Workbook()

    ws = wb.active

    ws.title = "Productos"


    ws.append([
        "Código",
        "Nombre",
        "Categoría",
        "Stock",
        "Costo compra",
        "Precio venta"
    ])


    for producto in productos:

        ws.append([
            producto.codigo,
            producto.nombre,
            producto.categoria,
            producto.stock,
            float(producto.costo_compra or 0),
            float(producto.precio_venta or 0)
        ])


    wb.save(archivo)


    archivo.seek(0)


    return send_file(
        archivo,
        download_name="productos_nexustock.xlsx",
        as_attachment=True,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ==================================================
# BUSCAR PRODUCTO POR CÓDIGO / BARRAS / QR
# ==================================================
@app.route("/buscar-producto/<codigo>")
@login_requerido
def buscar_producto(codigo):

    usuario_actual = obtener_usuario_actual()


    if not usuario_actual:

        return jsonify({
            "encontrado": False,
            "mensaje": "Sesión inválida"
        }), 401



# ==============================================
# OBTENER EMPRESA DEL USUARIO
# ==============================================

    empresa_actual = obtener_empresa_actual_obj()


    if not empresa_actual:

        return jsonify({
            "encontrado": False,
            "mensaje": "Empresa no encontrada"
        }), 404



# ==============================================
# BUSCAR PRODUCTO
# ==============================================

    producto = Producto.query.filter(

        Producto.empresa_id == empresa_actual.id,

        db.or_(

            Producto.codigo == codigo,

            Producto.codigo_barras == codigo,

            Producto.codigo_qr == codigo

        )

    ).first()



    if not producto:

        return jsonify({

            "encontrado": False,

            "codigo": codigo,

            "mensaje": "Producto no encontrado"

        })



    # ==============================================
    # RESPUESTA
    # ==============================================

    return jsonify({

        "encontrado": True,

        "id": producto.id,

        "codigo": producto.codigo,

        "nombre": producto.nombre,

        "categoria": producto.categoria,

        "stock": producto.stock,

        "precio": producto.precio,

        "unidades_por_caja": producto.unidades_por_caja,

        "codigo_barras": producto.codigo_barras,

        "codigo_qr": getattr(producto, "codigo_qr", None)

    })

# ==================================================
# NUEVO PRODUCTO
# ==================================================
@app.route("/nuevo-producto", methods=["GET", "POST"])
@login_requerido
def nuevo_producto():

    usuario_actual = obtener_usuario_actual()

    if not usuario_actual:
        return redirect(
            url_for("logout")
        )


    # ==================================================
    # PERMISOS
    # ==================================================

    if usuario_actual.rol not in [
        "admin_empresa",
        "super_admin",
        "supervisor"
    ]:

        flash(
            "No posee permisos para crear productos.",
            "danger"
        )

        return redirect(
            url_for("productos")
        )



    empresa_actual = obtener_empresa_actual_obj()


    if not empresa_actual:

        flash(
            "Empresa no encontrada.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )

# ==================================================
# VALIDAR LÍMITE DEL PLAN
# ==================================================

    from permisos import puede_crear_producto

    if not puede_crear_producto(empresa_actual):

        flash(
        "Has alcanzado el límite de productos permitido por tu plan.",
        "warning"
        )
        
        return redirect(
        url_for("productos")
    )



    # ==================================================
    # POST
    # ==================================================

    if request.method == "POST":

        try:


            # ==================================================
            # PRODUCTO
            # ==================================================

            codigo = request.form.get(
                "codigo",
                ""
            ).strip().upper()


            codigo_barras = request.form.get(
                "codigo_barras",
                ""
            ).strip()


            nombre = request.form.get(
                "nombre",
                ""
            ).strip()


            categoria = request.form.get(
                "categoria",
                ""
            ).strip()


            marca = request.form.get(
                "marca",
                ""
            ).strip()


            descripcion = request.form.get(
                "descripcion",
                ""
            ).strip()


            imagen_principal = request.form.get(
                "imagen",
                ""
            ).strip()



            # ==================================================
            # UNIDAD
            # ==================================================

            unidad_medida = request.form.get(
                "unidad_medida",
                "Unidad"
            ).strip()



            unidades_por_caja = max(
                1,
                int(
                    request.form.get(
                        "unidades_por_caja",
                        1
                    )
                    or 1
                )
            )



            # ==================================================
            # INVENTARIO
            # ==================================================

            stock = max(
                0,
                int(
                    request.form.get(
                        "stock",
                        0
                    )
                    or 0
                )
            )


            stock_minimo = max(
                0,
                int(
                    request.form.get(
                        "stock_minimo",
                        0
                    )
                    or 0
                )
            )


            stock_maximo = max(
                stock_minimo,
                int(
                    request.form.get(
                        "stock_maximo",
                        0
                    )
                    or 0
                )
            )


            punto_reorden = max(
                stock_minimo,
                int(
                    request.form.get(
                        "punto_reorden",
                        0
                    )
                    or 0
                )
            )


            ubicacion = request.form.get(
                "ubicacion",
                ""
            ).strip()



            tiempo_reposicion_dias = max(
                1,
                int(
                    request.form.get(
                        "tiempo_reposicion_dias",
                        7
                    )
                    or 7
                )
            )



            # ==================================================
            # COMERCIAL
            # ==================================================

            costo_compra = max(
                0,
                float(
                    request.form.get(
                        "costo_compra",
                        0
                    )
                    or 0
                )
            )



            precio_venta = max(
                0,
                float(
                    request.form.get(
                        "precio_venta",
                        0
                    )
                    or 0
                )
            )



            tasa_iva = max(
                0,
                float(
                    request.form.get(
                        "tasa_iva",
                        19
                    )
                    or 19
                )
            )



            # ==================================================
            # PROVEEDOR
            # ==================================================

            proveedor_id = request.form.get(
                "proveedor_id"
            )


            proveedor_id = (
                int(proveedor_id)
                if proveedor_id
                else None
            )



            # ==================================================
            # VALIDACIONES
            # ==================================================

            if not codigo:

                flash(
                    "El código es obligatorio.",
                    "warning"
                )

                return redirect(
                    url_for("nuevo_producto")
                )



            if not nombre:

                flash(
                    "El nombre es obligatorio.",
                    "warning"
                )

                return redirect(
                    url_for("nuevo_producto")
                )



            existe = Producto.query.filter_by(
                empresa_id=empresa_actual.id,
                codigo=codigo
            ).first()



            if existe:

                flash(
                    "Ya existe un producto con ese código.",
                    "warning"
                )

                return redirect(
                    url_for("nuevo_producto")
                )



            # ==================================================
            # CREAR PRODUCTO
            # ==================================================

            producto = Producto(

                empresa_id=empresa_actual.id,


                # Identificación

                codigo=codigo,

                codigo_barras=codigo_barras,

                nombre=nombre,

                categoria=categoria,

                marca=marca,

                descripcion=descripcion,

                imagen_principal=imagen_principal,



                # Inventario

                stock=stock,

                stock_minimo=stock_minimo,

                stock_maximo=stock_maximo,

                punto_reorden=punto_reorden,

                ubicacion=ubicacion,



                unidad_medida=unidad_medida,

                unidades_por_caja=unidades_por_caja,



                # Reposición inteligente

                tiempo_reposicion_dias=tiempo_reposicion_dias,



                # Comercial

                proveedor_id=proveedor_id,


                costo_compra=costo_compra,


                # Inicialmente igual al costo compra

                costo_promedio=costo_compra,


                precio_venta=precio_venta,


                tasa_iva=tasa_iva

            )



            db.session.add(producto)


            db.session.flush()



            # ==================================================
            # CÁLCULOS AUTOMÁTICOS
            # ==================================================

            producto.calcular_valor_inventario()

            producto.calcular_margen()



            # ==================================================
            # MOVIMIENTO INICIAL
            # ==================================================

            if stock > 0:


                movimiento = Movimiento(

                    empresa_id=empresa_actual.id,

                    producto_id=producto.id,

                    usuario_id=usuario_actual.id,

                    tipo="entrada",

                    cantidad=stock,

                    stock_anterior=0,

                    stock_nuevo=stock,

                    costo_unitario=costo_compra,

                    costo_total=(
                        stock *
                        costo_compra
                    ),

                    observacion=(
                        "Stock inicial creado."
                    )

                )


                db.session.add(movimiento)



            # ==================================================
            # AUDITORÍA
            # ==================================================

            auditoria = Auditoria.crear(

                accion="crear_producto",

                modulo="productos",

                descripcion=(
                    f"Producto creado: {producto.nombre}"
                ),

                empresa_id=empresa_actual.id,

                usuario_id=usuario_actual.id,

                ip=request.remote_addr,

                user_agent=request.headers.get(
                    "User-Agent"
                )

            )


            db.session.add(auditoria)



            db.session.commit()



            flash(
                "Producto creado correctamente.",
                "success"
            )



            return redirect(
                url_for("productos")
            )



        except ValueError:


            db.session.rollback()


            flash(
                "Error en los valores ingresados.",
                "warning"
            )


            return redirect(
                url_for("nuevo_producto")
            )



        except Exception:


            db.session.rollback()


            logger.exception(
                "Error creando producto"
            )


            flash(
                "Error interno creando producto.",
                "danger"
            )


            return redirect(
                url_for("nuevo_producto")
            )



    # ==================================================
    # GET
    # ==================================================

    proveedores = Proveedor.query.filter_by(
        empresa_id=empresa_actual.id
    ).order_by(
        Proveedor.nombre.asc()
    ).all()



    return render_template(
        "nuevo_producto.html",
        proveedores=proveedores
    )


# ==================================================
# MOVIMIENTOS
# ==================================================

@app.route("/movimientos")
@login_requerido
def movimientos():

    usuario_actual = obtener_usuario_actual()


    if not usuario_actual:

        session.clear()

        flash(
            "Sesión inválida.",
            "danger"
        )

        return redirect(
            url_for("login")
        )


    empresa_actual = obtener_empresa_actual_obj()


    if not empresa_actual:

        flash(
            "Empresa no encontrada.",
            "danger"
        )

        return redirect(
            url_for("logout")
        )


    # ==================================================
    # FILTROS
    # ==================================================

    tipo = request.args.get(
        "tipo",
        ""
    )


    busqueda = request.args.get(
        "busqueda",
        ""
    ).strip()



    # ==================================================
    # CONSULTA BASE
    # ==================================================

    consulta = Movimiento.query.filter_by(

        empresa_id=empresa_actual.id

    )



    if tipo:

        consulta = consulta.filter(

            Movimiento.tipo == tipo

        )



    if busqueda:

        consulta = consulta.join(

            Producto,

            Movimiento.producto_id == Producto.id

        ).filter(

            Producto.nombre.ilike(
                f"%{busqueda}%"
            )

        )



    # ==================================================
    # PAGINACIÓN
    # ==================================================

    pagina = request.args.get(
        "pagina",
        1,
        type=int
    )


    movimientos = consulta.order_by(

        Movimiento.fecha.desc()

    ).paginate(

        page=pagina,

        per_page=50,

        error_out=False

    )



    # ==================================================
    # MÉTRICAS
    # ==================================================

    total_movimientos = db.session.query(
        db.func.count(Movimiento.id)
    ).filter(
        Movimiento.empresa_id == empresa_actual.id
    ).scalar()



    total_entradas = db.session.query(
        db.func.count(Movimiento.id)
    ).filter(
        Movimiento.empresa_id == empresa_actual.id,
        Movimiento.tipo == "entrada"
    ).scalar()



    total_salidas = db.session.query(
        db.func.count(Movimiento.id)
    ).filter(
        Movimiento.empresa_id == empresa_actual.id,
        Movimiento.tipo == "salida"
    ).scalar()



    movimientos_hoy = db.session.query(
        db.func.count(Movimiento.id)
    ).filter(
        Movimiento.empresa_id == empresa_actual.id,
        db.func.date(Movimiento.fecha) == db.func.current_date()
    ).scalar()



    return render_template(

        "movimientos.html",

        usuario_actual=usuario_actual,

        empresa_actual=empresa_actual,

        movimientos=movimientos,

        tipo=tipo,

        busqueda=busqueda,

        total_movimientos=total_movimientos,

        total_entradas=total_entradas,

        total_salidas=total_salidas,

        movimientos_hoy=movimientos_hoy

    )


# ==================================================
# PRODUCTOS CON STOCK BAJO
# ==================================================

@app.route("/stock-bajo")
@app.route("/productos-stock-bajo")
@login_requerido
def stock_bajo():

    usuario_actual = obtener_usuario_actual()


    if not usuario_actual:

        session.clear()
        flash(
            "Sesión inválida.",
            "danger"
        )
        return redirect(
            url_for("login")
        )
# ==========================================
# VALIDAR EMPRESA
# ==========================================

    empresa_actual = obtener_empresa_actual_obj()



    if not empresa_actual:

        flash(
            "No existe una empresa asociada.",
            "danger"
        )

        return redirect(
            url_for("logout")
        )



    # ==========================================
    # BUSCAR PRODUCTOS STOCK BAJO
    # ==========================================

    productos = Producto.query.filter(

        Producto.empresa_id == empresa_actual.id,

        Producto.stock <= Producto.stock_minimo

    ).order_by(

        Producto.stock.asc()

    ).all()



    return render_template(

        "stock_bajo.html",

        usuario_actual=usuario_actual,

        empresa_actual=empresa_actual,

        productos=productos

    )

# ==================================================
# PRODUCTOS CON SOBRE STOCK
# ==================================================

@app.route("/sobre-stock")
@login_requerido
def sobre_stock():

    usuario_actual = obtener_usuario_actual()


    if not usuario_actual:

        session.clear()

        flash(
            "Sesión inválida.",
            "danger"
        )

        return redirect(
            url_for("login")
        )



    empresa_actual = obtener_empresa_actual_obj()



    if not empresa_actual:

        flash(
            "No existe una empresa asociada.",
            "danger"
        )

        return redirect(
            url_for("logout")
        )



    productos_db = Producto.query.filter(

        Producto.empresa_id == empresa_actual.id,

        Producto.stock > (
            Producto.stock_minimo * 3
        )

    ).order_by(

        Producto.stock.desc()

    ).all()



    productos = []

    unidades_exceso = 0

    valor_exceso = 0



    for producto in productos_db:


        stock_recomendado = producto.stock_minimo * 3


        exceso = producto.stock - stock_recomendado


        valor = exceso * producto.precio



        producto.exceso = exceso

        producto.valor_exceso = valor



        productos.append(producto)



        unidades_exceso += exceso

        valor_exceso += valor
        return render_template(

        "sobre_stock.html",

        usuario_actual=usuario_actual,

        empresa_actual=empresa_actual,

        productos=productos,

        unidades_exceso=unidades_exceso,

        valor_exceso=valor_exceso

    )




# ==================================================
# EDITAR USUARIO
# ==================================================

@app.route("/editar-usuario/<int:id>", methods=["GET", "POST"])
@login_requerido
def editar_usuario(id):

    usuario_actual = obtener_usuario_actual()


    if not usuario_actual:

        return redirect(
            url_for("login")
        )


    empresa_actual = obtener_empresa_actual_obj()


    if not empresa_actual:

        flash(
            "Empresa no encontrada.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )


# ======================================
# BUSCAR USUARIO DE LA EMPRESA
# ======================================

    usuario = Usuario.query.filter_by(

        id=id,

        empresa_id=empresa_actual.id

    ).first()

    if not usuario:

        flash(
            "Usuario no encontrado.",
            "danger"
        )

        return redirect(
            url_for("usuarios")
        )

    # ======================================
    # GUARDAR CAMBIOS
    # ======================================

    if request.method == "POST":


        try:


            nombre = request.form.get(
                "nombre",
                ""
            ).strip()


            email = request.form.get(
                "email",
                ""
            ).lower().strip()


            password = request.form.get(
                "password",
                ""
            )


            rol = request.form.get(
                "rol",
                "empleado"
            )



            # -------------------------------
            # VALIDACIONES
            # -------------------------------

            if not nombre or not email:

                flash(
                    "Nombre y correo son obligatorios.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "editar_usuario",
                        id=id
                    )
                )



            # Evitar correo duplicado

            correo_existente = Usuario.query.filter(

                Usuario.email == email,

                Usuario.id != usuario.id

            ).first()



            if correo_existente:

                flash(
                    "Ese correo ya está utilizado.",
                    "warning"
                )

                return redirect(
                    url_for(
                        "editar_usuario",
                        id=id
                    )
                )



            # -------------------------------
            # ACTUALIZAR DATOS
            # -------------------------------


            usuario.nombre = nombre

            usuario.email = email


            if rol in [
                "empleado",
                "admin_empresa"
            ]:

                usuario.rol = rol



            # -------------------------------
            # CAMBIO PASSWORD
            # -------------------------------


            if password:

                if len(password) < 8:

                    flash(
                        "La contraseña debe tener mínimo 8 caracteres.",
                        "danger"
                    )

                    return redirect(
                        url_for(
                            "editar_usuario",
                            id=id
                        )
                    )


                usuario.password = generate_password_hash(password)


# -------------------------------
# AUDITORÍA
# -------------------------------


            auditoria = Auditoria.crear(

                accion="editar_usuario",

                modulo="usuarios",

                descripcion=(

                    f"Usuario actualizado: {usuario.email}"

                ),

                empresa_id=empresa_actual.id,

                usuario_id=usuario_actual.id,

                ip=request.remote_addr,

                user_agent=request.headers.get(
                    "User-Agent"
                )

            )


            db.session.add(
                auditoria
            )

            db.session.commit()

            flash(
                "Usuario actualizado correctamente.",
                "success"
            )


            return redirect(
                url_for("usuarios")
            )



        except Exception:


            db.session.rollback()


            logger.exception(
                "Error editando usuario"
            )


            flash(
                "Error interno actualizando usuario.",
                "danger"
            )



    return render_template(

        "editar_usuario.html",

        usuario=usuario

    )

# ==================================================
# EDITAR PRODUCTO
# ==================================================
@app.route("/editar-producto/<int:id>", methods=["GET", "POST"])
@login_requerido
def editar_producto(id):

    usuario_actual = obtener_usuario_actual()


    if not usuario_actual:

        return redirect(
            url_for("login")
        )



    empresa_actual = obtener_empresa_actual_obj()


    if not empresa_actual:

        flash(
            "Empresa no encontrada.",
            "danger"
        )

        return redirect(
            url_for("dashboard")
        )



# ======================================
# BUSCAR PRODUCTO
# ======================================

    producto = Producto.query.filter_by(

        id=id,

        empresa_id=empresa_actual.id

    ).first()



    if not producto:

        flash(
            "Producto no encontrado.",
            "danger"
        )

        return redirect(
            url_for("productos")
        )

    # ======================================
    # ACTUALIZAR
    # ======================================

    if request.method == "POST":


        try:



            codigo = request.form.get(
                "codigo",
                ""
            ).strip()

            nombre = request.form.get(
                "nombre",
                ""
            ).strip()

            categoria = request.form.get(
                "categoria",
                ""
            ).strip()

            marca = request.form.get(
                "marca",
                ""
            ).strip()

            codigo_barras = request.form.get(
                "codigo_barras",
                ""
            ).strip()

            descripcion = request.form.get(
                "descripcion",
                ""
            ).strip()


            # ======================================
            # INVENTARIO
            # ======================================

            stock = request.form.get(
                "stock",
                0
            )

            stock_minimo = request.form.get(
                "stock_minimo",
                0
            )

            stock_maximo = request.form.get(
                "stock_maximo",
                0
            )

            unidad_medida = request.form.get(
                "unidad_medida",
                "unidad"
            ).strip()

            ubicacion = request.form.get(
                "ubicacion",
                ""
            ).strip()

            proveedor_id = request.form.get(
                "proveedor_id"
            )

            tiempo_reposicion_dias = request.form.get(
                "tiempo_reposicion_dias",
                7
            )


            # ======================================
            # PRECIOS
            # ======================================

            costo_compra = request.form.get(
                "costo_compra",
                0
            )

            precio_venta = request.form.get(
                "precio_venta",
                0
            )


            # ======================================
            # IMPUESTOS
            # ======================================

            tasa_iva = request.form.get(
                "tasa_iva",
                19
            )

            incluye_iva = (
                request.form.get(
                    "incluye_iva"
                )
                == "on"
            )


            # ======================================
            # CONTROL
            # ======================================

            activo = (
                request.form.get(
                    "activo"
                )
                == "on"
            )


# ==================================
# VALIDACIONES
# ==================================



            if not codigo:

                flash(
                    "Debe ingresar un código.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "editar_producto",
                        id=id
                    )
                )


            if not nombre:

                flash(
                    "Debe ingresar un nombre.",
                    "danger"
                )

                return redirect(
                    url_for(
                        "editar_producto",
                        id=id
                    )
                )


            producto_existente = Producto.query.filter(

                Producto.empresa_id == empresa_actual.id,

                Producto.codigo == codigo,

                Producto.id != producto.id

            ).first()


            if producto_existente:

                flash(
                    "Ya existe un producto con ese código.",
                    "warning"
                )

                return redirect(
                    url_for(
                        "editar_producto",
                        id=id
                    )
                )


            if float(costo_compra or 0) < 0:

                flash(
                    "El costo no puede ser negativo.",
                    "warning"
                )

                return redirect(
                    url_for(
                        "editar_producto",
                        id=id
                    )
                )


            if float(precio_venta or 0) < 0:

                flash(
                    "El precio de venta no puede ser negativo.",
                    "warning"
                )

                return redirect(
                    url_for(
                        "editar_producto",
                        id=id
                    )
                )


            if int(stock or 0) < 0:

                flash(
                    "El stock no puede ser negativo.",
                    "warning"
                )

                return redirect(
                    url_for(
                        "editar_producto",
                        id=id
                    )
                )



# ==================================
# GUARDAR CAMBIOS
# ==================================



            producto.codigo = codigo

            producto.nombre = nombre

            producto.categoria = categoria

            producto.marca = marca

            producto.codigo_barras = codigo_barras

            producto.descripcion = descripcion


            # ==================================
            # INVENTARIO
            # ==================================

            producto.stock = int(
                stock or 0
            )

            producto.stock_minimo = int(
                stock_minimo or 0
            )

            producto.stock_maximo = int(
                stock_maximo or 0
            )

            producto.unidad_medida = unidad_medida

            producto.ubicacion = ubicacion

            producto.tiempo_reposicion_dias = int(
                tiempo_reposicion_dias or 7
            )

            if proveedor_id:

                producto.proveedor_id = int(
                    proveedor_id
                )

            else:

                producto.proveedor_id = None


            # ==================================
            # PRECIOS
            # ==================================

            producto.costo_compra = float(
                costo_compra or 0
            )

            producto.precio_venta = float(
                precio_venta or 0
            )

            if not producto.costo_promedio:

                producto.costo_promedio = (
                    producto.costo_compra
                )


            # ==================================
            # IMPUESTOS
            # ==================================

            producto.tasa_iva = float(
                tasa_iva or 19
            )

            producto.incluye_iva = incluye_iva

            producto.activo = activo


            # ==================================
            # INDICADORES AUTOMÁTICOS
            # ==================================

            producto.calcular_margen()

            producto.calcular_valor_inventario()


            # ==================================
            # ACTUALIZAR INDICADORES
            # ==================================

            if producto.costo_promedio <= 0:

                producto.costo_promedio = (
                    producto.costo_compra
                )

            producto.calcular_margen()

            producto.calcular_valor_inventario()

            if producto.stock <= producto.stock_minimo:

                producto.punto_reorden = max(

                    producto.stock_minimo,

                    producto.stock_seguridad or 0

                )

            # ==================================
            # AUDITORÍA
            # ==================================


            auditoria = Auditoria.crear(

                accion="editar_producto",

                modulo="inventario",

                descripcion=(

                    f"Producto actualizado: {producto.nombre}"

                ),

                empresa_id=empresa_actual.id,

                usuario_id=usuario_actual.id,

                ip=request.remote_addr,

                user_agent=request.headers.get(
                    "User-Agent"
                )

            )


            db.session.add(
                auditoria
            )


            db.session.commit()



            flash(
                "Producto actualizado correctamente.",
                "success"
            )


            return redirect(
                url_for("productos")
            )



        except Exception:


            db.session.rollback()


            logger.exception(
                "Error editando producto"
            )


            flash(
                "Error interno actualizando producto.",
                "danger"
            )



    return render_template(

        "editar_producto.html",

        producto=producto

    )

# ==================================================
# ANALISIS DE CONSUMO Y PREDICCION
# ==================================================

from datetime import datetime, timedelta


def calcular_prediccion_producto(producto):


    fecha_inicio = datetime.utcnow() - timedelta(days=30)



    movimientos = Movimiento.query.filter(

        Movimiento.producto_id == producto.id,

        Movimiento.tipo == "salida",

        Movimiento.fecha >= fecha_inicio

    ).all()



    total_salidas = sum(
        m.cantidad
        for m in movimientos
    )



    consumo_diario = (
        total_salidas / 30
        if total_salidas > 0
        else 0
    )



    if consumo_diario > 0:

        dias_stock = (
            producto.stock /
            consumo_diario
        )

    else:

        dias_stock = 999



    if dias_stock <= 7:

        estado = "critico"


    elif dias_stock <= 15:

        estado = "atencion"


    else:

        estado = "estable"



    compra_recomendada = 0


    if dias_stock < 15:


        objetivo_stock = consumo_diario * 30


        compra_recomendada = max(
            0,
            int(objetivo_stock - producto.stock)
        )



    return {

        "producto": producto.nombre,

        "stock": producto.stock,

        "salidas_30_dias": total_salidas,

        "consumo_diario": round(
            consumo_diario,
            2
        ),

        "dias_stock": round(
            dias_stock,
            1
        ),

        "estado": estado,

        "compra_recomendada":
            compra_recomendada

    }


@app.route("/prediccion-inventario")
@login_requerido
def prediccion_inventario():

    productos = Producto.query.filter(
        Producto.activo == True
    ).all()


    predicciones = []


    for producto in productos:

        consumo_diario = float(
            producto.consumo_promedio_diario or 0
        )


        stock_actual = producto.stock or 0


        # Si no existe consumo histórico
        if consumo_diario <= 0:

            dias_stock = 999
            estado = "estable"
            compra_recomendada = 0


        else:

            dias_stock = int(
                stock_actual / consumo_diario
            )


            # Estado del inventario

            if dias_stock <= 7:

                estado = "critico"


            elif dias_stock <= 30:

                estado = "atencion"


            else:

                estado = "estable"



            # Compra sugerida:
            # llevar inventario al stock máximo

            if stock_actual < producto.stock_maximo:

                compra_recomendada = (
                    producto.stock_maximo -
                    stock_actual
                )

            else:

                compra_recomendada = 0



        predicciones.append({

            "producto": producto.nombre,

            "stock": stock_actual,

            "consumo_diario": round(
                consumo_diario,
                2
            ),

            "dias_stock": dias_stock,

            "estado": estado,

            "compra_recomendada": compra_recomendada

        })



    # ordenar primero los productos críticos

    prioridad = {
        "critico": 1,
        "atencion": 2,
        "estable": 3
    }


    predicciones.sort(
        key=lambda x: prioridad[x["estado"]]
    )



    return render_template(
        "prediccion_inventario.html",
        predicciones=predicciones
    )

# ==================================================
# CONFIGURACIÓN FINAL DE EJECUCIÓN
# ==================================================

if __name__ == "__main__":

    entorno = os.getenv(
        "FLASK_ENV",
        "development"
    )


    puerto = int(
        os.getenv(
            "PORT",
            5000
        )
    )


    if entorno == "production":

        print(
            "NexuStock ejecutándose en modo producción."
        )


    else:

        print(
            "NexuStock iniciando en modo desarrollo."
        )


    app.run(
        host="0.0.0.0",
        port=puerto,
        debug=(entorno != "production")
    )
