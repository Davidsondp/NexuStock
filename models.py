from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

# ----------------------------------
# PRODUCTOS
# ----------------------------------

class Producto(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    codigo = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )

    nombre = db.Column(
        db.String(100),
        nullable=False
    )

    categoria = db.Column(
        db.String(100)
    )

    stock = db.Column(
        db.Integer,
        default=0
    )

    stock_minimo = db.Column(
        db.Integer,
        default=0
    )

    precio = db.Column(
        db.Float,
        default=0
    )

    descripcion = db.Column(
        db.Text
    )

    movimientos = db.relationship(
        "Movimiento",
        backref="producto",
        lazy=True
    )

    codigo_barras = db.Column(
        db.String(100),
        unique=True
    )

    unidades_por_caja = db.Column(
        db.Integer,
        default=1
    )

# ----------------------------------
# MOVIMIENTOS
# ----------------------------------

class Movimiento(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    tipo = db.Column(
        db.String(20),
        nullable=False
    )

    cantidad = db.Column(
        db.Integer,
        nullable=False
    )

    fecha = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )

    producto_id = db.Column(
        db.Integer,
        db.ForeignKey("producto.id"),
        nullable=False
    )

    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey("usuario.id")
    )

    usuario = db.relationship(
        "Usuario"
    )

# ----------------------------------
# USUARIOS
# ----------------------------------

class Usuario(db.Model):

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    nombre = db.Column(
        db.String(100),
        nullable=False
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    password = db.Column(
        db.String(200),
        nullable=False
    )

    rol = db.Column(
        db.String(20),
        default="empleado"
    )
    