"""Flujo transaccional de transferencias entre bodegas."""
from __future__ import annotations

from decimal import Decimal

from ..models import (Bodega, Movimiento, Producto, Transferencia,
                      TransferenciaItem, UsuarioSucursal, db, utcnow)
from ..permisos import evaluar_permiso
from .auditoria import registrar_auditoria
from .contexto import ContextoOperacion, sucursales_autorizadas
from .inventario import ServicioInventario, _cantidad_positiva


class ErrorTransferencia(ValueError):
    pass


class EstadoTransferenciaInvalido(ErrorTransferencia):
    pass


class ServicioTransferencias:
    def __init__(self, usuario):
        self.usuario = usuario
        if not usuario.empresa_id or usuario.rol == "super_admin":
            raise PermissionError("Usuario sin ámbito empresarial")

    def crear(self, *, numero: str, bodega_origen_id: int, bodega_destino_id: int,
              items: list[dict], observaciones=None) -> Transferencia:
        self._exigir("transferencias.crear")
        origen = self._bodega_autorizada(bodega_origen_id)
        destino = self._bodega_autorizada(bodega_destino_id)
        if origen.id == destino.id:
            raise ErrorTransferencia("Las bodegas deben ser diferentes")
        if not (numero or "").strip() or not items:
            raise ErrorTransferencia("Número e items son obligatorios")
        try:
            transferencia = Transferencia(
                empresa_id=self.usuario.empresa_id, numero=numero.strip().upper(),
                bodega_origen_id=origen.id, bodega_destino_id=destino.id,
                estado="borrador", observaciones=observaciones,
            )
            db.session.add(transferencia); db.session.flush()
            productos_vistos = set()
            for datos in items:
                producto_id = int(datos["producto_id"])
                if producto_id in productos_vistos:
                    raise ErrorTransferencia("No se puede repetir un producto")
                producto = db.session.scalar(db.select(Producto).where(
                    Producto.id == producto_id, Producto.empresa_id == self.usuario.empresa_id,
                    Producto.activo.is_(True), Producto.eliminado.is_(False)))
                if not producto:
                    raise PermissionError("Producto fuera del ámbito empresarial")
                productos_vistos.add(producto_id)
                db.session.add(TransferenciaItem(
                    empresa_id=self.usuario.empresa_id, transferencia_id=transferencia.id,
                    producto_id=producto_id,
                    cantidad_solicitada=_cantidad_positiva(datos["cantidad"]),
                    cantidad_despachada=0, cantidad_recibida=0,
                ))
            self._auditar(transferencia, "creada")
            db.session.commit()
            return transferencia
        except Exception:
            db.session.rollback(); raise

    def solicitar(self, transferencia_id: int) -> Transferencia:
        transferencia = self._obtener(transferencia_id, bloquear=True)
        self._exigir("transferencias.crear")
        self._cambiar_estado(transferencia, "borrador", "solicitada")
        transferencia.solicitada_por_id = self.usuario.id
        transferencia.fecha_solicitud = utcnow()
        return self._confirmar(transferencia, "solicitada")

    def despachar(self, transferencia_id: int,
                  cantidades: dict[int, Decimal] | None = None) -> Transferencia:
        transferencia = self._obtener(transferencia_id, bloquear=True)
        self._exigir("transferencias.despachar")
        self._cambiar_estado(transferencia, "solicitada", "en_transito")
        origen = self._bodega_autorizada(transferencia.bodega_origen_id)
        contexto = ContextoOperacion(self.usuario.empresa_id, origen.sucursal, origen)
        try:
            for item in transferencia.items:
                cantidad = (_cantidad_positiva(cantidades[item.id]) if cantidades and item.id in cantidades
                            else Decimal(item.cantidad_solicitada))
                if cantidad > item.cantidad_solicitada:
                    raise ErrorTransferencia("No se puede despachar más de lo solicitado")
                ServicioInventario(self.usuario, contexto).transferencia_salida(
                    producto_id=item.producto_id, cantidad=cantidad,
                    motivo=f"Despacho transferencia {transferencia.numero}",
                    referencia_id=transferencia.id,
                    confirmar=False,
                )
                item.cantidad_despachada = cantidad
            transferencia.estado = "en_transito"
            transferencia.despachada_por_id = self.usuario.id
            transferencia.fecha_despacho = utcnow()
            self._auditar(transferencia, "despachada")
            db.session.commit(); return transferencia
        except Exception:
            db.session.rollback(); raise

    def recibir(self, transferencia_id: int,
                cantidades: dict[int, Decimal] | None = None) -> Transferencia:
        transferencia = self._obtener(transferencia_id, bloquear=True)
        self._exigir("transferencias.recibir")
        self._cambiar_estado(transferencia, "en_transito", "recibida")
        destino = self._bodega_autorizada(transferencia.bodega_destino_id)
        contexto = ContextoOperacion(self.usuario.empresa_id, destino.sucursal, destino)
        try:
            for item in transferencia.items:
                cantidad = (_cantidad_positiva(cantidades[item.id]) if cantidades and item.id in cantidades
                            else Decimal(item.cantidad_despachada))
                if cantidad > item.cantidad_despachada:
                    raise ErrorTransferencia("No se puede recibir más de lo despachado")
                movimiento_salida = db.session.scalar(db.select(Movimiento).where(
                    Movimiento.empresa_id == self.usuario.empresa_id,
                    Movimiento.referencia_tipo == "transferencia",
                    Movimiento.referencia_id == transferencia.id,
                    Movimiento.producto_id == item.producto_id,
                    Movimiento.bodega_id == transferencia.bodega_origen_id,
                ))
                ServicioInventario(self.usuario, contexto).transferencia_entrada(
                    producto_id=item.producto_id, cantidad=cantidad,
                    costo_unitario=movimiento_salida.costo_unitario,
                    motivo=f"Recepción transferencia {transferencia.numero}",
                    referencia_id=transferencia.id,
                    confirmar=False,
                )
                item.cantidad_recibida = cantidad
            transferencia.estado = "recibida"
            transferencia.recibida_por_id = self.usuario.id
            transferencia.fecha_recepcion = utcnow()
            self._auditar(transferencia, "recibida")
            db.session.commit(); return transferencia
        except Exception:
            db.session.rollback(); raise

    def cancelar(self, transferencia_id: int, motivo: str) -> Transferencia:
        transferencia = self._obtener(transferencia_id, bloquear=True)
        self._exigir("transferencias.crear")
        if transferencia.estado not in {"borrador", "solicitada"}:
            raise EstadoTransferenciaInvalido("Solo se cancela antes del despacho")
        transferencia.estado = "cancelada"
        transferencia.observaciones = motivo
        return self._confirmar(transferencia, "cancelada")

    def _exigir(self, permiso: str) -> None:
        decision = evaluar_permiso(self.usuario, permiso, empresa_id=self.usuario.empresa_id)
        if not decision.permitido:
            raise PermissionError(decision.mensaje)

    def _bodega_autorizada(self, bodega_id: int) -> Bodega:
        sucursales_ids = {s.id for s in sucursales_autorizadas(self.usuario)}
        bodega = db.session.scalar(db.select(Bodega).where(
            Bodega.id == bodega_id, Bodega.empresa_id == self.usuario.empresa_id,
            Bodega.sucursal_id.in_(sucursales_ids), Bodega.activa.is_(True),
            Bodega.eliminado.is_(False)))
        if not bodega:
            raise PermissionError("Bodega no autorizada")
        return bodega

    def _obtener(self, transferencia_id: int, bloquear=False) -> Transferencia:
        consulta = db.select(Transferencia).where(
            Transferencia.id == transferencia_id,
            Transferencia.empresa_id == self.usuario.empresa_id)
        if bloquear:
            consulta = consulta.with_for_update()
        transferencia = db.session.scalar(consulta)
        if not transferencia:
            raise PermissionError("Transferencia no autorizada")
        return transferencia

    @staticmethod
    def _cambiar_estado(transferencia, esperado, nuevo):
        if transferencia.estado != esperado:
            raise EstadoTransferenciaInvalido(
                f"La transferencia debe estar {esperado} para pasar a {nuevo}")
        transferencia.estado = nuevo

    def _auditar(self, transferencia, accion):
        registrar_auditoria(
            accion=f"transferencia.{accion}", modulo="transferencias",
            usuario_id=self.usuario.id, empresa_id=self.usuario.empresa_id,
            entidad_tipo="Transferencia", entidad_id=transferencia.id,
            datos_nuevos={"estado": transferencia.estado},
        )

    def _confirmar(self, transferencia, accion):
        try:
            self._auditar(transferencia, accion)
            db.session.commit(); return transferencia
        except Exception:
            db.session.rollback(); raise
