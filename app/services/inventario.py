"""Única puerta de escritura del inventario de NexuStock."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from sqlalchemy.exc import IntegrityError

from ..models import Bodega, Inventario, Movimiento, Producto, db, utcnow
from ..permisos import evaluar_permiso
from .auditoria import registrar_auditoria
from .contexto import ContextoOperacion

TRES_DECIMALES = Decimal("0.001")
CUATRO_DECIMALES = Decimal("0.0001")


class ErrorInventario(ValueError):
    codigo = "error_inventario"


class StockInsuficiente(ErrorInventario):
    codigo = "stock_insuficiente"


class LimiteMovimientosAlcanzado(ErrorInventario):
    codigo = "limite_movimientos"


@dataclass(frozen=True)
class ResultadoMovimiento:
    inventario_id: int
    movimiento_id: int
    stock_anterior: Decimal
    stock_nuevo: Decimal
    costo_promedio: Decimal


def _decimal(valor, nombre: str, decimales: Decimal) -> Decimal:
    try:
        resultado = Decimal(str(valor)).quantize(decimales, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ErrorInventario(f"{nombre} no es válido") from exc
    return resultado


def _inicio_mes(ahora: datetime) -> datetime:
    return ahora.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _cantidad_positiva(valor) -> Decimal:
    cantidad = _decimal(valor, "Cantidad", TRES_DECIMALES)
    if cantidad <= 0:
        raise ErrorInventario("La cantidad debe ser mayor que cero")
    return cantidad


class ServicioInventario:
    """Ejecuta saldo, movimiento y auditoría en una misma transacción."""

    def __init__(self, usuario, contexto: ContextoOperacion):
        self.usuario = usuario
        self.contexto = contexto
        if usuario.empresa_id != contexto.empresa_id:
            raise PermissionError("El contexto no pertenece al usuario")

    def entrada(self, *, producto_id: int, cantidad, costo_unitario,
                motivo: str, referencia_tipo=None, referencia_id=None,
                confirmar: bool = True) -> ResultadoMovimiento:
        return self._ejecutar("entrada", "stock.entrada", producto_id, _cantidad_positiva(cantidad),
                              costo_unitario=costo_unitario, motivo=motivo,
                              referencia_tipo=referencia_tipo, referencia_id=referencia_id,
                              confirmar=confirmar)

    def salida(self, *, producto_id: int, cantidad, motivo: str, precio_unitario=None,
               referencia_tipo=None, referencia_id=None,
               confirmar: bool = True) -> ResultadoMovimiento:
        return self._ejecutar("salida", "stock.salida", producto_id, -_cantidad_positiva(cantidad),
                              precio_unitario=precio_unitario, motivo=motivo,
                              referencia_tipo=referencia_tipo, referencia_id=referencia_id,
                              confirmar=confirmar)

    def devolucion(self, *, producto_id: int, cantidad, motivo: str, costo_unitario=None,
                   referencia_tipo=None, referencia_id=None,
                   confirmar: bool = True) -> ResultadoMovimiento:
        return self._ejecutar("devolucion", "stock.devolucion", producto_id, _cantidad_positiva(cantidad),
                              costo_unitario=costo_unitario, motivo=motivo,
                              referencia_tipo=referencia_tipo, referencia_id=referencia_id,
                              confirmar=confirmar)

    def transferencia_salida(self, *, producto_id: int, cantidad, motivo: str,
                             referencia_id: int, confirmar: bool = True) -> ResultadoMovimiento:
        return self._ejecutar("transferencia", "stock.transferencia", producto_id,
                              -_cantidad_positiva(cantidad), motivo=motivo,
                              referencia_tipo="transferencia", referencia_id=referencia_id,
                              confirmar=confirmar)

    def transferencia_entrada(self, *, producto_id: int, cantidad, costo_unitario,
                              motivo: str, referencia_id: int,
                              confirmar: bool = True) -> ResultadoMovimiento:
        return self._ejecutar("transferencia", "stock.transferencia", producto_id,
                              _cantidad_positiva(cantidad), costo_unitario=costo_unitario,
                              motivo=motivo, referencia_tipo="transferencia",
                              referencia_id=referencia_id, confirmar=confirmar)

    def ajuste(self, *, producto_id: int, stock_final, motivo: str,
               confirmar: bool = True) -> ResultadoMovimiento:
        producto, inventario = self._obtener_entidades(producto_id)
        objetivo = _decimal(stock_final, "Stock final", TRES_DECIMALES)
        if objetivo < 0:
            raise ErrorInventario("El stock final no puede ser negativo")
        delta = objetivo - Decimal(inventario.cantidad)
        return self._ejecutar("ajuste", "stock.ajuste", producto.id, delta, motivo=motivo,
                              inventario_bloqueado=inventario, confirmar=confirmar)

    def _ejecutar(self, tipo: str, permiso: str, producto_id: int, cantidad, *, motivo: str,
                  costo_unitario=None, precio_unitario=None, referencia_tipo=None,
                  referencia_id=None, inventario_bloqueado=None,
                  confirmar: bool = True) -> ResultadoMovimiento:
        try:
            decision = evaluar_permiso(self.usuario, permiso, empresa_id=self.contexto.empresa_id)
            if not decision.permitido:
                raise PermissionError(decision.mensaje)
            cantidad = _decimal(cantidad, "Cantidad", TRES_DECIMALES)
            if cantidad == 0:
                raise ErrorInventario("La cantidad del movimiento no puede ser cero")
            if not (motivo or "").strip():
                raise ErrorInventario("El motivo es obligatorio")
            self._validar_limite_mensual()
            producto, inventario = self._obtener_entidades(producto_id, inventario_bloqueado)
            anterior = Decimal(inventario.cantidad)
            nuevo = anterior + cantidad
            if nuevo < Decimal(inventario.cantidad_reservada):
                raise StockInsuficiente("Stock disponible insuficiente")

            costo_anterior = Decimal(inventario.costo_promedio)
            costo = (_decimal(costo_unitario, "Costo unitario", CUATRO_DECIMALES)
                     if costo_unitario is not None else costo_anterior)
            if costo < 0:
                raise ErrorInventario("El costo unitario no puede ser negativo")
            if cantidad > 0 and nuevo > 0:
                costo_nuevo = ((anterior * costo_anterior) + (cantidad * costo)) / nuevo
                inventario.costo_promedio = costo_nuevo.quantize(CUATRO_DECIMALES, rounding=ROUND_HALF_UP)
            inventario.cantidad = nuevo

            precio = (_decimal(precio_unitario, "Precio unitario", Decimal("0.01"))
                      if precio_unitario is not None else None)
            if precio is not None and precio < 0:
                raise ErrorInventario("El precio unitario no puede ser negativo")
            movimiento = Movimiento(
                empresa_id=self.contexto.empresa_id, producto_id=producto.id,
                bodega_id=self.contexto.bodega.id, usuario_id=self.usuario.id,
                tipo=tipo, cantidad=cantidad, stock_anterior=anterior, stock_nuevo=nuevo,
                costo_unitario=costo, precio_unitario=precio,
                referencia_tipo=referencia_tipo, referencia_id=referencia_id,
                motivo=motivo.strip(),
            )
            db.session.add(movimiento)
            db.session.flush()
            registrar_auditoria(
                accion=f"inventario.{tipo}", modulo="inventario",
                usuario_id=self.usuario.id, empresa_id=self.contexto.empresa_id,
                entidad_tipo="Movimiento", entidad_id=movimiento.id,
                datos_anteriores={"cantidad": str(anterior)},
                datos_nuevos={"cantidad": str(nuevo), "producto_id": producto.id,
                              "bodega_id": self.contexto.bodega.id},
            )
            if confirmar:
                db.session.commit()
            else:
                db.session.flush()
            return ResultadoMovimiento(inventario.id, movimiento.id, anterior, nuevo,
                                       Decimal(inventario.costo_promedio))
        except Exception:
            db.session.rollback()
            raise

    def _obtener_entidades(self, producto_id: int, inventario_existente=None):
        producto = db.session.scalar(
            db.select(Producto).where(
                Producto.id == producto_id,
                Producto.empresa_id == self.contexto.empresa_id,
                Producto.activo.is_(True), Producto.eliminado.is_(False),
            )
        )
        bodega = db.session.scalar(
            db.select(Bodega).where(
                Bodega.id == self.contexto.bodega.id,
                Bodega.empresa_id == self.contexto.empresa_id,
                Bodega.activa.is_(True), Bodega.eliminado.is_(False),
            )
        )
        if not producto or not bodega:
            raise PermissionError("Producto o bodega fuera del ámbito autorizado")
        inventario = inventario_existente or db.session.scalar(
            db.select(Inventario).where(
                Inventario.empresa_id == self.contexto.empresa_id,
                Inventario.bodega_id == bodega.id,
                Inventario.producto_id == producto.id,
            ).with_for_update()
        )
        if inventario is None:
            inventario = Inventario(empresa_id=self.contexto.empresa_id, bodega_id=bodega.id,
                                    producto_id=producto.id, cantidad=0,
                                    cantidad_reservada=0, costo_promedio=0)
            db.session.add(inventario)
            try:
                db.session.flush()
            except IntegrityError:
                # Una creación concurrente gana; reiniciamos para cargar y bloquear esa fila.
                db.session.rollback()
                raise ErrorInventario("Conflicto concurrente al crear el inventario; reintenta")
        return producto, inventario

    def _validar_limite_mensual(self) -> None:
        suscripcion = self.usuario.empresa.suscripcion_actual
        limite = suscripcion.plan.limite_movimientos_mes
        if limite is None:
            return
        ahora = utcnow()
        cantidad = db.session.scalar(
            db.select(db.func.count(Movimiento.id)).where(
                Movimiento.empresa_id == self.contexto.empresa_id,
                Movimiento.fecha >= _inicio_mes(ahora), Movimiento.fecha <= ahora,
            )
        )
        if cantidad >= limite:
            raise LimiteMovimientosAlcanzado("Se alcanzó el límite mensual de movimientos del plan")
