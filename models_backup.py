# ==================================================
# NEXUSTOCK ERP SaaS
# MODELS.PY
# PARTE 1/10
# IMPORTS + DB + MIXINS BASE
# ==================================================


# ==================================================
# IMPORTACIONES
# ==================================================

from datetime import datetime, timedelta

from flask_sqlalchemy import SQLAlchemy

from sqlalchemy import event

from sqlalchemy.orm import validates

import logging


# ==================================================
# CONFIGURACIÓN LOGGER
# ==================================================

logger = logging.getLogger(__name__)


# ==================================================
# INSTANCIA DATABASE
# ==================================================

db = SQLAlchemy()



# ==================================================
# MIXIN BASE
# ==================================================

class BaseModelMixin:
    """
    Campos comunes para todos los modelos.
    """

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )


    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )


    is_deleted = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )


    deleted_at = db.Column(
        db.DateTime,
        nullable=True
    )


    def soft_delete(self):

        self.is_deleted = True
        self.deleted_at = datetime.utcnow()



    def restore(self):

        self.is_deleted = False
        self.deleted_at = None




# ==================================================
# MIXIN CONTACTO
# ==================================================

class ContactoMixin:
    """
    Datos de contacto reutilizables.
    """

    telefono = db.Column(
        db.String(50),
        nullable=True
    )


    email_contacto = db.Column(
        db.String(120),
        nullable=True
    )


    direccion = db.Column(
        db.String(255),
        nullable=True
    )


    ciudad = db.Column(
        db.String(100),
        nullable=True
    )


    pais = db.Column(
        db.String(100),
        default="Chile"
    )



# ==================================================
# FUNCIONES AUXILIARES
# ==================================================
 
def utcnow():
    return datetime.utcnow()


# ==================================================
# NEXUSTOCK ERP SaaS
# MODELS.PY
# PARTE 2/10
# EMPRESA - NÚCLEO SaaS
# ==================================================


class Empresa(BaseModelMixin, db.Model):
    """
    Empresa cliente del sistema SaaS.

    Cada empresa tiene sus propios:
    - usuarios
    - productos
    - movimientos
    - configuraciones
    - pagos
    """

    __tablename__ = "empresa"


    __table_args__ = (

        db.Index(
            "idx_empresa_nombre",
            "nombre"
        ),

        db.Index(
            "idx_empresa_email",
            "email"
        ),

        db.Index(
            "idx_empresa_estado",
            "estado"
        ),

        db.Index(
            "idx_empresa_plan",
            "plan"
        ),

    )


    # ==================================================
    # IDENTIFICACIÓN
    # ==================================================

    id = db.Column(
        db.Integer,
        primary_key=True
    )


    nombre = db.Column(
        db.String(150),
        nullable=False
    )


    identificacion_fiscal = db.Column(
        db.String(50),
        nullable=True
    )


    email = db.Column(
        db.String(120),
        nullable=False,
        unique=True,
        index=True
    )


    telefono = db.Column(
        db.String(50),
        nullable=True
    )


    direccion = db.Column(
        db.String(255),
        nullable=True
    )


    ciudad = db.Column(
        db.String(100),
        nullable=True
    )


    pais = db.Column(
        db.String(100),
        default="Chile"
    )



    # ==================================================
    # SUSCRIPCIÓN SaaS
    # ==================================================

    plan = db.Column(
        db.String(50),
        default="basico",
        nullable=False
    )


    fecha_inicio_plan = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


    fecha_vencimiento = db.Column(
        db.DateTime,
        nullable=True
    )


    estado = db.Column(
        db.String(30),
        default="activo",
        nullable=False
    )


    # ==================================================
    # CONTROL DE LIMITES
    # ==================================================

    limite_productos = db.Column(
        db.Integer,
        default=100
    )


    limite_usuarios = db.Column(
        db.Integer,
        default=5
    )


    limite_movimientos = db.Column(
        db.Integer,
        default=10000
    )


    almacenamiento_mb = db.Column(
        db.Integer,
        default=500
    )



    # ==================================================
    # CONFIGURACIÓN
    # ==================================================

    moneda = db.Column(
        db.String(10),
        default="CLP"
    )


    zona_horaria = db.Column(
        db.String(50),
        default="America/Santiago"
    )


    idioma = db.Column(
        db.String(10),
        default="es"
    )


    logo = db.Column(
        db.String(255),
        nullable=True
    )



    # ==================================================
    # SEGURIDAD
    # ==================================================

    activo = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )


    bloqueada = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )


    motivo_bloqueo = db.Column(
        db.String(255),
        nullable=True
    )



    # ==================================================
    # RELACIONES
    # ==================================================

    usuarios = db.relationship(
        "Usuario",
        back_populates="empresa",
        lazy="select",
        cascade="all, delete-orphan"
    )


    productos = db.relationship(
        "Producto",
        back_populates="empresa",
        lazy="select",
        cascade="all, delete-orphan"
    )


    proveedores = db.relationship(
        "Proveedor",
        back_populates="empresa",
        lazy="select",
        cascade="all, delete-orphan"
    )


    movimientos = db.relationship(
        "Movimiento",
        back_populates="empresa",
        lazy="select",
        cascade="all, delete-orphan"
    )


    pagos = db.relationship(
        "Pago",
        back_populates="empresa",
        lazy="select"
    )


    configuracion = db.relationship(
        "ConfiguracionEmpresa",
        back_populates="empresa",
        uselist=False,
        cascade="all, delete-orphan"
    )



    # ==================================================
    # VALIDACIONES
    # ==================================================

    @validates("nombre")
    def validar_nombre(
        self,
        key,
        nombre
    ):

        if not nombre or not nombre.strip():

            raise ValueError(
                "El nombre de empresa es obligatorio"
            )


        return nombre.strip()



    @validates("estado")
    def validar_estado(
        self,
        key,
        estado
    ):

        estados = [

            "activo",
            "suspendido",
            "cancelado",
            "prueba"

        ]


        if estado not in estados:

            raise ValueError(
                "Estado de empresa inválido"
            )


        return estado



    # ==================================================
    # MÉTODOS SaaS
    # ==================================================

    def puede_agregar_producto(self):

        cantidad = len(
            self.productos
        )

        return cantidad < self.limite_productos



    def puede_agregar_usuario(self):

        cantidad = len(
            self.usuarios
        )

        return cantidad < self.limite_usuarios



    def esta_activa(self):

        if not self.activo:

            return False


        if self.bloqueada:

            return False


        return True



    def dias_restantes_plan(self):

        if not self.fecha_vencimiento:

            return None


        diferencia = (
            self.fecha_vencimiento
            -
            datetime.utcnow()
        )


        return diferencia.days



    def __repr__(self):

        return (
            f"<Empresa {self.nombre}>"
        )

# ==================================================
# NEXUSTOCK ERP SaaS
# MODELS.PY
# PARTE 3/10
# USUARIO - SEGURIDAD Y ROLES
# ==================================================


class Usuario(
    BaseModelMixin,
    ContactoMixin,
    db.Model
):

    """
    Usuario del sistema NexuStock.

    Puede ser:

    - super_admin
    - admin_empresa
    - supervisor
    - empleado

    Cada usuario pertenece a una empresa,
    excepto super_admin.
    """


    __tablename__ = "usuario"



    __table_args__ = (

        db.Index(
            "idx_usuario_empresa",
            "empresa_id"
        ),

        db.Index(
            "idx_usuario_email",
            "email"
        ),

        db.Index(
            "idx_usuario_rol",
            "rol"
        ),

        db.Index(
            "idx_usuario_activo",
            "activo"
        ),

    )



    # ==================================================
    # IDENTIFICACIÓN
    # ==================================================

    id = db.Column(
        db.Integer,
        primary_key=True
    )


    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "empresa.id",
            ondelete="CASCADE"
        ),
        nullable=True,
        index=True
    )



    nombre = db.Column(
        db.String(100),
        nullable=False
    )


    apellido = db.Column(
        db.String(100),
        nullable=True
    )


    email = db.Column(
        db.String(120),
        nullable=False,
        unique=True,
        index=True
    )



    avatar = db.Column(
        db.String(255),
        nullable=True
    )



    # ==================================================
    # PASSWORD
    # ==================================================

    password = db.Column(
        db.String(255),
        nullable=False
    )


    token_reset_password_hash = db.Column(
        db.String(255),
        nullable=True
    )


    token_expiracion = db.Column(
        db.DateTime,
        nullable=True
    )


    ultimo_cambio_password = db.Column(
        db.DateTime,
        nullable=True
    )


    password_expirada = db.Column(
        db.Boolean,
        default=False
    )



    # ==================================================
    # ROLES
    # ==================================================

    rol = db.Column(
        db.String(30),
        default="empleado",
        nullable=False
    )


    permisos_especiales = db.Column(
        db.JSON,
        nullable=True
    )



    # ==================================================
    # SEGURIDAD 2FA
    # ==================================================

    two_factor_enabled = db.Column(
        db.Boolean,
        default=False
    )


    two_factor_secret = db.Column(
        db.String(255),
        nullable=True
    )



    # ==================================================
    # ESTADO CUENTA
    # ==================================================

    activo = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )


    bloqueado = db.Column(
        db.Boolean,
        default=False,
        nullable=False
    )


    motivo_bloqueo = db.Column(
        db.String(255),
        nullable=True
    )


    bloqueado_hasta = db.Column(
        db.DateTime,
        nullable=True
    )



    email_verificado = db.Column(
        db.Boolean,
        default=False
    )



    # ==================================================
    # CONTROL LOGIN
    # ==================================================

    intentos_fallidos = db.Column(
        db.Integer,
        default=0
    )


    ultimo_acceso = db.Column(
        db.DateTime,
        nullable=True
    )


    ultimo_ip = db.Column(
        db.String(45),
        nullable=True
    )


    ultimo_user_agent = db.Column(
        db.Text,
        nullable=True
    )


    sesion_activa = db.Column(
        db.Boolean,
        default=False
    )


    token_sesion = db.Column(
        db.String(255),
        nullable=True
    )



    # ==================================================
    # PREFERENCIAS
    # ==================================================

    idioma = db.Column(
        db.String(10),
        default="es"
    )


    zona_horaria = db.Column(
        db.String(50),
        default="America/Santiago"
    )


    tema = db.Column(
        db.String(20),
        default="light"
    )


    notificaciones_activas = db.Column(
        db.Boolean,
        default=True
    )



    # ==================================================
    # RELACIÓN EMPRESA
    # ==================================================

    empresa = db.relationship(
        "Empresa",
        back_populates="usuarios"
    )



    # ==================================================
    # RELACIONES SISTEMA
    # ==================================================

    movimientos = db.relationship(
        "Movimiento",
        back_populates="usuario",
        foreign_keys="Movimiento.usuario_id"
    )


    auditorias = db.relationship(
        "Auditoria",
        back_populates="usuario",
        foreign_keys="Auditoria.usuario_id"
    )


    notificaciones = db.relationship(
        "Notificacion",
        back_populates="usuario",
        foreign_keys="Notificacion.usuario_id"
    )



    # ==================================================
    # VALIDACIONES
    # ==================================================

    @validates("nombre")
    def validar_nombre(
        self,
        key,
        nombre
    ):

        if not nombre or not nombre.strip():

            raise ValueError(
                "El nombre es obligatorio"
            )

        return nombre.strip()



    @validates("rol")
    def validar_rol(
        self,
        key,
        rol
    ):

        roles_validos = [

            "super_admin",
            "admin_empresa",
            "supervisor",
            "empleado"

        ]


        if rol not in roles_validos:

            raise ValueError(
                "Rol inválido"
            )


        return rol



    # ==================================================
    # SEGURIDAD
    # ==================================================

    def es_super_admin(self):

        return self.rol == "super_admin"



    def tiene_permiso(
        self,
        permiso
    ):

        if self.es_super_admin():

            return True


        if self.permisos_especiales:

            return permiso in self.permisos_especiales


        return False



    def esta_bloqueado(self):

        if not self.bloqueado:

            return False


        if self.bloqueado_hasta:

            if datetime.utcnow() > self.bloqueado_hasta:

                self.bloqueado = False

                self.bloqueado_hasta = None

                return False


        return True



    def registrar_fallo_login(self):

        self.intentos_fallidos += 1


        if self.intentos_fallidos >= 5:

            self.bloqueado = True

            self.bloqueado_hasta = (
                datetime.utcnow()
                +
                timedelta(minutes=30)
            )



    def reset_login(self):

        self.intentos_fallidos = 0

        self.bloqueado = False

        self.bloqueado_hasta = None



    def registrar_acceso(
        self,
        ip=None,
        user_agent=None
    ):

        self.ultimo_acceso = datetime.utcnow()

        self.ultimo_ip = ip

        self.ultimo_user_agent = user_agent

        self.sesion_activa = True



    def cerrar_sesion(self):

        self.sesion_activa = False

        self.token_sesion = None



    def __repr__(self):

        return (
            f"<Usuario {self.email} - {self.rol}>"
        )

# ==================================================
# NEXUSTOCK ERP SaaS
# MODELS.PY
# PARTE 4/10
# PROVEEDOR
# ==================================================


class Proveedor(
    BaseModelMixin,
    ContactoMixin,
    db.Model
):

    """
    Proveedor asociado a una empresa.

    Cada empresa SaaS administra
    sus propios proveedores.
    """


    __tablename__ = "proveedor"



    __table_args__ = (

        db.Index(
            "idx_proveedor_nombre",
            "nombre"
        ),

        db.Index(
            "idx_proveedor_categoria",
            "categoria"
        ),

        db.Index(
            "idx_proveedor_activo",
            "activo"
        ),

    )



    # ==================================================
    # IDENTIFICACIÓN
    # ==================================================

    id = db.Column(
        db.Integer,
        primary_key=True
    )


    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "empresa.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    ordenes_compra = db.relationship(
        "OrdenCompra",
        back_populates="proveedor",
        lazy="select"
    )


    nombre = db.Column(
        db.String(150),
        nullable=False
    )


    identificacion_fiscal = db.Column(
        db.String(50),
        nullable=True
    )



    # ==================================================
    # CONTACTO COMERCIAL
    # ==================================================

    email = db.Column(
        db.String(120),
        nullable=True
    )


    telefono = db.Column(
        db.String(50),
        nullable=True
    )


    direccion = db.Column(
        db.String(255),
        nullable=True
    )


    ciudad = db.Column(
        db.String(100),
        nullable=True
    )


    pais = db.Column(
        db.String(100),
        default="Chile"
    )



    # ==================================================
    # INFORMACIÓN COMERCIAL
    # ==================================================

    categoria = db.Column(
        db.String(100),
        nullable=True
    )


    dias_entrega = db.Column(
        db.Integer,
        default=7
    )


    compra_minima = db.Column(
        db.Numeric(12,2),
        default=0
    )


    condiciones_pago = db.Column(
        db.String(100),
        nullable=True
    )


    observaciones = db.Column(
        db.Text,
        nullable=True
    )


    sitio_web = db.Column(
        db.String(200),
        nullable=True
    )



    # ==================================================
    # EVALUACIÓN PROVEEDOR
    # ==================================================

    activo = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )


    calificacion = db.Column(
        db.Float,
        default=0
    )


    total_compras = db.Column(
        db.Integer,
        default=0
    )


    total_gastado = db.Column(
        db.Numeric(12,2),
        default=0
    )


    ultima_compra = db.Column(
        db.DateTime,
        nullable=True
    )



    # ==================================================
    # RELACIÓN EMPRESA
    # ==================================================

    empresa = db.relationship(
        "Empresa",
        back_populates="proveedores"
    )



    # ==================================================
    # RELACIÓN PRODUCTOS
    # ==================================================

    productos = db.relationship(
        "Producto",
        back_populates="proveedor",
        lazy="select"
    )



    # ==================================================
    # VALIDACIONES
    # ==================================================

    @validates("nombre")
    def validar_nombre(
        self,
        key,
        nombre
    ):

        if not nombre or not nombre.strip():

            raise ValueError(
                "El nombre del proveedor es obligatorio"
            )


        return nombre.strip()



    @validates("calificacion")
    def validar_calificacion(
        self,
        key,
        calificacion
    ):

        if calificacion < 0 or calificacion > 5:

            raise ValueError(
                "La calificación debe estar entre 0 y 5"
            )


        return calificacion



    # ==================================================
    # MÉTODOS
    # ==================================================

    def registrar_compra(
        self,
        monto
    ):

        self.total_compras += 1

        self.total_gastado += monto

        self.ultima_compra = datetime.utcnow()



    def desactivar(self):

        self.activo = False



    def __repr__(self):

        return f"<Proveedor {self.nombre}>"

# ==================================================
# PRODUCTO
# ==================================================

class Producto(BaseModelMixin, db.Model):
    """
    Producto del inventario.
    Cada producto pertenece a una empresa.
    """

    __tablename__ = "producto"


    __table_args__ = (

        db.UniqueConstraint(
            "empresa_id",
            "codigo",
            name="uq_producto_codigo_empresa"
        ),

        db.Index(
            "idx_producto_empresa",
            "empresa_id"
        ),

        db.Index(
            "idx_producto_nombre",
            "nombre"
        ),

        db.Index(
            "idx_producto_categoria",
            "categoria"
        ),

        db.Index(
            "idx_producto_stock",
            "stock"
        ),

    )


    id = db.Column(
        db.Integer,
        primary_key=True
    )


    # ==================================================
    # EMPRESA
    # ==================================================

    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "empresa.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    empresa = db.relationship(
    "Empresa",
    back_populates="productos")


    # ==================================================
    # IDENTIFICACIÓN
    # ==================================================

    codigo = db.Column(
        db.String(50),
        nullable=False
    )


    codigo_barras = db.Column(
        db.String(150),
        nullable=True
    )


    nombre = db.Column(
        db.String(150),
        nullable=False
    )


    descripcion = db.Column(
        db.Text,
        nullable=True
    )


    categoria = db.Column(
        db.String(100),
        nullable=True
    )


    subcategoria = db.Column(
        db.String(100),
        nullable=True
    )


    marca = db.Column(
        db.String(100),
        nullable=True
    )


    # ==================================================
    # PROVEEDOR
    # ==================================================

    proveedor_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "proveedor.id"
        ),
        nullable=True,
        index=True
    )


    proveedor = db.relationship(
        "Proveedor",
        back_populates="productos"
    )


    # ==================================================
    # UNIDADES
    # ==================================================

    unidad_medida = db.Column(
        db.String(30),
        default="unidad"
    )


    unidades_por_caja = db.Column(
        db.Integer,
        default=1
    )


    peso = db.Column(
        db.Float,
        nullable=True
    )


    volumen = db.Column(
        db.Float,
        nullable=True
    )


    # ==================================================
    # CONTROL STOCK
    # ==================================================

    stock = db.Column(
        db.Integer,
        default=0,
        nullable=False
    )


    stock_minimo = db.Column(
        db.Integer,
        default=0
    )


    stock_maximo = db.Column(
        db.Integer,
        default=0
    )


    punto_reorden = db.Column(
        db.Integer,
        default=0
    )


    stock_seguridad = db.Column(
        db.Integer,
        default=0
    )


    ubicacion = db.Column(
        db.String(100),
        nullable=True
    )


    # ==================================================
    # INTELIGENCIA INVENTARIO
    # ==================================================

    consumo_promedio_diario = db.Column(
        db.Float,
        default=0
    )


    demanda_estimada = db.Column(
        db.Float,
        default=0
    )


    dias_sin_movimiento = db.Column(
        db.Integer,
        default=0
    )


    tiempo_reposicion_dias = db.Column(
        db.Integer,
        default=7
    )


    ultima_reposicion = db.Column(
        db.DateTime,
        nullable=True
    )


    # ==================================================
    # PRECIOS Y COSTOS
    # ==================================================

    costo_compra = db.Column(
        db.Numeric(12,2),
        default=0
    )


    costo_promedio = db.Column(
        db.Numeric(12,2),
        default=0
    )


    precio_venta = db.Column(
        db.Numeric(12,2),
        default=0
    )


    precio_mayorista = db.Column(
        db.Numeric(12,2),
        default=0
    )


    margen_ganancia = db.Column(
        db.Float,
        default=0
    )


    valor_inventario = db.Column(
        db.Numeric(12,2),
        default=0
    )


    # ==================================================
    # IMPUESTOS CHILE
    # ==================================================

    tasa_iva = db.Column(
        db.Float,
        default=19
    )


    incluye_iva = db.Column(
        db.Boolean,
        default=True
    )


    # ==================================================
    # CONTROL PRODUCTO
    # ==================================================

    activo = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )


    requiere_serial = db.Column(
        db.Boolean,
        default=False
    )


    controla_vencimiento = db.Column(
        db.Boolean,
        default=False
    )


    fecha_vencimiento = db.Column(
        db.Date,
        nullable=True
    )


    # ==================================================
    # IMÁGENES
    # ==================================================

    imagen_principal = db.Column(
        db.String(255),
        nullable=True
    )


    imagenes = db.Column(
        db.JSON,
        nullable=True
    )

# ==================================================
# RELACIONES
# ==================================================

    empresa = db.relationship(
    "Empresa",
    back_populates="productos"
)

    movimientos = db.relationship(
    "Movimiento",
    back_populates="producto",
    lazy="select"
    )

    seriales = db.relationship(
    "ProductoSerial",
    back_populates="producto",
    lazy="select"
)

    alertas = db.relationship(
    "AlertaInventario",
    back_populates="producto",
    lazy="select")


    # ==================================================
    # VALIDACIONES
    # ==================================================

    @validates("nombre")
    def validar_nombre(
        self,
        key,
        nombre
    ):

        if not nombre or not nombre.strip():

            raise ValueError(
                "El nombre del producto es obligatorio"
            )

        return nombre.strip()



    @validates("codigo")
    def validar_codigo(
        self,
        key,
        codigo
    ):

        if not codigo:

            raise ValueError(
                "Código obligatorio"
            )

        return codigo.upper().strip()



    @validates("stock")
    def validar_stock(
        self,
        key,
        stock
    ):

        if stock < 0:

            raise ValueError(
                "El stock no puede ser negativo"
            )

        return stock



    # ==================================================
    # FUNCIONES INVENTARIO
    # ==================================================

    def tiene_stock_bajo(self):

        return self.stock <= self.stock_minimo



    def necesita_reposicion(self):

        return self.stock <= self.punto_reorden



    def calcular_valor_inventario(self):

        self.valor_inventario = (
            self.stock *
            self.costo_promedio
        )

        return self.valor_inventario



    def calcular_margen(self):

        if self.precio_venta > 0:

            self.margen_ganancia = (
                (
                    float(self.precio_venta)
                    -
                    float(self.costo_promedio)
                )
                /
                float(self.precio_venta)
            ) * 100


        return self.margen_ganancia



    def __repr__(self):

        return (
            f"<Producto {self.nombre}>"
        )

# ==================================================
# PRODUCTOS SERIALIZADOS
# ==================================================

class ProductoSerial(
    BaseModelMixin,
    db.Model
):

    """
    Control individual de productos
    con número de serie.
    """

    __tablename__ = "producto_serial"


    id = db.Column(
        db.Integer,
        primary_key=True
    )


    producto_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "producto.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )


    numero_serial = db.Column(
        db.String(150),
        nullable=False,
        unique=True
    )


    estado = db.Column(
        db.String(50),
        default="Disponible"
    )


    fecha_ingreso = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


    producto = db.relationship(
        "Producto",
        back_populates="seriales"
    )


    def __repr__(self):

        return f"<ProductoSerial {self.numero_serial}>"

    
# ==================================================
# ORDEN COMPRA
# ==================================================

class OrdenCompra(BaseModelMixin, db.Model):
    """
    Ordenes de compra realizadas a proveedores.
    """

    __tablename__ = "orden_compra"


    __table_args__ = (

        db.Index(
            "idx_orden_empresa",
            "empresa_id"
        ),

        db.Index(
            "idx_orden_proveedor",
            "proveedor_id"
        ),

        db.Index(
            "idx_orden_estado",
            "estado"
        ),

    )



    id = db.Column(
        db.Integer,
        primary_key=True
    )


    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "empresa.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )


    proveedor_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "proveedor.id"
        ),
        nullable=False
    )


    numero_orden = db.Column(
        db.String(50),
        unique=True,
        nullable=False
    )


    estado = db.Column(
        db.String(30),
        default="pendiente"
    )


    fecha_orden = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )


    fecha_entrega = db.Column(
        db.DateTime,
        nullable=True
    )


    # Valores

    subtotal = db.Column(
        db.Numeric(12,2),
        default=0
    )


    impuesto = db.Column(
        db.Numeric(12,2),
        default=0
    )


    descuento = db.Column(
        db.Numeric(12,2),
        default=0
    )


    total = db.Column(
        db.Numeric(12,2),
        default=0
    )


    moneda = db.Column(
        db.String(10),
        default="CLP"
    )


    observaciones = db.Column(
        db.Text,
        nullable=True
    )



    # Relaciones

    proveedor = db.relationship(
        "Proveedor",
        back_populates="ordenes_compra"
    )


    items = db.relationship(
        "OrdenCompraItem",
        back_populates="orden",
        cascade="all, delete-orphan"
    )



    def calcular_total(self):

        self.subtotal = sum(
            item.total
            for item in self.items
        )


        self.impuesto = (
            self.subtotal * 0.19
        )


        self.total = (
            self.subtotal
            +
            self.impuesto
            -
            self.descuento
        )


        return self.total



    def recibir(self):

        self.estado = "recibido"

        self.fecha_entrega = datetime.utcnow()



    def __repr__(self):

        return (
            f"<Orden {self.numero_orden}>"
        )



# ==================================================
# ITEM ORDEN COMPRA
# ==================================================

class OrdenCompraItem(BaseModelMixin, db.Model):

    """
    Productos dentro de una orden de compra.
    """


    __tablename__ = "orden_compra_item"



    id = db.Column(
        db.Integer,
        primary_key=True
    )


    orden_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "orden_compra.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )


    producto_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "producto.id"
        ),
        nullable=False
    )


    cantidad = db.Column(
        db.Integer,
        nullable=False
    )


    cantidad_recibida = db.Column(
        db.Integer,
        default=0
    )


    precio_unitario = db.Column(
        db.Numeric(12,2),
        nullable=False
    )


    descuento = db.Column(
        db.Numeric(12,2),
        default=0
    )


    total = db.Column(
        db.Numeric(12,2),
        default=0
    )


    observaciones = db.Column(
        db.Text,
        nullable=True
    )



    # Relaciones

    orden = db.relationship(
        "OrdenCompra",
        back_populates="items"
    )


    producto = db.relationship(
        "Producto"
    )



    def calcular_total(self):

        self.total = (
            self.cantidad
            *
            self.precio_unitario
        ) - self.descuento


        return self.total



    def __repr__(self):

        return (
            f"<OrdenItem {self.id}>"
        )


# ==================================================
# NEXUSTOCK ERP SaaS
# MODELS - PARTE 7/10
# MOVIMIENTO INVENTARIO
# ==================================================


# ==================================================
# MOVIMIENTO
# ==================================================

class Movimiento(BaseModelMixin, db.Model):
    """
    Registro histórico de todos los movimientos
    de inventario del sistema.

    Controla:
    - Entradas
    - Salidas
    - Ajustes
    - Devoluciones
    - Transferencias

    Cada movimiento queda asociado a:
    - Empresa
    - Producto
    - Usuario
    """

    __tablename__ = "movimiento"


    __table_args__ = (

        db.Index(
            "idx_movimiento_empresa",
            "empresa_id"
        ),

        db.Index(
            "idx_movimiento_producto",
            "producto_id"
        ),

        db.Index(
            "idx_movimiento_usuario",
            "usuario_id"
        ),

        db.Index(
            "idx_movimiento_tipo",
            "tipo"
        ),

        db.Index(
            "idx_movimiento_fecha",
            "fecha"
        ),

    )


    # --------------------------------------------------
    # IDENTIFICACIÓN
    # --------------------------------------------------

    id = db.Column(
        db.Integer,
        primary_key=True
    )


    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "empresa.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )


    producto_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "producto.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )


    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "usuario.id"
        ),
        nullable=True,
        index=True
    )



    # --------------------------------------------------
    # TIPO MOVIMIENTO
    # --------------------------------------------------

    tipo = db.Column(
        db.String(30),
        nullable=False
    )


    subtipo = db.Column(
        db.String(50),
        nullable=True
    )


    cantidad = db.Column(
        db.Integer,
        nullable=False
    )



    # --------------------------------------------------
    # CONTROL STOCK
    # --------------------------------------------------

    stock_anterior = db.Column(
        db.Integer,
        nullable=False
    )


    stock_nuevo = db.Column(
        db.Integer,
        nullable=False
    )



    # --------------------------------------------------
    # VALORES ECONÓMICOS
    # --------------------------------------------------

    costo_unitario = db.Column(
        db.Numeric(12,2),
        default=0
    )


    precio_unitario = db.Column(
        db.Numeric(12,2),
        default=0
    )


    costo_total = db.Column(
        db.Numeric(12,2),
        default=0
    )



    # --------------------------------------------------
    # REFERENCIA
    # --------------------------------------------------

    referencia_tipo = db.Column(
        db.String(50),
        nullable=True
    )


    referencia_id = db.Column(
        db.Integer,
        nullable=True
    )


    referencia = db.Column(
        db.String(150),
        nullable=True
    )


    observacion = db.Column(
        db.Text,
        nullable=True
    )



    # --------------------------------------------------
    # SEGURIDAD
    # --------------------------------------------------

    ip_usuario = db.Column(
        db.String(45),
        nullable=True
    )


    user_agent = db.Column(
        db.Text,
        nullable=True
    )



    # --------------------------------------------------
    # FECHA
    # --------------------------------------------------

    fecha = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )



    # ==================================================
    # VALIDACIONES
    # ==================================================

    @validates("cantidad")
    def validar_cantidad(self,key,cantidad):

        if cantidad <= 0:

            raise ValueError(
                "La cantidad debe ser mayor a cero"
            )

        return cantidad



    @validates("tipo")
    def validar_tipo(
        self,
        key,
        tipo
    ):


        tipos_validos = [

            "entrada",
            "salida",
            "ajuste",
            "devolucion",
            "transferencia"

        ]


        if tipo not in tipos_validos:

            raise ValueError(
                f"Tipo de movimiento inválido: {tipo}"
            )


        return tipo

    # ==================================================
    # RELACIONES
    # ==================================================
    
    # Relación con Empresa (INVERSA)
    empresa = db.relationship(
        "Empresa",
        back_populates="movimientos",
        foreign_keys=[empresa_id]
    )
    
    # Relación con Producto
    producto = db.relationship(
        "Producto",
        back_populates="movimientos",
        foreign_keys=[producto_id]
    )
    
    # Relación con Usuario
    usuario = db.relationship(
        "Usuario",
        back_populates="movimientos",
        foreign_keys=[usuario_id]
    )

    # ==================================================
    # PROPIEDADES
    # ==================================================

    @property
    def diferencia_stock(self):

        return (
            self.stock_nuevo -
            self.stock_anterior
        )



    @property
    def es_entrada(self):

        return self.tipo == "entrada"



    @property
    def es_salida(self):

        return self.tipo == "salida"



    @property
    def es_ajuste(self):

        return self.tipo == "ajuste"



    # ==================================================
    # MÉTODOS
    # ==================================================

    def calcular_costo_total(self):

        self.costo_total = (
            self.cantidad *
            self.costo_unitario
        )

        return self.costo_total



    def obtener_producto(self):

        return Producto.query.get(
            self.producto_id
        )



    def obtener_usuario(self):

        if not self.usuario_id:

            return None


        return Usuario.query.get(
            self.usuario_id
        )



    # ==================================================
    # REPRESENTACIÓN
    # ==================================================

    def __repr__(self):

        return (
            f"<Movimiento "
            f"{self.tipo} "
            f"Producto:{self.producto_id}>"
        )



# ==================================================
# EVENTO AUTOMÁTICO
# ==================================================

@event.listens_for(
    Movimiento,
    "after_insert"
)

def movimiento_creado(
    mapper,
    connection,
    target
):

    logger.info(
        "Movimiento creado: "
        f"{target.tipo} "
        f"Producto {target.producto_id}"
    )


# ==================================================
# NEXUSTOCK ERP SaaS
# MODELS - PARTE 8/10
# PAGOS + PLANES SAAS
# ==================================================


# ==================================================
# PLAN SAAS
# ==================================================

class PlanSaaS(BaseModelMixin, db.Model):
    """
    Planes comerciales de NexuStock.

    Ejemplo:

    Básico
    Profesional
    Empresa

    Define límites y funcionalidades.
    """


    __tablename__ = "planes_saas"


    __table_args__ = (

        db.Index(
            "idx_plan_nombre",
            "nombre"
        ),

        db.Index(
            "idx_plan_activo",
            "activo"
        ),

    )


    id = db.Column(
        db.Integer,
        primary_key=True
    )


    nombre = db.Column(
        db.String(50),
        nullable=False,
        unique=True
    )


    descripcion = db.Column(
        db.Text,
        nullable=True
    )


    caracteristicas = db.Column(
        db.JSON,
        nullable=True
    )



    # --------------------------------------------------
    # PRECIOS
    # --------------------------------------------------

    precio_mensual = db.Column(
        db.Numeric(12,2),
        default=0,
        nullable=False
    )


    precio_anual = db.Column(
        db.Numeric(12,2),
        nullable=True
    )


    moneda = db.Column(
        db.String(10),
        default="CLP"
    )



    # --------------------------------------------------
    # LIMITES
    # --------------------------------------------------

    limite_productos = db.Column(
        db.Integer,
        nullable=True
    )


    limite_usuarios = db.Column(
        db.Integer,
        nullable=True
    )


    limite_movimientos = db.Column(
        db.Integer,
        nullable=True
    )


    almacenamiento_mb = db.Column(
        db.Integer,
        nullable=True
    )

    dias_prueba = db.Column(
    db.Integer,
    default=0
    )

    limite_sucursales = db.Column(
    db.Integer,
    default=1
    )

    # --------------------------------------------------
    # FUNCIONES DISPONIBLES
    # --------------------------------------------------

    tiene_reportes = db.Column(
        db.Boolean,
        default=True
    )


    tiene_exportacion = db.Column(
        db.Boolean,
        default=False
    )


    tiene_ia = db.Column(
        db.Boolean,
        default=False
    )


    tiene_alertas_avanzadas = db.Column(
        db.Boolean,
        default=False
    )


    tiene_api = db.Column(
        db.Boolean,
        default=False
    )


    tiene_multisucursal = db.Column(
        db.Boolean,
        default=False
    )



    # --------------------------------------------------
    # ESTADO
    # --------------------------------------------------

    activo = db.Column(
        db.Boolean,
        default=True,
        nullable=False
    )


    destacado = db.Column(
        db.Boolean,
        default=False
    )


    orden = db.Column(
        db.Integer,
        default=0
    )



    # --------------------------------------------------
    # MÉTODOS
    # --------------------------------------------------

    def tiene_funcion(
        self,
        funcion
    ):

        funciones = {

            "reportes":
                self.tiene_reportes,

            "exportacion":
                self.tiene_exportacion,

            "ia":
                self.tiene_ia,

            "alertas":
                self.tiene_alertas_avanzadas,

            "api":
                self.tiene_api,

            "multisucursal":
                self.tiene_multisucursal

        }


        return funciones.get(
            funcion,
            False
        )


    def __repr__(self):

        return (
            f"<PlanSaaS {self.nombre}>"
        )


# ==================================================
# SOLICITUD CAMBIO DE PLAN
# ==================================================

class SolicitudCambioPlan(BaseModelMixin, db.Model):
    """
    Solicitudes realizadas por las empresas para
    cambiar su plan SaaS.
    """

    __tablename__ = "solicitudes_plan"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "empresa.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )

    plan_actual = db.Column(
        db.String(50),
        nullable=False
    )

    plan_solicitado = db.Column(
        db.String(50),
        nullable=False
    )

    estado = db.Column(
        db.String(30),
        default="pendiente",
        nullable=False
    )

    observacion = db.Column(
        db.Text,
        nullable=True
    )

    fecha_revision = db.Column(
        db.DateTime,
        nullable=True
    )

    revisado_por = db.Column(
        db.Integer,
        db.ForeignKey("usuario.id"),
        nullable=True
    )

    empresa = db.relationship(
        "Empresa"
    )

    revisor = db.relationship(
        "Usuario"
    )

    def __repr__(self):

        return (
            f"<SolicitudCambioPlan "
            f"{self.plan_actual} -> "
            f"{self.plan_solicitado}>"
        )


# ==================================================
# PAGO
# ==================================================

class Pago(BaseModelMixin, db.Model):

    """
    Registro de pagos realizados
    por empresas clientes.
    """


    __tablename__ = "pagos"



    __table_args__ = (

        db.Index(
            "idx_pago_empresa",
            "empresa_id"
        ),

        db.Index(
            "idx_pago_estado",
            "estado"
        ),

        db.Index(
            "idx_pago_fecha",
            "fecha_pago"
        ),

    )



    id = db.Column(
        db.Integer,
        primary_key=True
    )


    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "empresa.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    empresa = db.relationship(
        "Empresa",
        back_populates="pagos"
    )



    plan_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "planes_saas.id"
        ),
        nullable=True
    )



    # --------------------------------------------------
    # INFORMACIÓN PAGO
    # --------------------------------------------------

    monto = db.Column(
        db.Numeric(12,2),
        nullable=False,
        default=0
    )


    moneda = db.Column(
        db.String(10),
        default="CLP"
    )


    metodo_pago = db.Column(
        db.String(50),
        nullable=True
    )


    proveedor_pago = db.Column(
        db.String(50),
        nullable=True
    )


    codigo_transaccion = db.Column(
        db.String(120),
        nullable=True,
        unique=True
    )

    preference_id = db.Column(
    db.String(120),
    nullable=True,
    unique=True
    )



    # --------------------------------------------------
    # ESTADO
    # --------------------------------------------------

    estado = db.Column(
        db.String(30),
        default="pendiente"
    )


    fecha_pago = db.Column(
        db.DateTime,
        nullable=True
    )

    proveedor = db.Column(
    db.String(30),
    nullable=True
    )

    referencia_externa = db.Column(
    db.String(150),
    nullable=True,
    unique=True
    )
    url_pago = db.Column(
    db.Text,
    nullable=True
    )

    fecha_confirmacion = db.Column(
    db.DateTime,
    nullable=True)

    # --------------------------------------------------
    # SUSCRIPCIÓN
    # --------------------------------------------------

    fecha_inicio = db.Column(
        db.Date,
        nullable=True
    )


    fecha_vencimiento = db.Column(
        db.Date,
        nullable=True
    )



    # --------------------------------------------------
    # FACTURACIÓN
    # --------------------------------------------------

    numero_documento = db.Column(
        db.String(50),
        nullable=True
    )


    documento_url = db.Column(
        db.String(255),
        nullable=True
    )



    # --------------------------------------------------
    # CONTROL
    # --------------------------------------------------

    creado_por = db.Column(
        db.Integer,
        db.ForeignKey(
            "usuario.id"
        ),
        nullable=True
    )


    observacion = db.Column(
        db.Text,
        nullable=True
    )



    # --------------------------------------------------
    # MÉTODOS
    # --------------------------------------------------

    def aprobar(
        self
    ):

        self.estado = "pagado"

        self.fecha_pago = datetime.utcnow()



    def rechazar(
        self,
        motivo=None
    ):

        self.estado = "rechazado"

        if motivo:

            self.observacion = motivo



    def esta_vigente(
        self
    ):

        if not self.fecha_vencimiento:

            return False


        return (
            self.fecha_vencimiento
            >=
            datetime.utcnow().date()
        )



    def __repr__(self):

        return (
            f"<Pago "
            f"{self.id} "
            f"{self.estado}>"
        )

# ==================================================
# NEXUSTOCK ERP SaaS
# MODELS - PARTE 9/10
# ALERTAS + CONFIGURACION EMPRESA
# ==================================================


# ==================================================
# ALERTA INVENTARIO
# ==================================================

class AlertaInventario(BaseModelMixin, db.Model):
    """
    Sistema inteligente de alertas de inventario.

    Genera avisos cuando:
    - Stock bajo
    - Sobre stock
    - Riesgo de quiebre
    - Producto sin movimiento
    - Compra recomendada
    """


    __tablename__ = "alerta_inventario"


    __table_args__ = (

        db.Index(
            "idx_alerta_empresa",
            "empresa_id"
        ),

        db.Index(
            "idx_alerta_producto",
            "producto_id"
        ),

        db.Index(
            "idx_alerta_estado",
            "estado"
        ),

        db.Index(
            "idx_alerta_prioridad",
            "prioridad"
        ),

    )


    id = db.Column(
        db.Integer,
        primary_key=True
    )


    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "empresa.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )


    producto_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "producto.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    producto = db.relationship(
    "Producto",
    back_populates="alertas"
)



    # --------------------------------------------------
    # INFORMACION ALERTA
    # --------------------------------------------------

    tipo = db.Column(
        db.String(50),
        nullable=False
    )


    prioridad = db.Column(
        db.String(20),
        default="media"
    )


    titulo = db.Column(
        db.String(150),
        nullable=False
    )


    mensaje = db.Column(
        db.Text,
        nullable=False
    )


    accion_sugerida = db.Column(
        db.Text,
        nullable=True
    )



    # --------------------------------------------------
    # DATOS INVENTARIO
    # --------------------------------------------------

    stock_actual = db.Column(
        db.Integer
    )


    stock_minimo = db.Column(
        db.Integer
    )


    cantidad_recomendada = db.Column(
        db.Integer
    )


    dias_sin_movimiento = db.Column(
        db.Integer
    )



    # --------------------------------------------------
    # ESTADO
    # --------------------------------------------------

    estado = db.Column(
        db.String(30),
        default="pendiente"
    )


    creada_automaticamente = db.Column(
        db.Boolean,
        default=True
    )


    fecha_resolucion = db.Column(
        db.DateTime,
        nullable=True
    )


    resuelta_por = db.Column(
        db.Integer,
        nullable=True
    )



    # --------------------------------------------------
    # METODOS
    # --------------------------------------------------

    def resolver(
        self,
        usuario_id=None
    ):

        self.estado = "resuelta"

        self.fecha_resolucion = datetime.utcnow()

        self.resuelta_por = usuario_id



    def ignorar(self):

        self.estado = "ignorada"



    @staticmethod
    def crear_alertas_producto(
        producto
    ):

        alertas = []


        if producto.stock <= producto.stock_minimo:

            alertas.append({

                "tipo":
                    "STOCK_BAJO",

                "prioridad":
                    "alta",

                "titulo":
                    f"Stock bajo {producto.nombre}",

                "mensaje":
                    (
                    f"Stock actual: "
                    f"{producto.stock}"
                    )

            })



        if (
            producto.stock >=
            producto.stock_maximo
        ):

            alertas.append({

                "tipo":
                    "SOBRE_STOCK",

                "prioridad":
                    "media",

                "titulo":
                    f"Sobre stock {producto.nombre}",

                "mensaje":
                    (
                    f"Stock supera límite permitido"
                    )

            })



        return alertas



    def __repr__(self):

        return (
            f"<AlertaInventario "
            f"{self.tipo}>"
        )



# ==================================================
# CONFIGURACION EMPRESA
# ==================================================

class ConfiguracionEmpresa(BaseModelMixin, db.Model):

    """
    Configuración personalizada
    para cada empresa cliente.
    """


    __tablename__ = "configuracion_empresa"



    id = db.Column(
        db.Integer,
        primary_key=True
    )


    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "empresa.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        unique=True
    )

    empresa = db.relationship(
    "Empresa",
    back_populates="configuracion"
)



    # --------------------------------------------------
    # IDENTIDAD VISUAL
    # --------------------------------------------------

    logo = db.Column(
        db.String(255),
        nullable=True
    )


    nombre_comercial = db.Column(
        db.String(150),
        nullable=True
    )


    color_principal = db.Column(
        db.String(20),
        default="#2563eb"
    )


    color_secundario = db.Column(
        db.String(20),
        default="#10b981"
    )



    # --------------------------------------------------
    # REGIONAL
    # --------------------------------------------------

    moneda = db.Column(
        db.String(10),
        default="CLP"
    )


    simbolo_moneda = db.Column(
        db.String(5),
        default="$"
    )


    zona_horaria = db.Column(
        db.String(50),
        default="America/Santiago"
    )


    idioma = db.Column(
        db.String(10),
        default="es"
    )



    # --------------------------------------------------
    # INVENTARIO
    # --------------------------------------------------

    alerta_stock_bajo = db.Column(
        db.Boolean,
        default=True
    )


    alerta_sobre_stock = db.Column(
        db.Boolean,
        default=True
    )


    dias_sin_movimiento = db.Column(
        db.Integer,
        default=30
    )



    # --------------------------------------------------
    # REPORTES
    # --------------------------------------------------

    incluir_costos = db.Column(
        db.Boolean,
        default=True
    )


    incluir_margenes = db.Column(
        db.Boolean,
        default=True
    )


    formato_exportacion = db.Column(
        db.String(20),
        default="excel"
    )



    # --------------------------------------------------
    # IA Y MODULOS
    # --------------------------------------------------

    modulos_activos = db.Column(
        db.JSON,
        nullable=True
    )


    integraciones = db.Column(
        db.JSON,
        nullable=True
    )



    # --------------------------------------------------
    # METODOS
    # --------------------------------------------------

    def tiene_modulo(
        self,
        modulo
    ):

        if not self.modulos_activos:

            return False


        return (
            modulo
            in
            self.modulos_activos
        )



    def __repr__(self):

        return (
            f"<ConfiguracionEmpresa "
            f"{self.empresa_id}>"
        )

# ==================================================
# NEXUSTOCK ERP SaaS
# MODELS - PARTE 10/10
# NOTIFICACIONES Y AUDITORÍA
# ==================================================


# ==================================================
# NOTIFICACION
# ==================================================

class Notificacion(BaseModelMixin, db.Model):

    """
    Sistema de notificaciones internas.
    """

    __tablename__ = "notificacion"


    __table_args__ = (

        db.Index(
            "idx_notificacion_empresa",
            "empresa_id"
        ),

        db.Index(
            "idx_notificacion_usuario",
            "usuario_id"
        ),

        db.Index(
            "idx_notificacion_tipo",
            "tipo"
        ),

        db.Index(
            "idx_notificacion_estado",
            "leida"
        ),

    )


    id = db.Column(
        db.Integer,
        primary_key=True
    )


    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "empresa.id",
            ondelete="CASCADE"
        ),
        nullable=False,
        index=True
    )


    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "usuario.id"
        ),
        nullable=True,
        index=True
    )


    # --------------------------
    # CONTENIDO
    # --------------------------

    tipo = db.Column(
        db.String(50),
        nullable=False
    )


    titulo = db.Column(
        db.String(150),
        nullable=False
    )


    mensaje = db.Column(
        db.Text,
        nullable=False
    )


    prioridad = db.Column(
        db.String(20),
        default="media"
    )


    # --------------------------
    # ESTADO
    # --------------------------

    leida = db.Column(
        db.Boolean,
        default=False
    )


    fecha_lectura = db.Column(
        db.DateTime,
        nullable=True
    )


    enviada_email = db.Column(
        db.Boolean,
        default=False
    )


    # --------------------------
    # REFERENCIA
    # --------------------------

    referencia_tipo = db.Column(
        db.String(50),
        nullable=True
    )


    referencia_id = db.Column(
        db.Integer,
        nullable=True
    )


    # --------------------------
    # RELACION
    # --------------------------

    usuario = db.relationship(
        "Usuario",
        back_populates="notificaciones"
    )



    def marcar_leida(self):

        self.leida = True

        self.fecha_lectura = datetime.utcnow()



    def __repr__(self):

        return (
            f"<Notificacion {self.tipo}>"
        )


# ==================================================
# AUDITORIA GENERAL
# ==================================================

class Auditoria(BaseModelMixin, db.Model):


    """
    Registro completo de acciones del sistema.
    """

    __tablename__ = "auditoria"



    __table_args__ = (

        db.Index(
            "idx_auditoria_empresa",
            "empresa_id"
        ),

        db.Index(
            "idx_auditoria_usuario",
            "usuario_id"
        ),

        db.Index(
            "idx_auditoria_fecha",
            "created_at"
        ),

    )



    id = db.Column(
        db.Integer,
        primary_key=True
    )



    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "empresa.id",
            ondelete="CASCADE"
        ),
        nullable=True
    )



    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "usuario.id"
        ),
        nullable=True
    )



    accion = db.Column(
        db.String(100),
        nullable=False
    )



    modulo = db.Column(
        db.String(50),
        nullable=True
    )



    descripcion = db.Column(
        db.Text,
        nullable=True
    )



    datos_anteriores = db.Column(
        db.JSON,
        nullable=True
    )



    datos_nuevos = db.Column(
        db.JSON,
        nullable=True
    )



    ip_usuario = db.Column(
        db.String(45),
        nullable=True
    )



    user_agent = db.Column(
        db.Text,
        nullable=True
    )



    fecha = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )



    usuario = db.relationship(
        "Usuario",
        back_populates="auditorias"
    )



    @classmethod
    def crear(
        cls,
        accion,
        empresa_id=None,
        usuario_id=None,
        modulo=None,
        descripcion=None
    ):

        return cls(

            accion=accion,

            empresa_id=empresa_id,

            usuario_id=usuario_id,

            modulo=modulo,

            descripcion=descripcion

        )



    def __repr__(self):

        return (
            f"<Auditoria {self.accion}>"
        )





# ==================================================
# AUDITORIA DE PAGOS
# ==================================================

class AuditoriaPago(BaseModelMixin, db.Model):


    """
    Auditoría financiera del sistema SaaS.
    """

    __tablename__ = "auditoria_pago"



    id = db.Column(
        db.Integer,
        primary_key=True
    )



    empresa_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "empresa.id"
        ),
        nullable=False
    )



    pago_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "pagos.id"
        ),
        nullable=False
    )



    usuario_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "usuario.id"
        ),
        nullable=True
    )



    accion = db.Column(
        db.String(100),
        nullable=False
    )



    descripcion = db.Column(
        db.Text,
        nullable=True
    )



    estado = db.Column(
        db.String(30),
        default="INFO"
    )



    valor_anterior = db.Column(
        db.Text,
        nullable=True
    )



    valor_nuevo = db.Column(
        db.Text,
        nullable=True
    )



    fecha = db.Column(
        db.DateTime,
        default=datetime.utcnow
    )



    def __repr__(self):

        return (
            f"<AuditoriaPago {self.accion}>"
        )
