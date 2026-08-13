from decimal import Decimal

import pytest

from app.models import (Bodega, Empresa, Inventario, Lote, Movimiento, OrdenCompra,
                        Producto, ProductoSerial, Proveedor, RecepcionCompra,
                        Usuario, db)
from app.services.compras import ErrorCompra, EstadoCompraInvalido, ServicioCompras
from tests.test_autenticacion import REGISTRO


def _preparar(app, client, *, trazabilidad=False):
    client.post("/autenticacion/registro", data=REGISTRO)
    with app.app_context():
        usuario = db.session.scalar(db.select(Usuario))
        bodega = db.session.scalar(db.select(Bodega).where(Bodega.empresa_id == usuario.empresa_id))
        proveedor = Proveedor(empresa_id=usuario.empresa_id, nombre="Proveedor Uno", activo=True)
        producto = Producto(empresa_id=usuario.empresa_id, codigo="COMP-1", nombre="Comprable",
                            costo_referencia=100, precio_venta=200,
                            controla_lotes=trazabilidad, controla_vencimiento=trazabilidad,
                            requiere_serial=trazabilidad)
        db.session.add_all([proveedor, producto]); db.session.commit()
        return usuario.id, bodega.id, proveedor.id, producto.id


def _crear(ids, *, numero="OC-001", cantidad=10, precio=100):
    return ServicioCompras(db.session.get(Usuario, ids[0])).crear(
        numero=numero, proveedor_id=ids[2], bodega_destino_id=ids[1],
        items=[{"producto_id": ids[3], "cantidad": cantidad,
                "precio_unitario": precio, "descuento": 100, "impuesto": 190}])


def _enviar(servicio, orden):
    servicio.confirmar(orden.id)
    return servicio.enviar(orden.id)


def test_crear_borrador_calcula_totales_sin_modificar_stock(app, client):
    ids = _preparar(app, client)
    with app.app_context():
        orden = _crear(ids)
        assert orden.estado == "borrador" and orden.subtotal == 1000 and orden.total == 1090
        assert db.session.scalar(db.select(db.func.count(Inventario.id))) == 0
        assert db.session.scalar(db.select(db.func.count(Movimiento.id))) == 0


def test_flujo_recepcion_parcial_y_total_actualiza_stock_y_costo(app, client):
    ids = _preparar(app, client)
    with app.app_context():
        servicio = ServicioCompras(db.session.get(Usuario, ids[0]))
        orden = _crear(ids); _enviar(servicio, orden); item_id = orden.items[0].id
        primera = servicio.recibir(orden.id, numero="RC-001",
            items=[{"orden_item_id": item_id, "cantidad": 4, "costo_unitario": 100}])
        assert primera.estado == "confirmada"
        assert db.session.get(OrdenCompra, orden.id).estado == "parcialmente_recibida"
        servicio.recibir(orden.id, numero="RC-002",
            items=[{"orden_item_id": item_id, "cantidad": 6, "costo_unitario": 200}])
        inventario = db.session.scalar(db.select(Inventario))
        assert db.session.get(OrdenCompra, orden.id).estado == "recibida"
        assert inventario.cantidad == 10 and inventario.costo_promedio == Decimal("160.0000")
        assert db.session.scalar(db.select(db.func.count(Movimiento.id)).where(
            Movimiento.referencia_tipo == "recepcion_compra")) == 2


def test_no_permite_recibir_mas_de_lo_pendiente_y_revierte(app, client):
    ids = _preparar(app, client)
    with app.app_context():
        servicio = ServicioCompras(db.session.get(Usuario, ids[0]))
        orden = _crear(ids); _enviar(servicio, orden)
        with pytest.raises(ErrorCompra):
            servicio.recibir(orden.id, numero="RC-MAYOR", items=[{
                "orden_item_id": orden.items[0].id, "cantidad": 11, "costo_unitario": 100}])
        assert db.session.get(OrdenCompra, orden.id).estado == "enviada"
        assert db.session.scalar(db.select(db.func.count(RecepcionCompra.id))) == 0
        assert db.session.scalar(db.select(db.func.count(Inventario.id))) == 0


def test_recepcion_de_varios_items_es_atomica(app, client):
    ids = _preparar(app, client)
    with app.app_context():
        usuario = db.session.get(Usuario, ids[0])
        segundo = Producto(empresa_id=usuario.empresa_id, codigo="COMP-2",
                           nombre="Segundo", costo_referencia=10, precio_venta=20)
        db.session.add(segundo); db.session.commit()
        servicio = ServicioCompras(usuario)
        orden = servicio.crear(numero="OC-ATOM", proveedor_id=ids[2], bodega_destino_id=ids[1],
            items=[{"producto_id": ids[3], "cantidad": 2, "precio_unitario": 100},
                   {"producto_id": segundo.id, "cantidad": 1, "precio_unitario": 10}])
        _enviar(servicio, orden)
        with pytest.raises(ErrorCompra):
            servicio.recibir(orden.id, numero="RC-ATOM", items=[
                {"orden_item_id": orden.items[0].id, "cantidad": 1},
                {"orden_item_id": orden.items[1].id, "cantidad": 2}])
        assert db.session.scalar(db.select(db.func.count(Inventario.id))) == 0
        assert all(i.cantidad_recibida == 0 for i in db.session.get(OrdenCompra, orden.id).items)


def test_cancelacion_solo_antes_de_recibir(app, client):
    ids = _preparar(app, client)
    with app.app_context():
        servicio = ServicioCompras(db.session.get(Usuario, ids[0]))
        orden = _crear(ids); _enviar(servicio, orden)
        servicio.recibir(orden.id, numero="RC-PARCIAL",
                         items=[{"orden_item_id": orden.items[0].id, "cantidad": 1}])
        with pytest.raises(EstadoCompraInvalido):
            servicio.cancelar(orden.id, "Ya no se necesita")


def test_recepcion_registra_lote_vencimiento_y_seriales(app, client):
    ids = _preparar(app, client, trazabilidad=True)
    with app.app_context():
        servicio = ServicioCompras(db.session.get(Usuario, ids[0]))
        orden = _crear(ids, cantidad=2); _enviar(servicio, orden)
        servicio.recibir(orden.id, numero="RC-TRAZA", items=[{
            "orden_item_id": orden.items[0].id, "cantidad": 2,
            "numero_lote": "LOTE-1", "fecha_vencimiento": "2028-12-31",
            "seriales": ["SER-1", "SER-2"]}])
        lote = db.session.scalar(db.select(Lote))
        assert lote.cantidad == 2 and str(lote.fecha_vencimiento) == "2028-12-31"
        assert set(db.session.scalars(db.select(ProductoSerial.numero_serial))) == {"SER-1", "SER-2"}


def test_trazabilidad_incompleta_revierte_toda_la_recepcion(app, client):
    ids = _preparar(app, client, trazabilidad=True)
    with app.app_context():
        servicio = ServicioCompras(db.session.get(Usuario, ids[0]))
        orden = _crear(ids, cantidad=2); _enviar(servicio, orden)
        with pytest.raises(ErrorCompra):
            servicio.recibir(orden.id, numero="RC-MALA", items=[{
                "orden_item_id": orden.items[0].id, "cantidad": 2,
                "numero_lote": "LOTE-1", "fecha_vencimiento": "2028-12-31",
                "seriales": ["SOLO-UNO"]}])
        assert db.session.scalar(db.select(db.func.count(Lote.id))) == 0
        assert db.session.scalar(db.select(db.func.count(Inventario.id))) == 0


def test_rechaza_proveedor_de_otra_empresa(app, client):
    ids = _preparar(app, client)
    with app.app_context():
        otra = Empresa(nombre="Empresa ajena", email="compras-ajena@nexustock.cl")
        db.session.add(otra); db.session.flush()
        proveedor = Proveedor(empresa_id=otra.id, nombre="Proveedor ajeno")
        db.session.add(proveedor); db.session.commit()
        with pytest.raises(PermissionError):
            ServicioCompras(db.session.get(Usuario, ids[0])).crear(
                numero="OC-AJENA", proveedor_id=proveedor.id, bodega_destino_id=ids[1],
                items=[{"producto_id": ids[3], "cantidad": 1, "precio_unitario": 10}])


def test_api_compras_expone_flujo_en_espanol(app, client):
    ids = _preparar(app, client)
    respuesta = client.post("/api/compras", json={
        "numero": "OC-API", "proveedor_id": ids[2], "bodega_destino_id": ids[1],
        "items": [{"producto_id": ids[3], "cantidad": 2, "precio_unitario": 100}]})
    assert respuesta.status_code == 201 and respuesta.get_json()["estado"] == "borrador"
    orden_id = respuesta.get_json()["id"]
    assert client.post(f"/api/compras/{orden_id}/confirmar").get_json()["estado"] == "creada"