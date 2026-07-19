from flask import Flask, render_template, request, redirect, url_for, session
from models import db, Producto, Movimiento, Usuario
from functools import wraps
from flask import send_file
from openpyxl import Workbook
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)
from dotenv import load_dotenv
import os
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer
load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "nexustock_local_dev_key"
)

serializer = URLSafeTimedSerializer(
    app.secret_key
)

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
    "DATABASE_URL",
    "sqlite:///optistock.db"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# ----------------------------------
# CORREO
# ----------------------------------

app.config["MAIL_SERVER"] = "smtp.gmail.com"
app.config["MAIL_PORT"] = 587
app.config["MAIL_USE_TLS"] = True

app.config["MAIL_USERNAME"] = os.getenv(
    "MAIL_USERNAME"
)

app.config["MAIL_PASSWORD"] = os.getenv(
    "MAIL_PASSWORD"
)

app.config["MAIL_DEFAULT_SENDER"] = os.getenv(
    "MAIL_USERNAME"
)
mail = Mail(app)

db.init_app(app)

with app.app_context():
    db.create_all()
    
# ----------------------------------
# LOGIN
# ----------------------------------

@app.route("/", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form["email"]
        password = request.form["password"]

        usuario = Usuario.query.filter_by(
            email=email
        ).first()

        if usuario and check_password_hash(
            usuario.password,
            password
        ):

            session["usuario_id"] = usuario.id

            return redirect(
                url_for("dashboard")
            )

        return "Correo o contraseña incorrectos"

    return render_template(
        "login.html"
    )

# ----------------------------------
# SOLO ADMIN
# ----------------------------------

def admin_requerido(f):

    @wraps(f)
    def decorada(*args, **kwargs):

        if "usuario_id" not in session:
            return redirect(
                url_for("login")
            )

        usuario = Usuario.query.get(
            session["usuario_id"]
        )

        if not usuario:
            session.clear()
            return redirect(
                url_for("login")
            )

        if usuario.rol != "admin":
            return """
            Acceso denegado.
            Solo administradores.
            """

        return f(*args, **kwargs)

    return decorada

# ----------------------------------
# PROTEGER RUTAS
# ----------------------------------

from functools import wraps

def login_requerido(f):

    @wraps(f)
    def decorada(*args, **kwargs):

        if "usuario_id" not in session:
            return redirect(
                url_for("login")
            )

        return f(*args, **kwargs)

    return decorada
# ----------------------------------
# VERIFICAR ADMIN
# ----------------------------------

def es_admin():

    if "usuario_id" not in session:
        return False

    usuario = Usuario.query.get(
        session["usuario_id"]
    )

    if not usuario:
        return False

    return usuario.rol == "admin"

# ----------------------------------
# DASHBOARD
# ----------------------------------

@app.route("/dashboard")
@login_requerido
def dashboard():

    total_productos = Producto.query.count()

    stock_bajo = Producto.query.filter(
        Producto.stock <= Producto.stock_minimo
    ).count()

    total_movimientos = Movimiento.query.count()

    productos = Producto.query.all()

    valor_inventario = sum(
        producto.stock * producto.precio
        for producto in productos
    )

    # STOCK BAJO

    productos_stock_bajo = Producto.query.filter(
        Producto.stock <= Producto.stock_minimo
    ).all()

    # SIN MOVIMIENTO

    productos_sin_movimiento = []

    for producto in productos:

        if len(producto.movimientos) == 0:

            productos_sin_movimiento.append(
                producto
            )

    total_sin_movimiento = len(
        productos_sin_movimiento
    )

    # MÁS VENDIDOS

    productos_mas_vendidos = []

    for producto in productos:

        total_salidas = 0

        for movimiento in producto.movimientos:

            if movimiento.tipo == "Salida":

                total_salidas += movimiento.cantidad

        productos_mas_vendidos.append({
            "nombre": producto.nombre,
            "ventas": total_salidas
        })

    productos_mas_vendidos.sort(
        key=lambda x: x["ventas"],
        reverse=True
    )

    productos_mas_vendidos = (
        productos_mas_vendidos[:5]
    )

    # MENOS VENDIDOS

    productos_menos_vendidos = sorted(
        productos_mas_vendidos,
        key=lambda x: x["ventas"]
    )[:5]

    # SOBRE STOCK

    productos_sobre_stock = []

    for producto in productos:

        if producto.stock > (
            producto.stock_minimo * 3
        ):

            productos_sobre_stock.append(
                producto
            )

    print(
        "Productos sobre stock:",
        len(productos_sobre_stock)
    )
    # ----------------------------------
    # DASHBOARD IA
    # ----------------------------------

    # Riesgo de quiebre

    riesgo_quiebre = len(
        productos_stock_bajo
    )

    # Dinero inmovilizado

    dinero_inmovilizado = 0

    for producto in productos_sin_movimiento:

        dinero_inmovilizado += (
            producto.stock *
            producto.precio
        )

    # Productos recomendados para compra

    productos_recomendados = []

    for producto in productos_stock_bajo:

        cantidad_recomendada = (
            producto.stock_minimo * 2
        ) - producto.stock

        if cantidad_recomendada > 0:

            productos_recomendados.append({
                "nombre": producto.nombre,
                "cantidad": cantidad_recomendada
            })

    # Salud del inventario

    salud_inventario = 100

    salud_inventario -= (
        len(productos_stock_bajo) * 5
    )

    salud_inventario -= (
        len(productos_sin_movimiento) * 2
    )

    salud_inventario -= (
        len(productos_sobre_stock) * 2
    )

    if salud_inventario < 0:
        salud_inventario = 0

    # ----------------------------------
    # ESTADO DE SALUD
    # ----------------------------------

    if salud_inventario >= 80:

        estado_salud = "Excelente"
        color_salud = "green"

    elif salud_inventario >= 50:

        estado_salud = "Regular"
        color_salud = "yellow"

    else:

        estado_salud = "Crítico"
        color_salud = "red"

    # ----------------------------------
    # RECOMENDACIONES IA
    # ----------------------------------

    productos_recomendados = []

    for producto in productos:

        if producto.stock <= (
            producto.stock_minimo * 1.5
        ):

            productos_recomendados.append(
                producto
            )

    # ----------------------------------
    # COPILOTO IA
    # ----------------------------------

    acciones_hoy = []

    # Compras recomendadas

    for producto in productos_stock_bajo:
        
        cantidad_comprar = (
            producto.stock_minimo * 2
            ) - producto.stock
        
        if cantidad_comprar > 0:
            
            acciones_hoy.append(
                f"🔴 URGENTE | Comprar {cantidad_comprar} unidades de {producto.nombre}."
                )

    # Sobre stock

    for producto in productos_sobre_stock:
        
        acciones_hoy.append(
            f"🟡 ATENCIÓN | Revisar sobre stock de {producto.nombre}."
            )

    # Sin movimiento

    for producto in productos_sin_movimiento:
        
        acciones_hoy.append(
            f"🟢 OPORTUNIDAD | Promocionar o liquidar {producto.nombre}."
            )
        
    # ----------------------------------
    # NOMBRES PARA COPILOTO IA
    # ----------------------------------

    if len(acciones_hoy) == 0:

        acciones_hoy.append(
            "Todo está funcionando correctamente."
        )

    nombres_stock_bajo = [
        producto.nombre
        for producto in productos_stock_bajo
    ]

    nombres_sobre_stock = [
        producto.nombre
        for producto in productos_sobre_stock
    ]

    nombres_sin_movimiento = [
        producto.nombre
        for producto in productos_sin_movimiento
    ]

    return render_template(
        "dashboard.html",

        total_productos=total_productos,
        stock_bajo=stock_bajo,
        total_movimientos=total_movimientos,
        valor_inventario=valor_inventario,

        productos_stock_bajo=productos_stock_bajo,
        productos_sin_movimiento=productos_sin_movimiento,

        total_sin_movimiento=total_sin_movimiento,

        productos_sobre_stock=productos_sobre_stock,

        productos_mas_vendidos=productos_mas_vendidos,
        productos_menos_vendidos=productos_menos_vendidos,

        productos_recomendados=productos_recomendados,

        nombres_stock_bajo=nombres_stock_bajo,
        nombres_sobre_stock=nombres_sobre_stock,
        nombres_sin_movimiento=nombres_sin_movimiento,

        estado_salud=estado_salud,
        color_salud=color_salud,

        riesgo_quiebre=riesgo_quiebre,
        dinero_inmovilizado=dinero_inmovilizado,
        salud_inventario=salud_inventario,
        acciones_hoy=acciones_hoy
    )

# ----------------------------------
# PRODUCTOS
# ----------------------------------

@app.route("/productos")
@login_requerido
def productos():

    busqueda = request.args.get(
        "buscar",
        ""
    )

    if busqueda:

        productos = Producto.query.filter(
            Producto.nombre.contains(busqueda)
        ).all()

    else:

        productos = Producto.query.all()

    usuario_actual = Usuario.query.get(
        session["usuario_id"]
    )

    return render_template(
        "productos.html",
        productos=productos,
        busqueda=busqueda,
        usuario_actual=usuario_actual
    )

# ----------------------------------
# EXPORTAR EXCEL
# ----------------------------------

@app.route("/exportar-excel")
@login_requerido
def exportar_excel():

    productos = Producto.query.all()

    wb = Workbook()

    ws = wb.active

    ws.title = "Productos"

    ws.append([
        "Código",
        "Nombre",
        "Categoría",
        "Stock",
        "Stock Mínimo",
        "Precio"
    ])

    for producto in productos:

        ws.append([
            producto.codigo,
            producto.nombre,
            producto.categoria,
            producto.stock,
            producto.stock_minimo,
            producto.precio
        ])

    archivo = "optistock_productos.xlsx"

    wb.save(archivo)

    return send_file(
        archivo,
        as_attachment=True
    )

# ----------------------------------
# NUEVO PRODUCTO
# ----------------------------------

@app.route("/nuevo-producto", methods=["GET", "POST"])
@login_requerido
def nuevo_producto():

    if request.method == "POST":

        existe = Producto.query.filter_by(
            codigo=request.form["codigo"]
        ).first()

        if existe:
            return "Ya existe un producto con ese código."

        producto = Producto(

            codigo=request.form["codigo"],

            codigo_barras=request.form.get(
                "codigo_barras", ""
            ),

            nombre=request.form["nombre"],

            categoria=request.form["categoria"],

            stock=int(
                request.form["stock"] or 0
            ),

            stock_minimo=int(
                request.form["stock_minimo"] or 0
            ),

            precio=float(
                request.form["precio"] or 0
            ),

            unidades_por_caja=int(
                request.form.get(
                    "unidades_por_caja", 1
                )
            ),

            descripcion=request.form[
                "descripcion"
            ]

        )

        db.session.add(producto)
        db.session.commit()

        return redirect(
            url_for("productos")
        )

    return render_template(
        "nuevo_producto.html"
    )

# ----------------------------------
# EDITAR PRODUCTO
# ----------------------------------

@app.route("/editar-producto/<int:id>", methods=["GET", "POST"])
@login_requerido
def editar_producto(id):

    producto = Producto.query.get_or_404(id)

    if request.method == "POST":

        existe = Producto.query.filter(
            Producto.codigo == request.form["codigo"],
            Producto.id != id
        ).first()

        if existe:
            return "Ya existe otro producto con ese código."

        producto.codigo = request.form["codigo"]

        producto.nombre = request.form["nombre"]

        producto.categoria = request.form["categoria"]

        producto.stock = int(
            request.form["stock"] or 0
        )

        producto.stock_minimo = int(
            request.form["stock_minimo"] or 0
        )

        producto.precio = float(
            request.form["precio"] or 0
        )

        producto.descripcion = request.form[
            "descripcion"
        ]
        
        producto.codigo_barras = request.form[
            "codigo_barras"
            ]
        
        producto.unidades_por_caja = int(
            request.form["unidades_por_caja"] or 1
            )

        db.session.commit()

        return redirect(
            url_for("productos")
        )

    return render_template(
        "editar_producto.html",
        producto=producto
    )

# ----------------------------------
# ELIMINAR PRODUCTO
# ----------------------------------

@app.route("/eliminar-producto/<int:id>")
@admin_requerido
def eliminar_producto(id):

    producto = Producto.query.get_or_404(
        id
    )

    db.session.delete(producto)

    db.session.commit()

    return redirect(
        url_for("productos")
    )

# ----------------------------------
# MOVIMIENTOS
# ----------------------------------

@app.route("/movimientos")
@login_requerido
def movimientos():

    movimientos = Movimiento.query.order_by(
        Movimiento.fecha.desc()
    ).all()

    return render_template(
        "movimientos.html",
        movimientos=movimientos
    )

# ----------------------------------
# REPORTES
# ----------------------------------

@app.route("/reportes")
@login_requerido
def reportes():

    total_productos = Producto.query.count()

    stock_bajo = Producto.query.filter(
        Producto.stock <= Producto.stock_minimo
    ).count()

    movimientos = Movimiento.query.order_by(
        Movimiento.fecha.desc()
    ).limit(10).all()

    productos = Producto.query.all()

    valor_inventario = sum(
        producto.stock * producto.precio
        for producto in productos
    )

    return render_template(
        "reportes.html",
        total_productos=total_productos,
        stock_bajo=stock_bajo,
        valor_inventario=valor_inventario,
        movimientos=movimientos
    )
# ----------------------------------
# USUARIOS
# ----------------------------------
@app.route("/usuarios")
@login_requerido
def usuarios():

    if not es_admin():
        return "Acceso denegado"

    usuarios = Usuario.query.all()

    return render_template(
        "usuarios.html",
        usuarios=usuarios
    )

# ----------------------------------
# NUEVO USUARIO
# ----------------------------------

@app.route("/nuevo-usuario", methods=["GET", "POST"])
@login_requerido
def nuevo_usuario():

    if not es_admin():
        return "Acceso denegado"

    if request.method == "POST":

        existe = Usuario.query.filter_by(
            email=request.form["email"]
        ).first()

        if existe:
            return "Ya existe un usuario con ese correo."

        rol = request.form["rol"]

        if rol not in ["admin", "empleado"]:
            return "Rol inválido."

        usuario = Usuario(
            nombre=request.form["nombre"],
            email=request.form["email"],
            password=generate_password_hash(
                request.form["password"]
            ),
            rol=rol
        )

        db.session.add(usuario)
        db.session.commit()

        return redirect(
            url_for("usuarios")
        )

    return render_template(
        "nuevo_usuario.html"
    )

# ----------------------------------
# EDITAR USUARIO
# ----------------------------------

@app.route("/editar-usuario/<int:id>", methods=["GET", "POST"])
@login_requerido
def editar_usuario(id):

    if not es_admin():
        return "Acceso denegado"

    usuario = Usuario.query.get_or_404(id)

    if request.method == "POST":

        existe = Usuario.query.filter(
            Usuario.email == request.form["email"],
            Usuario.id != id
        ).first()

        if existe:
            return "Ya existe otro usuario con ese correo."

        rol = request.form["rol"]

        if rol not in ["admin", "empleado"]:
            return "Rol inválido."

        usuario.nombre = request.form["nombre"]
        usuario.email = request.form["email"]
        usuario.rol = rol

        if request.form["password"]:

            usuario.password = generate_password_hash(
                request.form["password"]
            )

        db.session.commit()

        return redirect(
            url_for("usuarios")
        )

    return render_template(
        "editar_usuario.html",
        usuario=usuario
    )

# ----------------------------------
# ELIMINAR USUARIO
# ----------------------------------

@app.route("/eliminar-usuario/<int:id>")
@login_requerido
def eliminar_usuario(id):

    if not es_admin():
        return "Acceso denegado"

    usuario = Usuario.query.get_or_404(id)

    if usuario.id == session["usuario_id"]:
        return "No puedes eliminar tu propia cuenta."

    admins = Usuario.query.filter_by(
        rol="admin"
    ).count()

    if usuario.rol == "admin" and admins <= 1:
        return "No puedes eliminar el único administrador."

    db.session.delete(usuario)
    db.session.commit()

    return redirect(
        url_for("usuarios")
    )

# ----------------------------------
# ENTRADA DE STOCK
# ----------------------------------

@app.route("/entrada-stock", methods=["GET", "POST"])
@login_requerido
def entrada_stock():

    if request.method == "POST":

        try:

            producto_id = int(
                request.form["producto_id"]
            )

            cantidad = int(
                request.form["cantidad"]
            )

        except:
            return "Cantidad inválida."

        if cantidad <= 0:
            return "La cantidad debe ser mayor que cero."

        producto = Producto.query.get_or_404(
            producto_id
        )

        producto.stock += cantidad

        movimiento = Movimiento(
            tipo="Entrada",
            cantidad=cantidad,
            producto_id=producto.id,
            usuario_id=session["usuario_id"]
        )

        db.session.add(movimiento)
        db.session.commit()

        return redirect(
            url_for("productos")
        )

    productos = Producto.query.all()

    producto_preseleccionado = request.args.get(
        "producto"
    )

    return render_template(
        "entrada_stock.html",
        productos=productos,
        producto_preseleccionado=producto_preseleccionado
    )

# ----------------------------------
# SALIDA DE STOCK
# ----------------------------------

@app.route("/salida-stock", methods=["GET", "POST"])
@login_requerido
def salida_stock():

    if request.method == "POST":

        try:

            producto_id = int(
                request.form["producto_id"]
            )

            cantidad = int(
                request.form["cantidad"]
            )

        except:
            return "Cantidad inválida."

        if cantidad <= 0:
            return "La cantidad debe ser mayor que cero."

        producto = Producto.query.get_or_404(
            producto_id
        )

        if cantidad > producto.stock:
            return "Stock insuficiente."

        producto.stock -= cantidad

        movimiento = Movimiento(
            tipo="Salida",
            cantidad=cantidad,
            producto_id=producto.id,
            usuario_id=session["usuario_id"]
        )

        db.session.add(movimiento)
        db.session.commit()

        return redirect(
            url_for("productos")
        )

    productos = Producto.query.all()

    producto_preseleccionado = request.args.get(
        "producto"
    )

    return render_template(
        "salida_stock.html",
        productos=productos,
        producto_preseleccionado=producto_preseleccionado
    )

# ----------------------------------
# CREAR ADMIN
# ----------------------------------

@app.route("/crear-admin")
@login_requerido
def crear_admin():

    if not es_admin():
        return "Acceso denegado"

    existe = Usuario.query.filter_by(
        email="admin@optistock.com"
    ).first()

    if existe:
        return "El administrador ya existe."

    admin = Usuario(
        nombre="Administrador",
        email="admin@optistock.com",
        password=generate_password_hash(
            "123456"
        ),
        rol="admin"
    )

    db.session.add(admin)
    db.session.commit()

    return "Administrador creado correctamente"

# ----------------------------------
# LOGOUT
# ----------------------------------

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("login")
    )

# ----------------------------------
# OLVIDE CONTRASEÑA
# ----------------------------------

@app.route(
    "/olvide-password",
    methods=["GET", "POST"]
)
def olvide_password():

    if request.method == "POST":

        email = request.form["email"]

        usuario = Usuario.query.filter_by(
            email=email
        ).first()

        if usuario:

            token = serializer.dumps(
                email,
                salt="recuperar-password"
            )

            enlace = url_for(
                "reset_password",
                token=token,
                _external=True
            )

            mensaje = Message(
                "Recuperación de contraseña NexuStock",
                recipients=[email]
            )

            mensaje.body = f"""
Hola {usuario.nombre}

Haz clic en el siguiente enlace para cambiar tu contraseña:

{enlace}

Este enlace expira en 30 minutos.
"""

            mail.send(mensaje)

        return """
        Si el correo existe,
        se ha enviado un enlace
        de recuperación.
        """

    return render_template(
        "olvide_password.html"
    )

# ----------------------------------
# RESET PASSWORD
# ----------------------------------

@app.route(
    "/reset-password/<token>",
    methods=["GET", "POST"]
)
def reset_password(token):

    try:

        email = serializer.loads(
            token,
            salt="recuperar-password",
            max_age=1800
        )

    except:

        return """
        El enlace es inválido
        o ha expirado.
        """

    usuario = Usuario.query.filter_by(
        email=email
    ).first()

    if not usuario:
        return "Usuario no encontrado."

    if request.method == "POST":

        nueva_password = request.form[
            "password"
        ]

        usuario.password = (
            generate_password_hash(
                nueva_password
            )
        )

        db.session.commit()

        return """
        Contraseña actualizada
        correctamente.
        """

    return render_template(
        "reset_password.html"
    )

# ----------------------------------
# ESCÁNER
# ----------------------------------

@app.route("/escaner")
@login_requerido
def escaner():

    return render_template(
        "escaner.html"
    )

# ----------------------------------
# BUSCAR PRODUCTO POR CÓDIGO
# ----------------------------------

@app.route("/buscar-producto/<codigo>")
@login_requerido
def buscar_producto(codigo):

    producto = Producto.query.filter_by(
        codigo_barras=codigo
    ).first()

    if not producto:

        return {
            "encontrado": False
        }

    return {
        "encontrado": True,
        "id": producto.id,
        "nombre": producto.nombre,
        "stock": producto.stock,
        "precio": producto.precio,
        "unidades_por_caja": producto.unidades_por_caja
    }

# ----------------------------------
# PROBAR CORREO
# ----------------------------------

@app.route("/probar-correo")
def probar_correo():

    mensaje = Message(
        "Prueba NexuStock",
        recipients=[
            "davidsondp1993@gmail.com"
        ]
    )

    mensaje.body = """
    Este es un correo de prueba
    enviado desde NexuStock.
    """

    mail.send(mensaje)

    return "Correo enviado correctamente"

# ----------------------------------
# EJECUTAR
# ----------------------------------

if __name__ == "__main__":
    app.run(debug=True)