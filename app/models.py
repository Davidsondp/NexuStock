"""NexuStock: modelo de dominio reconstruido desde el Prompt Maestro.

UTC se guarda como datetime naive. El stock sólo existe en Inventario y cada
cambio genera un Movimiento mediante un servicio transaccional. PlanSaaS y
Suscripcion son la única fuente de verdad del plan, funciones y límites.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import hmac
import secrets
from decimal import Decimal
from typing import Any

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, UniqueConstraint, event, text
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import validates
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()
BIGINT_ID = db.BigInteger().with_variant(db.Integer, "sqlite")


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class TimestampMixin:
    creado_en = db.Column(db.DateTime, nullable=False, default=utcnow)
    actualizado_en = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class SoftDeleteMixin:
    eliminado = db.Column(db.Boolean, nullable=False, default=False, index=True)
    eliminado_en = db.Column(db.DateTime)

    def soft_delete(self) -> None:
        self.eliminado, self.eliminado_en = True, utcnow()

    def restore(self) -> None:
        self.eliminado, self.eliminado_en = False, None


class PlanSaaS(TimestampMixin, db.Model):
    __tablename__ = "plan_saas"
    __table_args__ = (
        CheckConstraint("precio_mensual >= 0 AND precio_anual >= 0", name="ck_plan_precios"),
        CheckConstraint("dias_prueba >= 0", name="ck_plan_dias_prueba"),
        CheckConstraint("limite_productos IS NULL OR limite_productos >= 0", name="ck_plan_limite_productos"),
        CheckConstraint("limite_usuarios IS NULL OR limite_usuarios >= 0", name="ck_plan_limite_usuarios"),
        CheckConstraint("limite_movimientos_mes IS NULL OR limite_movimientos_mes >= 0", name="ck_plan_limite_movimientos"),
        CheckConstraint("limite_sucursales IS NULL OR limite_sucursales >= 0", name="ck_plan_limite_sucursales"),
        CheckConstraint("limite_bodegas IS NULL OR limite_bodegas >= 0", name="ck_plan_limite_bodegas"),
    )
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(30), nullable=False, unique=True)
    nombre = db.Column(db.String(80), nullable=False, unique=True)
    descripcion = db.Column(db.Text)
    precio_mensual = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    precio_anual = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    moneda = db.Column(db.String(3), nullable=False, default="CLP")
    dias_prueba = db.Column(db.Integer, nullable=False, default=0)
    # NULL representa un recurso ilimitado.
    limite_productos = db.Column(db.Integer)
    limite_usuarios = db.Column(db.Integer)
    limite_movimientos_mes = db.Column(db.Integer)
    limite_sucursales = db.Column(db.Integer)
    limite_bodegas = db.Column(db.Integer)
    almacenamiento_mb = db.Column(db.Integer)
    funciones = db.Column(MutableDict.as_mutable(db.JSON), nullable=False, default=dict)
    activo = db.Column(db.Boolean, nullable=False, default=True, index=True)
    orden = db.Column(db.Integer, nullable=False, default=0)
    suscripciones = db.relationship("Suscripcion", back_populates="plan")

    @validates("codigo")
    def validar_codigo(self, _key: str, value: str) -> str:
        value = (value or "").strip().lower()
        if not value:
            raise ValueError("Código de plan obligatorio")
        return value

    def tiene_funcion(self, codigo: str) -> bool:
        return bool((self.funciones or {}).get(codigo, False))

    def limite(self, recurso: str) -> int | None:
        campos = {"productos": "limite_productos", "usuarios": "limite_usuarios",
                  "movimientos_mes": "limite_movimientos_mes", "sucursales": "limite_sucursales",
                  "bodegas": "limite_bodegas", "almacenamiento_mb": "almacenamiento_mb"}
        if recurso not in campos:
            raise ValueError(f"Recurso desconocido: {recurso}")
        return getattr(self, campos[recurso])


class Empresa(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "empresa"
    __table_args__ = (
        CheckConstraint("estado IN ('activa','suspendida','cancelada')", name="ck_empresa_estado"),
    )
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(150), nullable=False)
    identificacion_fiscal = db.Column(db.String(30), unique=True)
    email = db.Column(db.String(254), nullable=False, unique=True)
    telefono = db.Column(db.String(30))
    direccion = db.Column(db.String(255))
    ciudad = db.Column(db.String(100))
    pais = db.Column(db.String(2), nullable=False, default="CL")
    moneda = db.Column(db.String(3), nullable=False, default="CLP")
    idioma = db.Column(db.String(10), nullable=False, default="es")
    zona_horaria = db.Column(db.String(64), nullable=False, default="America/Santiago")
    estado = db.Column(db.String(20), nullable=False, default="activa", index=True)
    motivo_suspension = db.Column(db.String(255))
    suscripciones = db.relationship("Suscripcion", back_populates="empresa")
    usuarios = db.relationship("Usuario", back_populates="empresa")
    sucursales = db.relationship("Sucursal", back_populates="empresa")
    productos = db.relationship("Producto", back_populates="empresa")
    proveedores = db.relationship("Proveedor", back_populates="empresa")
    configuracion = db.relationship("ConfiguracionEmpresa", back_populates="empresa", uselist=False,
                                    cascade="all, delete-orphan")

    @property
    def suscripcion_actual(self):
        vigentes = [s for s in self.suscripciones if s.esta_vigente()]
        return max(vigentes, key=lambda s: s.fecha_inicio, default=None)

    def esta_activa(self) -> bool:
        return self.estado == "activa" and not self.eliminado

    def suspender(self, motivo: str) -> None:
        self.estado, self.motivo_suspension = "suspendida", motivo


class Suscripcion(TimestampMixin, db.Model):
    __tablename__ = "suscripcion"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_suscripcion_id_empresa"),
        CheckConstraint("estado IN ('prueba','activa','vencida','suspendida','cancelada')",
                        name="ck_suscripcion_estado"),
        CheckConstraint("ciclo IN ('prueba','mensual','anual')", name="ck_suscripcion_ciclo"),
        CheckConstraint("fecha_fin IS NULL OR fecha_fin >= fecha_inicio", name="ck_suscripcion_fechas"),
        Index("ix_suscripcion_empresa_estado", "empresa_id", "estado"),
        Index("uq_suscripcion_empresa_vigente", "empresa_id", unique=True,
              postgresql_where=text("estado IN ('prueba', 'activa')")),
    )
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresa.id"), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("plan_saas.id"), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="prueba")
    ciclo = db.Column(db.String(10), nullable=False, default="prueba")
    fecha_inicio = db.Column(db.DateTime, nullable=False, default=utcnow)
    fecha_fin = db.Column(db.DateTime)
    cancelada_en = db.Column(db.DateTime)
    motivo_cancelacion = db.Column(db.String(255))
    empresa = db.relationship("Empresa", back_populates="suscripciones")
    plan = db.relationship("PlanSaaS", back_populates="suscripciones")
    pagos = db.relationship("Pago", back_populates="suscripcion")

    def esta_vigente(self, ahora: datetime | None = None) -> bool:
        ahora = ahora or utcnow()
        return (self.estado in {"prueba", "activa"} and self.fecha_inicio <= ahora
                and (self.fecha_fin is None or ahora < self.fecha_fin))


class Usuario(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "usuario"
    __table_args__ = (
        UniqueConstraint("id", "empresa_id", name="uq_usuario_id_empresa"),
        CheckConstraint("rol IN ('super_admin','admin_empresa','supervisor','empleado')", name="ck_usuario_rol"),
        CheckConstraint("(rol = 'super_admin' AND empresa_id IS NULL) OR "
                        "(rol <> 'super_admin' AND empresa_id IS NOT NULL)", name="ck_usuario_ambito"),
    )
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresa.id"), index=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100))
    # Globalmente único: el inicio de sesión por correo nunca es ambiguo.
    email = db.Column(db.String(254), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(30), nullable=False, default="empleado", index=True)
    permisos_especiales = db.Column(MutableDict.as_mutable(db.JSON), nullable=False, default=dict)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    email_verificado = db.Column(db.Boolean, nullable=False, default=False)
    intentos_fallidos = db.Column(db.Integer, nullable=False, default=0)
    bloqueado_hasta = db.Column(db.DateTime)
    ultimo_acceso = db.Column(db.DateTime)
    ultimo_cambio_password = db.Column(db.DateTime)
    token_restablecimiento_hash = db.Column(db.String(64), unique=True, index=True)
    token_restablecimiento_expira = db.Column(db.DateTime)
    version_sesion = db.Column(db.Integer, nullable=False, default=1)
    two_factor_enabled = db.Column(db.Boolean, nullable=False, default=False)
    two_factor_secret_encrypted = db.Column(db.Text)
    empresa = db.relationship("Empresa", back_populates="usuarios")
    asignaciones = db.relationship("UsuarioSucursal", back_populates="usuario", cascade="all, delete-orphan",
                                   overlaps="sucursal,usuarios")

    @validates("email")
    def validar_email(self, _key: str, value: str) -> str:
        value = (value or "").strip().lower()
        if "@" not in value:
            raise ValueError("Correo inválido")
        return value

    def set_password(self, password: str) -> None:
        if len(password or "") < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres")
        self.password_hash, self.ultimo_cambio_password = generate_password_hash(password), utcnow()

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def esta_bloqueado(self) -> bool:
        return bool(self.bloqueado_hasta and self.bloqueado_hasta > utcnow())

    def registrar_intento_fallido(self, max_intentos: int = 5, minutos_bloqueo: int = 15) -> None:
        self.intentos_fallidos += 1
        if self.intentos_fallidos >= max_intentos:
            self.bloqueado_hasta = utcnow() + timedelta(minutes=minutos_bloqueo)

    def registrar_acceso(self) -> None:
        self.intentos_fallidos = 0
        self.bloqueado_hasta = None
        self.ultimo_acceso = utcnow()

    def crear_token_restablecimiento(self, minutos_validez: int = 30) -> str:
        token = secrets.token_urlsafe(32)
        self.token_restablecimiento_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        self.token_restablecimiento_expira = utcnow() + timedelta(minutes=minutos_validez)
        return token

    def token_restablecimiento_valido(self, token: str) -> bool:
        if not self.token_restablecimiento_hash or not self.token_restablecimiento_expira:
            return False
        if self.token_restablecimiento_expira <= utcnow():
            return False
        resumen = hashlib.sha256((token or "").encode("utf-8")).hexdigest()
        return hmac.compare_digest(self.token_restablecimiento_hash, resumen)

    def consumir_token_restablecimiento(self, password: str) -> None:
        self.set_password(password)
        self.token_restablecimiento_hash = None
        self.token_restablecimiento_expira = None
        self.version_sesion += 1
        self.intentos_fallidos = 0
        self.bloqueado_hasta = None

    @property
    def is_authenticated(self): return True
    @property
    def is_anonymous(self): return False
    @property
    def is_active(self): return self.activo and not self.eliminado and not self.esta_bloqueado()
    def get_id(self): return f"{self.id}:{self.version_sesion}"


class Sucursal(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "sucursal"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo", name="uq_sucursal_empresa_codigo"),
                      UniqueConstraint("id", "empresa_id", name="uq_sucursal_id_empresa"))
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresa.id"), nullable=False, index=True)
    codigo = db.Column(db.String(30), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    direccion = db.Column(db.String(255))
    ciudad = db.Column(db.String(100))
    telefono = db.Column(db.String(30))
    activa = db.Column(db.Boolean, nullable=False, default=True)
    empresa = db.relationship("Empresa", back_populates="sucursales")
    bodegas = db.relationship("Bodega", back_populates="sucursal")
    usuarios = db.relationship("UsuarioSucursal", back_populates="sucursal", cascade="all, delete-orphan",
                               overlaps="asignaciones,usuario")


class UsuarioSucursal(TimestampMixin, db.Model):
    __tablename__ = "usuario_sucursal"
    __table_args__ = (
        ForeignKeyConstraint(["usuario_id", "empresa_id"], ["usuario.id", "usuario.empresa_id"]),
        ForeignKeyConstraint(["sucursal_id", "empresa_id"], ["sucursal.id", "sucursal.empresa_id"]),
        UniqueConstraint("usuario_id", "sucursal_id", name="uq_usuario_sucursal"),
    )
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, nullable=False, index=True)
    usuario_id = db.Column(db.Integer, nullable=False)
    sucursal_id = db.Column(db.Integer, nullable=False)
    es_principal = db.Column(db.Boolean, nullable=False, default=False)
    usuario = db.relationship("Usuario", back_populates="asignaciones", overlaps="sucursal,usuarios")
    sucursal = db.relationship("Sucursal", back_populates="usuarios", overlaps="asignaciones,usuario")


class Bodega(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "bodega"
    __table_args__ = (
        ForeignKeyConstraint(["sucursal_id", "empresa_id"], ["sucursal.id", "sucursal.empresa_id"]),
        UniqueConstraint("empresa_id", "codigo", name="uq_bodega_empresa_codigo"),
        UniqueConstraint("id", "empresa_id", name="uq_bodega_id_empresa"),
    )
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, nullable=False, index=True)
    sucursal_id = db.Column(db.Integer, nullable=False, index=True)
    codigo = db.Column(db.String(30), nullable=False)
    nombre = db.Column(db.String(120), nullable=False)
    descripcion = db.Column(db.Text)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    sucursal = db.relationship("Sucursal", back_populates="bodegas")
    inventarios = db.relationship("Inventario", back_populates="bodega", overlaps="inventarios,producto")


class ConfiguracionEmpresa(TimestampMixin, db.Model):
    __tablename__ = "configuracion_empresa"
    __table_args__ = (
        CheckConstraint("dias_sin_movimiento BETWEEN 1 AND 3650", name="ck_configuracion_dias_sin_movimiento"),
    )
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresa.id"), nullable=False, unique=True)
    nombre_comercial = db.Column(db.String(150))
    logo_url = db.Column(db.String(500))
    color_principal = db.Column(db.String(7), nullable=False, default="#2563EB")
    alerta_stock_bajo = db.Column(db.Boolean, nullable=False, default=True)
    alerta_sobrestock = db.Column(db.Boolean, nullable=False, default=True)
    dias_sin_movimiento = db.Column(db.Integer, nullable=False, default=90)
    opciones = db.Column(MutableDict.as_mutable(db.JSON), nullable=False, default=dict)
    empresa = db.relationship("Empresa", back_populates="configuracion")


class Proveedor(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "proveedor"
    __table_args__ = (
        UniqueConstraint("empresa_id", "identificacion_fiscal", name="uq_proveedor_empresa_fiscal"),
        UniqueConstraint("id", "empresa_id", name="uq_proveedor_id_empresa"),
        CheckConstraint("dias_entrega >= 0", name="ck_proveedor_dias_entrega"),
    )
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresa.id"), nullable=False, index=True)
    nombre = db.Column(db.String(150), nullable=False)
    identificacion_fiscal = db.Column(db.String(30))
    email = db.Column(db.String(254)); telefono = db.Column(db.String(30))
    direccion = db.Column(db.String(255)); ciudad = db.Column(db.String(100))
    pais = db.Column(db.String(2), nullable=False, default="CL")
    sitio_web = db.Column(db.String(255)); condiciones_pago = db.Column(db.String(120))
    dias_entrega = db.Column(db.Integer, nullable=False, default=7)
    compra_minima = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    observaciones = db.Column(db.Text)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    empresa = db.relationship("Empresa", back_populates="proveedores")
    productos = db.relationship("Producto", back_populates="proveedor_principal", overlaps="empresa,productos")
    ordenes = db.relationship("OrdenCompra", back_populates="proveedor")


class Producto(TimestampMixin, SoftDeleteMixin, db.Model):
    """Maestro del producto; deliberadamente no contiene una columna stock."""
    __tablename__ = "producto"
    __table_args__ = (
        ForeignKeyConstraint(["proveedor_principal_id", "empresa_id"],
                             ["proveedor.id", "proveedor.empresa_id"]),
        UniqueConstraint("empresa_id", "codigo", name="uq_producto_empresa_codigo"),
        UniqueConstraint("empresa_id", "codigo_barras", name="uq_producto_empresa_barras"),
        UniqueConstraint("id", "empresa_id", name="uq_producto_id_empresa"),
        CheckConstraint("costo_referencia >= 0 AND precio_venta >= 0", name="ck_producto_precios"),
        CheckConstraint("stock_minimo >= 0 AND punto_reorden >= 0", name="ck_producto_minimos"),
        CheckConstraint("stock_maximo IS NULL OR stock_maximo >= stock_minimo", name="ck_producto_maximo"),
        Index("ix_producto_empresa_nombre", "empresa_id", "nombre"),
    )
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresa.id"), nullable=False, index=True)
    proveedor_principal_id = db.Column(db.Integer)
    codigo = db.Column(db.String(50), nullable=False); codigo_barras = db.Column(db.String(150))
    nombre = db.Column(db.String(150), nullable=False); descripcion = db.Column(db.Text)
    categoria = db.Column(db.String(100)); subcategoria = db.Column(db.String(100)); marca = db.Column(db.String(100))
    unidad_medida = db.Column(db.String(30), nullable=False, default="unidad")
    unidades_por_caja = db.Column(db.Numeric(12, 3), nullable=False, default=1)
    costo_referencia = db.Column(db.Numeric(14, 4), nullable=False, default=0)
    precio_venta = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    incluye_iva = db.Column(db.Boolean, nullable=False, default=True)
    tasa_impuesto = db.Column(db.Numeric(6, 4), nullable=False, default=Decimal("0.19"))
    stock_minimo = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    punto_reorden = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    stock_maximo = db.Column(db.Numeric(14, 3))
    requiere_serial = db.Column(db.Boolean, nullable=False, default=False)
    controla_lotes = db.Column(db.Boolean, nullable=False, default=False)
    controla_vencimiento = db.Column(db.Boolean, nullable=False, default=False)
    activo = db.Column(db.Boolean, nullable=False, default=True, index=True)
    empresa = db.relationship("Empresa", back_populates="productos", overlaps="productos,proveedor_principal")
    proveedor_principal = db.relationship("Proveedor", back_populates="productos", overlaps="empresa,productos")
    imagenes = db.relationship("ProductoImagen", back_populates="producto", cascade="all, delete-orphan")
    inventarios = db.relationship("Inventario", back_populates="producto", overlaps="bodega,inventarios")

    @property
    def stock_total(self) -> Decimal:
        return sum((i.cantidad for i in self.inventarios), Decimal("0"))

    @property
    def margen_porcentaje(self) -> Decimal:
        return Decimal("0") if not self.precio_venta else \
            ((self.precio_venta - self.costo_referencia) / self.precio_venta) * 100


class ProductoImagen(TimestampMixin, db.Model):
    __tablename__ = "producto_imagen"
    __table_args__ = (ForeignKeyConstraint(["producto_id", "empresa_id"],
                                           ["producto.id", "producto.empresa_id"]),
                      UniqueConstraint("producto_id", "orden", name="uq_imagen_orden"))
    id = db.Column(db.Integer, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False)
    producto_id = db.Column(db.Integer, nullable=False); url = db.Column(db.String(500), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0)
    es_principal = db.Column(db.Boolean, nullable=False, default=False)
    producto = db.relationship("Producto", back_populates="imagenes")


class Inventario(TimestampMixin, db.Model):
    __tablename__ = "inventario"
    __table_args__ = (
        ForeignKeyConstraint(["producto_id", "empresa_id"], ["producto.id", "producto.empresa_id"]),
        ForeignKeyConstraint(["bodega_id", "empresa_id"], ["bodega.id", "bodega.empresa_id"]),
        UniqueConstraint("empresa_id", "bodega_id", "producto_id", name="uq_inventario_producto_bodega"),
        UniqueConstraint("id", "empresa_id", name="uq_inventario_id_empresa"),
        CheckConstraint("cantidad >= 0 AND cantidad_reservada >= 0", name="ck_inventario_cantidades"),
        CheckConstraint("cantidad_reservada <= cantidad", name="ck_inventario_reserva"),
        CheckConstraint("costo_promedio >= 0", name="ck_inventario_costo"),
    )
    id = db.Column(db.Integer, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False, index=True)
    bodega_id = db.Column(db.Integer, nullable=False, index=True)
    producto_id = db.Column(db.Integer, nullable=False, index=True)
    cantidad = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    cantidad_reservada = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    costo_promedio = db.Column(db.Numeric(14, 4), nullable=False, default=0)
    bodega = db.relationship("Bodega", back_populates="inventarios", overlaps="inventarios,producto")
    producto = db.relationship("Producto", back_populates="inventarios", overlaps="bodega,inventarios")
    @property
    def cantidad_disponible(self): return self.cantidad - self.cantidad_reservada


class Lote(TimestampMixin, db.Model):
    __tablename__ = "lote"
    __table_args__ = (
        ForeignKeyConstraint(["producto_id", "empresa_id"], ["producto.id", "producto.empresa_id"]),
        ForeignKeyConstraint(["bodega_id", "empresa_id"], ["bodega.id", "bodega.empresa_id"]),
        UniqueConstraint("empresa_id", "producto_id", "bodega_id", "numero",
                         name="uq_lote_numero_bodega"),
        CheckConstraint("cantidad >= 0", name="ck_lote_cantidad"),
    )
    id = db.Column(db.Integer, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False, index=True)
    producto_id = db.Column(db.Integer, nullable=False); bodega_id = db.Column(db.Integer, nullable=False)
    numero = db.Column(db.String(100), nullable=False); fecha_fabricacion = db.Column(db.Date)
    fecha_vencimiento = db.Column(db.Date, index=True)
    cantidad = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    costo_unitario = db.Column(db.Numeric(14, 4), nullable=False, default=0)
    activo = db.Column(db.Boolean, nullable=False, default=True)


class ProductoSerial(TimestampMixin, db.Model):
    __tablename__ = "producto_serial"
    __table_args__ = (
        ForeignKeyConstraint(["producto_id", "empresa_id"], ["producto.id", "producto.empresa_id"]),
        ForeignKeyConstraint(["bodega_id", "empresa_id"], ["bodega.id", "bodega.empresa_id"]),
        UniqueConstraint("empresa_id", "numero_serial", name="uq_serial_empresa"),
        CheckConstraint("estado IN ('ingresado','disponible','reservado','salido','devuelto','danado','perdido')",
                        name="ck_serial_estado"),
    )
    id = db.Column(db.Integer, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False, index=True)
    producto_id = db.Column(db.Integer, nullable=False); bodega_id = db.Column(db.Integer, nullable=False)
    numero_serial = db.Column(db.String(150), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="ingresado", index=True)
    fecha_ingreso = db.Column(db.DateTime, nullable=False, default=utcnow); fecha_salida = db.Column(db.DateTime)


class OrdenCompra(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "orden_compra"
    __table_args__ = (
        ForeignKeyConstraint(["proveedor_id", "empresa_id"], ["proveedor.id", "proveedor.empresa_id"]),
        ForeignKeyConstraint(["bodega_destino_id", "empresa_id"], ["bodega.id", "bodega.empresa_id"]),
        ForeignKeyConstraint(["creada_por_id", "empresa_id"], ["usuario.id", "usuario.empresa_id"]),
        UniqueConstraint("empresa_id", "numero", name="uq_orden_numero"),
        UniqueConstraint("id", "empresa_id", name="uq_orden_id_empresa"),
        CheckConstraint("estado IN ('borrador','creada','enviada','parcialmente_recibida','recibida','cancelada')",
                        name="ck_orden_estado"),
        CheckConstraint("subtotal >= 0 AND descuento >= 0 AND impuesto >= 0 AND total >= 0",
                        name="ck_orden_totales"),
    )
    id = db.Column(db.Integer, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False, index=True)
    proveedor_id = db.Column(db.Integer, nullable=False); bodega_destino_id = db.Column(db.Integer, nullable=False)
    creada_por_id = db.Column(db.Integer); numero = db.Column(db.String(50), nullable=False)
    estado = db.Column(db.String(30), nullable=False, default="borrador", index=True)
    fecha_orden = db.Column(db.DateTime, nullable=False, default=utcnow); fecha_entrega_esperada = db.Column(db.Date)
    moneda = db.Column(db.String(3), nullable=False, default="CLP")
    subtotal = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    descuento = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    impuesto = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    observaciones = db.Column(db.Text); cancelada_en = db.Column(db.DateTime)
    motivo_cancelacion = db.Column(db.String(255))
    proveedor = db.relationship("Proveedor", back_populates="ordenes")
    items = db.relationship("OrdenCompraItem", back_populates="orden", cascade="all, delete-orphan")
    recepciones = db.relationship("RecepcionCompra", back_populates="orden")


class OrdenCompraItem(TimestampMixin, db.Model):
    __tablename__ = "orden_compra_item"
    __table_args__ = (
        ForeignKeyConstraint(["orden_id", "empresa_id"], ["orden_compra.id", "orden_compra.empresa_id"]),
        ForeignKeyConstraint(["producto_id", "empresa_id"], ["producto.id", "producto.empresa_id"]),
        UniqueConstraint("orden_id", "producto_id", name="uq_orden_producto"),
        UniqueConstraint("id", "empresa_id", name="uq_orden_item_id_empresa"),
        CheckConstraint("cantidad > 0 AND cantidad_recibida >= 0 AND cantidad_recibida <= cantidad",
                        name="ck_orden_item_cantidades"),
        CheckConstraint("precio_unitario >= 0 AND descuento >= 0 AND impuesto >= 0 AND total >= 0",
                        name="ck_orden_item_totales"),
    )
    id = db.Column(db.Integer, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False)
    orden_id = db.Column(db.Integer, nullable=False); producto_id = db.Column(db.Integer, nullable=False)
    cantidad = db.Column(db.Numeric(14, 3), nullable=False)
    cantidad_recibida = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    precio_unitario = db.Column(db.Numeric(14, 4), nullable=False)
    descuento = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    impuesto = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(14, 2), nullable=False)
    orden = db.relationship("OrdenCompra", back_populates="items")
    producto = db.relationship("Producto", overlaps="items,orden")
    recepciones = db.relationship("RecepcionCompraItem", back_populates="orden_item",
                                  overlaps="items,recepcion")


class RecepcionCompra(TimestampMixin, db.Model):
    __tablename__ = "recepcion_compra"
    __table_args__ = (
        ForeignKeyConstraint(["orden_id", "empresa_id"], ["orden_compra.id", "orden_compra.empresa_id"]),
        ForeignKeyConstraint(["bodega_id", "empresa_id"], ["bodega.id", "bodega.empresa_id"]),
        ForeignKeyConstraint(["recibida_por_id", "empresa_id"], ["usuario.id", "usuario.empresa_id"]),
        UniqueConstraint("empresa_id", "numero", name="uq_recepcion_numero"),
        UniqueConstraint("id", "empresa_id", name="uq_recepcion_id_empresa"),
        CheckConstraint("estado IN ('borrador','confirmada','anulada')", name="ck_recepcion_estado"),
    )
    id = db.Column(db.Integer, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False)
    orden_id = db.Column(db.Integer, nullable=False); bodega_id = db.Column(db.Integer, nullable=False)
    recibida_por_id = db.Column(db.Integer); numero = db.Column(db.String(50), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="borrador")
    fecha = db.Column(db.DateTime, nullable=False, default=utcnow)
    documento_referencia = db.Column(db.String(100)); observaciones = db.Column(db.Text)
    orden = db.relationship("OrdenCompra", back_populates="recepciones")
    items = db.relationship("RecepcionCompraItem", back_populates="recepcion",
                            cascade="all, delete-orphan", overlaps="recepciones,orden_item")


class RecepcionCompraItem(TimestampMixin, db.Model):
    __tablename__ = "recepcion_compra_item"
    __table_args__ = (
        ForeignKeyConstraint(["recepcion_id", "empresa_id"],
                             ["recepcion_compra.id", "recepcion_compra.empresa_id"]),
        ForeignKeyConstraint(["orden_item_id", "empresa_id"],
                             ["orden_compra_item.id", "orden_compra_item.empresa_id"]),
        UniqueConstraint("recepcion_id", "orden_item_id", name="uq_recepcion_orden_item"),
        CheckConstraint("cantidad > 0", name="ck_recepcion_item_cantidad"),
        CheckConstraint("costo_unitario >= 0", name="ck_recepcion_item_costo"),
    )
    id = db.Column(db.Integer, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False)
    recepcion_id = db.Column(db.Integer, nullable=False); orden_item_id = db.Column(db.Integer, nullable=False)
    cantidad = db.Column(db.Numeric(14, 3), nullable=False)
    costo_unitario = db.Column(db.Numeric(14, 4), nullable=False)
    numero_lote = db.Column(db.String(100)); fecha_vencimiento = db.Column(db.Date)
    recepcion = db.relationship("RecepcionCompra", back_populates="items",
                                overlaps="recepciones,orden_item")
    orden_item = db.relationship("OrdenCompraItem", back_populates="recepciones",
                                 overlaps="items,recepcion")


class Transferencia(TimestampMixin, db.Model):
    __tablename__ = "transferencia"
    __table_args__ = (
        ForeignKeyConstraint(["bodega_origen_id", "empresa_id"], ["bodega.id", "bodega.empresa_id"]),
        ForeignKeyConstraint(["bodega_destino_id", "empresa_id"], ["bodega.id", "bodega.empresa_id"]),
        ForeignKeyConstraint(["solicitada_por_id", "empresa_id"], ["usuario.id", "usuario.empresa_id"]),
        ForeignKeyConstraint(["despachada_por_id", "empresa_id"], ["usuario.id", "usuario.empresa_id"]),
        ForeignKeyConstraint(["recibida_por_id", "empresa_id"], ["usuario.id", "usuario.empresa_id"]),
        UniqueConstraint("empresa_id", "numero", name="uq_transferencia_numero"),
        UniqueConstraint("id", "empresa_id", name="uq_transferencia_id_empresa"),
        CheckConstraint("bodega_origen_id <> bodega_destino_id", name="ck_transferencia_bodegas"),
        CheckConstraint("estado IN ('borrador','solicitada','en_transito','recibida','cancelada')",
                        name="ck_transferencia_estado"),
    )
    id = db.Column(db.Integer, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False, index=True)
    numero = db.Column(db.String(50), nullable=False)
    bodega_origen_id = db.Column(db.Integer, nullable=False); bodega_destino_id = db.Column(db.Integer, nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="borrador", index=True)
    solicitada_por_id = db.Column(db.Integer); despachada_por_id = db.Column(db.Integer); recibida_por_id = db.Column(db.Integer)
    fecha_solicitud = db.Column(db.DateTime); fecha_despacho = db.Column(db.DateTime); fecha_recepcion = db.Column(db.DateTime)
    observaciones = db.Column(db.Text)
    items = db.relationship("TransferenciaItem", back_populates="transferencia", cascade="all, delete-orphan")


class TransferenciaItem(TimestampMixin, db.Model):
    __tablename__ = "transferencia_item"
    __table_args__ = (
        ForeignKeyConstraint(["transferencia_id", "empresa_id"],
                             ["transferencia.id", "transferencia.empresa_id"]),
        ForeignKeyConstraint(["producto_id", "empresa_id"], ["producto.id", "producto.empresa_id"]),
        UniqueConstraint("transferencia_id", "producto_id", name="uq_transferencia_producto"),
        CheckConstraint("cantidad_solicitada > 0 AND cantidad_despachada >= 0 AND cantidad_recibida >= 0",
                        name="ck_transferencia_cantidades"),
        CheckConstraint("cantidad_despachada <= cantidad_solicitada", name="ck_transferencia_despacho_maximo"),
        CheckConstraint("cantidad_recibida <= cantidad_despachada", name="ck_transferencia_recepcion_maxima"),
    )
    id = db.Column(db.Integer, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False)
    transferencia_id = db.Column(db.Integer, nullable=False); producto_id = db.Column(db.Integer, nullable=False)
    cantidad_solicitada = db.Column(db.Numeric(14, 3), nullable=False)
    cantidad_despachada = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    cantidad_recibida = db.Column(db.Numeric(14, 3), nullable=False, default=0)
    transferencia = db.relationship("Transferencia", back_populates="items")


class Cliente(TimestampMixin, SoftDeleteMixin, db.Model):
    __tablename__ = "cliente"
    __table_args__ = (
        UniqueConstraint("empresa_id", "identificacion_fiscal", name="uq_cliente_empresa_fiscal"),
        UniqueConstraint("id", "empresa_id", name="uq_cliente_id_empresa"),
    )
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresa.id"), nullable=False, index=True)
    nombre = db.Column(db.String(150), nullable=False)
    identificacion_fiscal = db.Column(db.String(30)); email = db.Column(db.String(254))
    telefono = db.Column(db.String(30)); direccion = db.Column(db.String(255))
    activo = db.Column(db.Boolean, nullable=False, default=True)


class Venta(TimestampMixin, db.Model):
    __tablename__ = "venta"
    __table_args__ = (
        ForeignKeyConstraint(["cliente_id", "empresa_id"], ["cliente.id", "cliente.empresa_id"]),
        ForeignKeyConstraint(["bodega_id", "empresa_id"], ["bodega.id", "bodega.empresa_id"]),
        ForeignKeyConstraint(["creada_por_id", "empresa_id"], ["usuario.id", "usuario.empresa_id"]),
        UniqueConstraint("empresa_id", "numero", name="uq_venta_numero"),
        UniqueConstraint("id", "empresa_id", name="uq_venta_id_empresa"),
        CheckConstraint("estado IN ('borrador','reservada','confirmada','cancelada')", name="ck_venta_estado"),
        CheckConstraint("subtotal >= 0 AND descuento >= 0 AND impuesto >= 0 AND total >= 0", name="ck_venta_totales"),
    )
    id = db.Column(db.Integer, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False, index=True)
    cliente_id = db.Column(db.Integer); bodega_id = db.Column(db.Integer, nullable=False)
    creada_por_id = db.Column(db.Integer); numero = db.Column(db.String(50), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="borrador", index=True)
    moneda = db.Column(db.String(3), nullable=False, default="CLP")
    subtotal = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    descuento = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    impuesto = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    observaciones = db.Column(db.Text); confirmada_en = db.Column(db.DateTime)
    cancelada_en = db.Column(db.DateTime); motivo_cancelacion = db.Column(db.String(255))
    items = db.relationship("VentaItem", back_populates="venta", cascade="all, delete-orphan")


class VentaItem(TimestampMixin, db.Model):
    __tablename__ = "venta_item"
    __table_args__ = (
        ForeignKeyConstraint(["venta_id", "empresa_id"], ["venta.id", "venta.empresa_id"]),
        ForeignKeyConstraint(["producto_id", "empresa_id"], ["producto.id", "producto.empresa_id"]),
        UniqueConstraint("venta_id", "producto_id", name="uq_venta_producto"),
        CheckConstraint("cantidad > 0 AND precio_unitario >= 0", name="ck_venta_item_valores"),
        CheckConstraint("descuento >= 0 AND impuesto >= 0 AND total >= 0", name="ck_venta_item_totales"),
    )
    id = db.Column(db.Integer, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False)
    venta_id = db.Column(db.Integer, nullable=False); producto_id = db.Column(db.Integer, nullable=False)
    cantidad = db.Column(db.Numeric(14, 3), nullable=False)
    precio_unitario = db.Column(db.Numeric(14, 2), nullable=False)
    descuento = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    impuesto = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(14, 2), nullable=False)
    venta = db.relationship("Venta", back_populates="items")


class Movimiento(TimestampMixin, db.Model):
    """Libro mayor append-only. cantidad lleva signo y cumple nuevo=anterior+cantidad."""
    __tablename__ = "movimiento"
    __table_args__ = (
        ForeignKeyConstraint(["producto_id", "empresa_id"], ["producto.id", "producto.empresa_id"]),
        ForeignKeyConstraint(["bodega_id", "empresa_id"], ["bodega.id", "bodega.empresa_id"]),
        ForeignKeyConstraint(["usuario_id", "empresa_id"], ["usuario.id", "usuario.empresa_id"]),
        CheckConstraint("tipo IN ('entrada','salida','ajuste','devolucion','transferencia')",
                        name="ck_movimiento_tipo"),
        CheckConstraint("cantidad <> 0", name="ck_movimiento_cantidad"),
        CheckConstraint("stock_anterior >= 0 AND stock_nuevo >= 0", name="ck_movimiento_stock"),
        CheckConstraint("stock_nuevo = stock_anterior + cantidad", name="ck_movimiento_ecuacion"),
        Index("ix_movimiento_empresa_fecha", "empresa_id", "fecha"),
        Index("ix_movimiento_producto_fecha", "producto_id", "fecha"),
    )
    id = db.Column(BIGINT_ID, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False, index=True)
    producto_id = db.Column(db.Integer, nullable=False); bodega_id = db.Column(db.Integer, nullable=False)
    usuario_id = db.Column(db.Integer); tipo = db.Column(db.String(20), nullable=False); subtipo = db.Column(db.String(40))
    cantidad = db.Column(db.Numeric(14, 3), nullable=False)
    stock_anterior = db.Column(db.Numeric(14, 3), nullable=False); stock_nuevo = db.Column(db.Numeric(14, 3), nullable=False)
    costo_unitario = db.Column(db.Numeric(14, 4)); precio_unitario = db.Column(db.Numeric(14, 2))
    referencia_tipo = db.Column(db.String(50)); referencia_id = db.Column(db.BigInteger)
    motivo = db.Column(db.String(255), nullable=False); fecha = db.Column(db.DateTime, nullable=False, default=utcnow)


class AlertaInventario(TimestampMixin, db.Model):
    __tablename__ = "alerta_inventario"
    __table_args__ = (
        ForeignKeyConstraint(["producto_id", "empresa_id"], ["producto.id", "producto.empresa_id"]),
        ForeignKeyConstraint(["bodega_id", "empresa_id"], ["bodega.id", "bodega.empresa_id"]),
        ForeignKeyConstraint(["resuelta_por_id", "empresa_id"], ["usuario.id", "usuario.empresa_id"]),
        CheckConstraint("tipo IN ('stock_bajo','sobrestock','riesgo_agotamiento','sin_movimiento','recomendacion_compra')",
                        name="ck_alerta_tipo"),
        CheckConstraint("estado IN ('activa','resuelta','ignorada')", name="ck_alerta_estado"),
        CheckConstraint("prioridad IN ('baja','media','alta','critica')", name="ck_alerta_prioridad"),
        # Solo una alerta activa por producto/bodega/tipo; conserva todo el historial resuelto.
        Index("uq_alerta_activa", "empresa_id", "producto_id", "bodega_id", "tipo",
              unique=True, postgresql_where=text("estado = 'activa'"),
              sqlite_where=text("estado = 'activa'")),
        Index("ix_alerta_empresa_estado", "empresa_id", "estado"),
    )
    id = db.Column(BIGINT_ID, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False, index=True)
    producto_id = db.Column(db.Integer, nullable=False); bodega_id = db.Column(db.Integer, nullable=False)
    tipo = db.Column(db.String(40), nullable=False); estado = db.Column(db.String(20), nullable=False, default="activa")
    prioridad = db.Column(db.String(15), nullable=False, default="media")
    titulo = db.Column(db.String(150), nullable=False); mensaje = db.Column(db.Text, nullable=False)
    datos = db.Column(MutableDict.as_mutable(db.JSON), nullable=False, default=dict)
    resuelta_por_id = db.Column(db.Integer); resuelta_en = db.Column(db.DateTime)


class Notificacion(TimestampMixin, db.Model):
    __tablename__ = "notificacion"
    __table_args__ = (ForeignKeyConstraint(["usuario_id", "empresa_id"], ["usuario.id", "usuario.empresa_id"]),
                      Index("ix_notificacion_usuario_leida", "usuario_id", "leida"))
    id = db.Column(BIGINT_ID, primary_key=True); empresa_id = db.Column(db.Integer, nullable=False, index=True)
    usuario_id = db.Column(db.Integer, nullable=False); tipo = db.Column(db.String(50), nullable=False)
    titulo = db.Column(db.String(150), nullable=False); mensaje = db.Column(db.Text, nullable=False)
    leida = db.Column(db.Boolean, nullable=False, default=False); leida_en = db.Column(db.DateTime)
    referencia_tipo = db.Column(db.String(50)); referencia_id = db.Column(db.BigInteger)


class Pago(TimestampMixin, db.Model):
    __tablename__ = "pago"
    __table_args__ = (
        ForeignKeyConstraint(["suscripcion_id", "empresa_id"], ["suscripcion.id", "suscripcion.empresa_id"]),
        ForeignKeyConstraint(["solicitud_id", "empresa_id"],
                             ["solicitud_cambio_plan.id", "solicitud_cambio_plan.empresa_id"]),
        CheckConstraint("estado IN ('pendiente','procesando','pagado','rechazado','anulado','reembolsado')",
                        name="ck_pago_estado"),
        CheckConstraint("monto >= 0", name="ck_pago_monto"),
        UniqueConstraint("proveedor", "referencia_externa", name="uq_pago_referencia"),
    )
    id = db.Column(BIGINT_ID, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresa.id"), nullable=False, index=True)
    suscripcion_id = db.Column(db.Integer, nullable=False)
    solicitud_id = db.Column(db.Integer, nullable=False)
    proveedor = db.Column(db.String(50), nullable=False); referencia_externa = db.Column(db.String(150), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="pendiente")
    monto = db.Column(db.Numeric(14, 2), nullable=False); moneda = db.Column(db.String(3), nullable=False, default="CLP")
    metodo = db.Column(db.String(50)); fecha_pago = db.Column(db.DateTime); fecha_confirmacion = db.Column(db.DateTime)
    datos_proveedor = db.Column(MutableDict.as_mutable(db.JSON), nullable=False, default=dict)
    suscripcion = db.relationship("Suscripcion", back_populates="pagos", overlaps="pagos,solicitud")
    solicitud = db.relationship("SolicitudCambioPlan", back_populates="pagos", overlaps="pagos,suscripcion")


class SolicitudCambioPlan(TimestampMixin, db.Model):
    __tablename__ = "solicitud_cambio_plan"
    __table_args__ = (
        CheckConstraint("estado IN ('pendiente','aprobada','rechazada','cancelada')",
                        name="ck_solicitud_estado"),
        ForeignKeyConstraint(["solicitada_por_id", "empresa_id"], ["usuario.id", "usuario.empresa_id"]),
        UniqueConstraint("id", "empresa_id", name="uq_solicitud_plan_id_empresa"),
        CheckConstraint("ciclo IN ('mensual','anual')", name="ck_solicitud_plan_ciclo"),
        CheckConstraint("monto_esperado >= 0", name="ck_solicitud_plan_monto"),
        Index("uq_solicitud_plan_pendiente", "empresa_id", unique=True,
              postgresql_where=text("estado = 'pendiente'"),
              sqlite_where=text("estado = 'pendiente'")),
    )
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresa.id"), nullable=False, index=True)
    plan_solicitado_id = db.Column(db.Integer, db.ForeignKey("plan_saas.id"), nullable=False)
    solicitada_por_id = db.Column(db.Integer); estado = db.Column(db.String(20), nullable=False, default="pendiente")
    ciclo = db.Column(db.String(10), nullable=False)
    monto_esperado = db.Column(db.Numeric(14, 2), nullable=False)
    moneda = db.Column(db.String(3), nullable=False, default="CLP")
    revisada_por_id = db.Column(db.Integer); revisada_en = db.Column(db.DateTime); observacion = db.Column(db.Text)
    pagos = db.relationship("Pago", back_populates="solicitud", overlaps="pagos,suscripcion")


class Auditoria(TimestampMixin, db.Model):
    """Bitácora global/empresarial append-only."""
    __tablename__ = "auditoria"
    __table_args__ = (Index("ix_auditoria_empresa_fecha", "empresa_id", "fecha"),
                      Index("ix_auditoria_entidad", "entidad_tipo", "entidad_id"))
    id = db.Column(BIGINT_ID, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresa.id"), index=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuario.id"), index=True)
    accion = db.Column(db.String(100), nullable=False, index=True); modulo = db.Column(db.String(50), nullable=False)
    entidad_tipo = db.Column(db.String(80)); entidad_id = db.Column(db.BigInteger); descripcion = db.Column(db.Text)
    datos_anteriores = db.Column(db.JSON); datos_nuevos = db.Column(db.JSON)
    ip = db.Column(db.String(45)); agente_usuario = db.Column(db.String(500)); id_solicitud = db.Column(db.String(100), index=True)
    fecha = db.Column(db.DateTime, nullable=False, default=utcnow)


class ClaveApi(TimestampMixin, db.Model):
    __tablename__ = "clave_api"
    __table_args__ = (UniqueConstraint("empresa_id", "prefijo", name="uq_clave_api_prefijo"),)
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey("empresa.id"), nullable=False, index=True)
    nombre = db.Column(db.String(100), nullable=False); prefijo = db.Column(db.String(16), nullable=False)
    secreto_hash = db.Column(db.String(255), nullable=False)
    permisos = db.Column(MutableDict.as_mutable(db.JSON), nullable=False, default=dict)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    ultimo_uso = db.Column(db.DateTime); expira_en = db.Column(db.DateTime)


class LimiteSolicitud(db.Model):
    """Contador distribuido de solicitudes sensibles; no almacena IP en claro."""
    __tablename__ = "limite_solicitud"
    __table_args__ = (
        UniqueConstraint("clave_hash", "ruta", "ventana_inicio", name="uq_limite_solicitud_ventana"),
        CheckConstraint("cantidad >= 1", name="ck_limite_solicitud_cantidad"),
        Index("ix_limite_solicitud_expira", "expira_en"),
    )
    id = db.Column(BIGINT_ID, primary_key=True)
    clave_hash = db.Column(db.String(64), nullable=False)
    ruta = db.Column(db.String(120), nullable=False)
    ventana_inicio = db.Column(db.DateTime, nullable=False)
    expira_en = db.Column(db.DateTime, nullable=False)
    cantidad = db.Column(db.Integer, nullable=False, default=1)


def _inmutable(_mapper: Any, _connection: Any, target: Any) -> None:
    raise ValueError(f"{target.__class__.__name__} es append-only")


for _modelo in (Movimiento, Auditoria):
    event.listen(_modelo, "before_update", _inmutable)
    event.listen(_modelo, "before_delete", _inmutable)


__all__ = ["db", "utcnow", "PlanSaaS", "Empresa", "Suscripcion", "Usuario", "Sucursal",
           "UsuarioSucursal", "Bodega", "ConfiguracionEmpresa", "Proveedor", "Producto",
           "ProductoImagen", "Inventario", "Lote", "ProductoSerial", "OrdenCompra",
           "OrdenCompraItem", "RecepcionCompra", "RecepcionCompraItem", "Transferencia",
           "TransferenciaItem", "Cliente", "Venta", "VentaItem", "Movimiento", "AlertaInventario", "Notificacion", "Pago",
           "SolicitudCambioPlan", "Auditoria", "ClaveApi", "LimiteSolicitud"]