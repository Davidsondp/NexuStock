"""Ventas con reserva y confirmación atómicas."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy.exc import IntegrityError

from ..models import Bodega, Cliente, Inventario, Producto, Venta, VentaItem, db, utcnow
from ..permisos import evaluar_permiso
from .auditoria import registrar_auditoria
from .contexto import ContextoOperacion, sucursales_autorizadas
from .inventario import ServicioInventario, StockInsuficiente, _cantidad_positiva

DOS = Decimal("0.01")


class ErrorVenta(ValueError): codigo = "venta_invalida"
class EstadoVentaInvalido(ErrorVenta): codigo = "estado_venta_invalido"


def _dinero(valor, nombre):
    try: resultado = Decimal(str(valor)).quantize(DOS, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc: raise ErrorVenta(f"{nombre} no es válido") from exc
    if resultado < 0: raise ErrorVenta(f"{nombre} no puede ser negativo")
    return resultado


class ServicioVentas:
    def __init__(self, usuario):
        self.usuario = usuario
        if not usuario.empresa_id or usuario.rol == "super_admin": raise PermissionError("Usuario sin ámbito empresarial")

    def listar(self, estado=None):
        self._exigir("ventas.ver")
        q = db.select(Venta).where(Venta.empresa_id == self.usuario.empresa_id)
        if estado: q = q.where(Venta.estado == estado)
        return list(db.session.scalars(q.order_by(Venta.creado_en.desc())))

    def obtener(self, venta_id, bloquear=False):
        self._exigir("ventas.ver")
        q = db.select(Venta).where(Venta.id == venta_id, Venta.empresa_id == self.usuario.empresa_id)
        venta = db.session.scalar(q.with_for_update() if bloquear else q)
        if not venta: raise PermissionError("Venta no autorizada")
        return venta

    def crear(self, *, numero, bodega_id, items, cliente_id=None, moneda="CLP", observaciones=None):
        self._exigir("ventas.crear")
        numero = (numero or "").strip().upper()
        if not numero or not isinstance(items, list) or not items: raise ErrorVenta("El número y los items son obligatorios")
        bodega = self._bodega(bodega_id)
        if cliente_id and not db.session.scalar(db.select(Cliente).where(Cliente.id == cliente_id,
                Cliente.empresa_id == self.usuario.empresa_id, Cliente.activo.is_(True), Cliente.eliminado.is_(False))):
            raise PermissionError("Cliente fuera del ámbito empresarial")
        try:
            venta = Venta(empresa_id=self.usuario.empresa_id, cliente_id=cliente_id, bodega_id=bodega.id,
                          creada_por_id=self.usuario.id, numero=numero, moneda=(moneda or "CLP").upper(),
                          observaciones=(observaciones or "").strip() or None)
            db.session.add(venta); db.session.flush(); vistos = set()
            for datos in items:
                producto = self._producto(int(datos.get("producto_id", 0)))
                if producto.id in vistos: raise ErrorVenta("No se puede repetir un producto")
                vistos.add(producto.id); cantidad = _cantidad_positiva(datos.get("cantidad"))
                precio = _dinero(datos.get("precio_unitario", producto.precio_venta), "Precio unitario")
                descuento = _dinero(datos.get("descuento", 0), "Descuento")
                impuesto = _dinero(datos.get("impuesto", 0), "Impuesto")
                bruto = (cantidad * precio).quantize(DOS)
                if descuento > bruto: raise ErrorVenta("El descuento supera el subtotal del item")
                venta.items.append(VentaItem(empresa_id=self.usuario.empresa_id, producto_id=producto.id,
                    cantidad=cantidad, precio_unitario=precio, descuento=descuento,
                    impuesto=impuesto, total=bruto-descuento+impuesto))
            venta.subtotal = sum(((Decimal(i.cantidad)*Decimal(i.precio_unitario)).quantize(DOS) for i in venta.items), Decimal(0))
            venta.descuento = sum((Decimal(i.descuento) for i in venta.items), Decimal(0))
            venta.impuesto = sum((Decimal(i.impuesto) for i in venta.items), Decimal(0)); venta.total = venta.subtotal-venta.descuento+venta.impuesto
            db.session.flush(); self._auditar(venta, "borrador_creado"); db.session.commit(); return venta
        except IntegrityError as exc: db.session.rollback(); raise ErrorVenta("El número de venta ya existe") from exc
        except Exception: db.session.rollback(); raise

    def reservar(self, venta_id):
        self._exigir("ventas.reservar"); venta = self.obtener(venta_id, True)
        if venta.estado != "borrador": raise EstadoVentaInvalido("Solo se reserva una venta en borrador")
        try:
            for item in venta.items:
                inv = self._inventario(venta.bodega_id, item.producto_id)
                if Decimal(inv.cantidad)-Decimal(inv.cantidad_reservada) < Decimal(item.cantidad): raise StockInsuficiente("Stock disponible insuficiente para reservar")
                inv.cantidad_reservada = Decimal(inv.cantidad_reservada)+Decimal(item.cantidad)
            venta.estado = "reservada"; self._auditar(venta, "reservada"); db.session.commit(); return venta
        except Exception: db.session.rollback(); raise

    def confirmar(self, venta_id):
        self._exigir("ventas.confirmar"); venta = self.obtener(venta_id, True)
        if venta.estado != "reservada": raise EstadoVentaInvalido("La venta debe estar reservada para confirmarse")
        bodega = self._bodega(venta.bodega_id); contexto = ContextoOperacion(self.usuario.empresa_id, bodega.sucursal, bodega)
        try:
            for item in venta.items:
                inv = self._inventario(venta.bodega_id, item.producto_id)
                if Decimal(inv.cantidad_reservada) < Decimal(item.cantidad): raise ErrorVenta("La reserva de inventario está incompleta")
                inv.cantidad_reservada = Decimal(inv.cantidad_reservada)-Decimal(item.cantidad); db.session.flush()
                ServicioInventario(self.usuario, contexto).salida(producto_id=item.producto_id,
                    cantidad=item.cantidad, precio_unitario=item.precio_unitario,
                    motivo=f"Venta {venta.numero}", referencia_tipo="venta", referencia_id=venta.id, confirmar=False)
            venta.estado = "confirmada"; venta.confirmada_en = utcnow(); self._auditar(venta, "confirmada"); db.session.commit(); return venta
        except Exception: db.session.rollback(); raise

    def cancelar(self, venta_id, motivo):
        self._exigir("ventas.cancelar"); venta = self.obtener(venta_id, True); motivo=(motivo or "").strip()
        if venta.estado not in {"borrador", "reservada"}: raise EstadoVentaInvalido("Una venta confirmada no puede cancelarse")
        if not motivo: raise ErrorVenta("El motivo de cancelación es obligatorio")
        try:
            if venta.estado == "reservada":
                for item in venta.items:
                    inv=self._inventario(venta.bodega_id,item.producto_id)
                    if Decimal(inv.cantidad_reservada) < Decimal(item.cantidad): raise ErrorVenta("La reserva de inventario está incompleta")
                    inv.cantidad_reservada=Decimal(inv.cantidad_reservada)-Decimal(item.cantidad)
            venta.estado="cancelada"; venta.cancelada_en=utcnow(); venta.motivo_cancelacion=motivo
            self._auditar(venta,"cancelada"); db.session.commit(); return venta
        except Exception: db.session.rollback(); raise

    def _inventario(self,bodega_id,producto_id):
        inv=db.session.scalar(db.select(Inventario).where(Inventario.empresa_id==self.usuario.empresa_id,
            Inventario.bodega_id==bodega_id,Inventario.producto_id==producto_id).with_for_update())
        if not inv: raise StockInsuficiente("El producto no tiene existencias en la bodega")
        return inv
    def _producto(self,id):
        p=db.session.scalar(db.select(Producto).where(Producto.id==id,Producto.empresa_id==self.usuario.empresa_id,Producto.activo.is_(True),Producto.eliminado.is_(False)))
        if not p: raise PermissionError("Producto fuera del ámbito empresarial")
        return p
    def _bodega(self,id):
        ids={s.id for s in sucursales_autorizadas(self.usuario)}
        b=db.session.scalar(db.select(Bodega).where(Bodega.id==id,Bodega.empresa_id==self.usuario.empresa_id,Bodega.sucursal_id.in_(ids),Bodega.activa.is_(True),Bodega.eliminado.is_(False)))
        if not b: raise PermissionError("Bodega no autorizada")
        return b
    def _exigir(self,p):
        d=evaluar_permiso(self.usuario,p,empresa_id=self.usuario.empresa_id)
        if not d.permitido: raise PermissionError(d.mensaje)
    def _auditar(self,v,a):
        registrar_auditoria(accion=f"venta.{a}",modulo="ventas",usuario_id=self.usuario.id,empresa_id=self.usuario.empresa_id,entidad_tipo="Venta",entidad_id=v.id,datos_nuevos={"numero":v.numero,"estado":v.estado})