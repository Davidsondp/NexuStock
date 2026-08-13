"""Órdenes de compra y recepción atómica de mercadería."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy.exc import IntegrityError

from ..models import (Bodega, Lote, OrdenCompra, OrdenCompraItem, Producto,
                      ProductoSerial, Proveedor, RecepcionCompra,
                      RecepcionCompraItem, db, utcnow)
from ..permisos import evaluar_permiso
from .auditoria import registrar_auditoria
from .contexto import ContextoOperacion, sucursales_autorizadas
from .inventario import ServicioInventario, _cantidad_positiva

DOS_DECIMALES = Decimal("0.01")
CUATRO_DECIMALES = Decimal("0.0001")


class ErrorCompra(ValueError):
    codigo = "compra_invalida"


class EstadoCompraInvalido(ErrorCompra):
    codigo = "estado_compra_invalido"


def _decimal_no_negativo(valor, nombre, precision):
    try:
        resultado = Decimal(str(valor)).quantize(precision, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ErrorCompra(f"{nombre} no es válido") from exc
    if resultado < 0:
        raise ErrorCompra(f"{nombre} no puede ser negativo")
    return resultado


def _fecha(valor, nombre):
    if valor in (None, ""):
        return None
    if isinstance(valor, date):
        return valor
    try:
        return date.fromisoformat(str(valor))
    except ValueError as exc:
        raise ErrorCompra(f"{nombre} debe tener formato AAAA-MM-DD") from exc


class ServicioCompras:
    def __init__(self, usuario):
        self.usuario = usuario
        if not usuario.empresa_id or usuario.rol == "super_admin":
            raise PermissionError("Usuario sin ámbito empresarial")

    def listar(self, *, estado=None):
        self._exigir("compras.ver")
        consulta = db.select(OrdenCompra).where(
            OrdenCompra.empresa_id == self.usuario.empresa_id,
            OrdenCompra.eliminado.is_(False),
        )
        if estado:
            consulta = consulta.where(OrdenCompra.estado == estado)
        return list(db.session.scalars(consulta.order_by(OrdenCompra.fecha_orden.desc())))

    def obtener(self, orden_id: int, *, bloquear=False) -> OrdenCompra:
        self._exigir("compras.ver")
        consulta = db.select(OrdenCompra).where(
            OrdenCompra.id == orden_id,
            OrdenCompra.empresa_id == self.usuario.empresa_id,
            OrdenCompra.eliminado.is_(False),
        )
        if bloquear:
            consulta = consulta.with_for_update()
        orden = db.session.scalar(consulta)
        if not orden:
            raise PermissionError("Orden de compra no autorizada")
        return orden

    def crear(self, *, numero: str, proveedor_id: int, bodega_destino_id: int,
              items: list[dict], moneda="CLP", fecha_entrega_esperada=None,
              observaciones=None) -> OrdenCompra:
        self._exigir("compras.crear")
        numero = (numero or "").strip().upper()
        if not numero or not isinstance(items, list) or not items:
            raise ErrorCompra("El número y al menos un item son obligatorios")
        proveedor = self._proveedor(proveedor_id)
        bodega = self._bodega_autorizada(bodega_destino_id)
        moneda = (moneda or "CLP").strip().upper()
        if len(moneda) != 3:
            raise ErrorCompra("La moneda debe usar un código de tres letras")
        try:
            orden = OrdenCompra(
                empresa_id=self.usuario.empresa_id, proveedor_id=proveedor.id,
                bodega_destino_id=bodega.id, creada_por_id=self.usuario.id,
                numero=numero, estado="borrador", moneda=moneda,
                fecha_entrega_esperada=_fecha(fecha_entrega_esperada, "Fecha de entrega"),
                observaciones=(observaciones or "").strip() or None,
            )
            db.session.add(orden); db.session.flush()
            productos_vistos = set()
            for datos in items:
                producto = self._producto(int(datos.get("producto_id", 0)))
                if producto.id in productos_vistos:
                    raise ErrorCompra("No se puede repetir un producto en la orden")
                productos_vistos.add(producto.id)
                cantidad = _cantidad_positiva(datos.get("cantidad"))
                precio = _decimal_no_negativo(datos.get("precio_unitario"), "Precio unitario", CUATRO_DECIMALES)
                descuento = _decimal_no_negativo(datos.get("descuento", 0), "Descuento", DOS_DECIMALES)
                impuesto = _decimal_no_negativo(datos.get("impuesto", 0), "Impuesto", DOS_DECIMALES)
                bruto = (cantidad * precio).quantize(DOS_DECIMALES, rounding=ROUND_HALF_UP)
                if descuento > bruto:
                    raise ErrorCompra("El descuento no puede superar el subtotal del item")
                total = bruto - descuento + impuesto
                orden.items.append(OrdenCompraItem(
                    empresa_id=self.usuario.empresa_id, producto_id=producto.id,
                    cantidad=cantidad, cantidad_recibida=0, precio_unitario=precio,
                    descuento=descuento, impuesto=impuesto, total=total,
                ))
            self._recalcular(orden)
            db.session.flush(); self._auditar(orden, "borrador_creado")
            db.session.commit(); return orden
        except IntegrityError as exc:
            db.session.rollback()
            raise ErrorCompra("El número de orden ya existe o los datos están duplicados") from exc
        except Exception:
            db.session.rollback(); raise

    def confirmar(self, orden_id: int) -> OrdenCompra:
        self._exigir("compras.crear")
        orden = self.obtener(orden_id, bloquear=True)
        return self._transicionar(orden, "borrador", "creada", "creada")

    def enviar(self, orden_id: int) -> OrdenCompra:
        self._exigir("compras.enviar")
        orden = self.obtener(orden_id, bloquear=True)
        return self._transicionar(orden, "creada", "enviada", "enviada")

    def cancelar(self, orden_id: int, motivo: str) -> OrdenCompra:
        self._exigir("compras.cancelar")
        orden = self.obtener(orden_id, bloquear=True)
        motivo = (motivo or "").strip()
        if orden.estado not in {"borrador", "creada", "enviada"}:
            raise EstadoCompraInvalido("Solo se puede cancelar una orden sin recepciones")
        if not motivo:
            raise ErrorCompra("El motivo de cancelación es obligatorio")
        orden.estado, orden.cancelada_en, orden.motivo_cancelacion = "cancelada", utcnow(), motivo
        return self._guardar(orden, "cancelada")

    def recibir(self, orden_id: int, *, numero: str, items: list[dict],
                documento_referencia=None, observaciones=None) -> RecepcionCompra:
        self._exigir("compras.recibir")
        orden = self.obtener(orden_id, bloquear=True)
        if orden.estado not in {"enviada", "parcialmente_recibida"}:
            raise EstadoCompraInvalido("La orden debe estar enviada para recibir mercadería")
        numero = (numero or "").strip().upper()
        if not numero or not isinstance(items, list) or not items:
            raise ErrorCompra("El número y al menos un item recibido son obligatorios")
        bodega = self._bodega_autorizada(orden.bodega_destino_id)
        contexto = ContextoOperacion(self.usuario.empresa_id, bodega.sucursal, bodega)
        try:
            recepcion = RecepcionCompra(
                empresa_id=self.usuario.empresa_id, orden_id=orden.id,
                bodega_id=bodega.id, recibida_por_id=self.usuario.id,
                numero=numero, estado="borrador",
                documento_referencia=(documento_referencia or "").strip() or None,
                observaciones=(observaciones or "").strip() or None,
            )
            db.session.add(recepcion); db.session.flush()
            lineas = {item.id: item for item in orden.items}
            vistos = set()
            for datos in items:
                item_id = int(datos.get("orden_item_id", 0))
                if item_id in vistos or item_id not in lineas:
                    raise ErrorCompra("Item de orden inválido o repetido")
                vistos.add(item_id)
                linea = lineas[item_id]
                cantidad = _cantidad_positiva(datos.get("cantidad"))
                pendiente = Decimal(linea.cantidad) - Decimal(linea.cantidad_recibida)
                if cantidad > pendiente:
                    raise ErrorCompra("La cantidad recibida supera la cantidad pendiente")
                costo = _decimal_no_negativo(datos.get("costo_unitario", linea.precio_unitario),
                                             "Costo unitario", CUATRO_DECIMALES)
                producto = self._producto(linea.producto_id)
                numero_lote = (datos.get("numero_lote") or "").strip() or None
                vencimiento = _fecha(datos.get("fecha_vencimiento"), "Fecha de vencimiento")
                self._validar_y_registrar_trazabilidad(
                    producto, bodega, cantidad, costo, numero_lote, vencimiento,
                    datos.get("seriales") or [],
                )
                recepcion.items.append(RecepcionCompraItem(
                    empresa_id=self.usuario.empresa_id, orden_item_id=linea.id,
                    cantidad=cantidad, costo_unitario=costo,
                    numero_lote=numero_lote, fecha_vencimiento=vencimiento,
                ))
                db.session.flush()
                ServicioInventario(self.usuario, contexto).entrada(
                    producto_id=producto.id, cantidad=cantidad, costo_unitario=costo,
                    motivo=f"Recepción de compra {recepcion.numero}",
                    referencia_tipo="recepcion_compra", referencia_id=recepcion.id,
                    confirmar=False,
                )
                linea.cantidad_recibida = Decimal(linea.cantidad_recibida) + cantidad
            recepcion.estado = "confirmada"
            orden.estado = ("recibida" if all(Decimal(i.cantidad_recibida) == Decimal(i.cantidad)
                                               for i in orden.items)
                            else "parcialmente_recibida")
            self._auditar(orden, "recepcion_confirmada", {"recepcion_id": recepcion.id,
                                                           "estado": orden.estado})
            db.session.commit(); return recepcion
        except IntegrityError as exc:
            db.session.rollback()
            raise ErrorCompra("El número de recepción, lote o serial ya existe") from exc
        except Exception:
            db.session.rollback(); raise

    def _validar_y_registrar_trazabilidad(self, producto, bodega, cantidad, costo,
                                          numero_lote, vencimiento, seriales):
        if (producto.controla_lotes or producto.controla_vencimiento) and not numero_lote:
            raise ErrorCompra("El número de lote es obligatorio para este producto")
        if producto.controla_vencimiento and not vencimiento:
            raise ErrorCompra("La fecha de vencimiento es obligatoria para este producto")
        if numero_lote:
            lote = db.session.scalar(db.select(Lote).where(
                Lote.empresa_id == self.usuario.empresa_id,
                Lote.producto_id == producto.id, Lote.bodega_id == bodega.id,
                Lote.numero == numero_lote).with_for_update())
            if lote:
                if lote.fecha_vencimiento and vencimiento and lote.fecha_vencimiento != vencimiento:
                    raise ErrorCompra("El lote ya existe con otra fecha de vencimiento")
                total = Decimal(lote.cantidad) + cantidad
                lote.costo_unitario = (((Decimal(lote.cantidad) * Decimal(lote.costo_unitario)) +
                                        (cantidad * costo)) / total).quantize(CUATRO_DECIMALES)
                lote.cantidad = total
                lote.fecha_vencimiento = lote.fecha_vencimiento or vencimiento
            else:
                db.session.add(Lote(
                    empresa_id=self.usuario.empresa_id, producto_id=producto.id,
                    bodega_id=bodega.id, numero=numero_lote,
                    fecha_vencimiento=vencimiento, cantidad=cantidad, costo_unitario=costo,
                ))
        seriales = [str(s).strip() for s in seriales if str(s).strip()]
        if producto.requiere_serial:
            if cantidad != cantidad.to_integral_value() or len(seriales) != int(cantidad):
                raise ErrorCompra("Debe informar un serial único por cada unidad recibida")
            if len(set(seriales)) != len(seriales):
                raise ErrorCompra("Los seriales no pueden repetirse")
        elif seriales:
            raise ErrorCompra("Este producto no utiliza números de serie")
        for numero_serial in seriales:
            db.session.add(ProductoSerial(
                empresa_id=self.usuario.empresa_id, producto_id=producto.id,
                bodega_id=bodega.id, numero_serial=numero_serial,
                estado="disponible", fecha_ingreso=utcnow(),
            ))

    def _producto(self, producto_id):
        producto = db.session.scalar(db.select(Producto).where(
            Producto.id == producto_id, Producto.empresa_id == self.usuario.empresa_id,
            Producto.activo.is_(True), Producto.eliminado.is_(False)))
        if not producto:
            raise PermissionError("Producto fuera del ámbito empresarial")
        return producto

    def _proveedor(self, proveedor_id):
        proveedor = db.session.scalar(db.select(Proveedor).where(
            Proveedor.id == proveedor_id, Proveedor.empresa_id == self.usuario.empresa_id,
            Proveedor.activo.is_(True), Proveedor.eliminado.is_(False)))
        if not proveedor:
            raise PermissionError("Proveedor fuera del ámbito empresarial")
        return proveedor

    def _bodega_autorizada(self, bodega_id):
        sucursales_ids = {s.id for s in sucursales_autorizadas(self.usuario)}
        bodega = db.session.scalar(db.select(Bodega).where(
            Bodega.id == bodega_id, Bodega.empresa_id == self.usuario.empresa_id,
            Bodega.sucursal_id.in_(sucursales_ids), Bodega.activa.is_(True),
            Bodega.eliminado.is_(False)))
        if not bodega:
            raise PermissionError("Bodega no autorizada")
        return bodega

    @staticmethod
    def _recalcular(orden):
        orden.subtotal = sum(((Decimal(i.cantidad) * Decimal(i.precio_unitario)).quantize(DOS_DECIMALES)
                              for i in orden.items), Decimal("0"))
        orden.descuento = sum((Decimal(i.descuento) for i in orden.items), Decimal("0"))
        orden.impuesto = sum((Decimal(i.impuesto) for i in orden.items), Decimal("0"))
        orden.total = orden.subtotal - orden.descuento + orden.impuesto

    def _exigir(self, permiso):
        decision = evaluar_permiso(self.usuario, permiso, empresa_id=self.usuario.empresa_id)
        if not decision.permitido:
            raise PermissionError(decision.mensaje)

    def _transicionar(self, orden, esperado, nuevo, accion):
        if orden.estado != esperado:
            raise EstadoCompraInvalido(f"La orden debe estar {esperado} para pasar a {nuevo}")
        orden.estado = nuevo
        return self._guardar(orden, accion)

    def _guardar(self, orden, accion):
        try:
            self._auditar(orden, accion); db.session.commit(); return orden
        except Exception:
            db.session.rollback(); raise

    def _auditar(self, orden, accion, nuevos=None):
        registrar_auditoria(
            accion=f"compra.{accion}", modulo="compras", usuario_id=self.usuario.id,
            empresa_id=self.usuario.empresa_id, entidad_tipo="OrdenCompra", entidad_id=orden.id,
            datos_nuevos=nuevos or {"numero": orden.numero, "estado": orden.estado},
        )