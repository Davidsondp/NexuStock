from decimal import Decimal

import pytest

from app.models import Bodega, Empresa, Inventario, Movimiento, Producto, Sucursal, Usuario, Venta, db
from app.services.contexto import ContextoOperacion
from app.services.inventario import ServicioInventario, StockInsuficiente
from app.services.ventas import EstadoVentaInvalido, ServicioVentas
from tests.test_autenticacion import REGISTRO


def _preparar(app,client):
    client.post("/autenticacion/registro",data=REGISTRO)
    with app.app_context():
        u=db.session.scalar(db.select(Usuario)); b=db.session.scalar(db.select(Bodega).where(Bodega.empresa_id==u.empresa_id))
        p=Producto(empresa_id=u.empresa_id,codigo="V-1",nombre="Vendible",costo_referencia=100,precio_venta=200)
        db.session.add(p);db.session.commit()
        ServicioInventario(u,ContextoOperacion(u.empresa_id,b.sucursal,b)).entrada(producto_id=p.id,cantidad=10,costo_unitario=100,motivo="Inicial")
        return u.id,b.id,p.id


def _crear(ids,cantidad=4,numero="VTA-1"):
    return ServicioVentas(db.session.get(Usuario,ids[0])).crear(numero=numero,bodega_id=ids[1],items=[{"producto_id":ids[2],"cantidad":cantidad,"precio_unitario":200}])


def test_borrador_no_modifica_existencias(app,client):
    ids=_preparar(app,client)
    with app.app_context():
        v=_crear(ids); inv=db.session.scalar(db.select(Inventario))
        assert v.estado=="borrador" and inv.cantidad==10 and inv.cantidad_reservada==0


def test_reservar_y_confirmar_venta(app,client):
    ids=_preparar(app,client)
    with app.app_context():
        s=ServicioVentas(db.session.get(Usuario,ids[0]));v=_crear(ids);s.reservar(v.id)
        inv=db.session.scalar(db.select(Inventario));assert inv.cantidad==10 and inv.cantidad_reservada==4
        s.confirmar(v.id);inv=db.session.scalar(db.select(Inventario))
        assert inv.cantidad==6 and inv.cantidad_reservada==0
        m=db.session.scalar(db.select(Movimiento).where(Movimiento.referencia_tipo=="venta"))
        assert m.cantidad==Decimal("-4.000") and m.precio_unitario==200


def test_reserva_sin_stock_revierte(app,client):
    ids=_preparar(app,client)
    with app.app_context():
        v=_crear(ids,11)
        with pytest.raises(StockInsuficiente): ServicioVentas(db.session.get(Usuario,ids[0])).reservar(v.id)
        assert db.session.get(Venta,v.id).estado=="borrador" and db.session.scalar(db.select(Inventario.cantidad_reservada))==0


def test_cancelar_libera_reserva(app,client):
    ids=_preparar(app,client)
    with app.app_context():
        s=ServicioVentas(db.session.get(Usuario,ids[0]));v=_crear(ids);s.reservar(v.id);s.cancelar(v.id,"Cliente desistió")
        assert db.session.scalar(db.select(Inventario.cantidad_reservada))==0 and db.session.get(Venta,v.id).estado=="cancelada"


def test_confirmada_no_se_cancela(app,client):
    ids=_preparar(app,client)
    with app.app_context():
        s=ServicioVentas(db.session.get(Usuario,ids[0]));v=_crear(ids);s.reservar(v.id);s.confirmar(v.id)
        with pytest.raises(EstadoVentaInvalido): s.cancelar(v.id,"Inválida")


def test_producto_ajeno_es_rechazado(app,client):
    ids=_preparar(app,client)
    with app.app_context():
        e=Empresa(nombre="Ajena",email="venta-ajena@nexustock.cl");db.session.add(e);db.session.flush()
        p=Producto(empresa_id=e.id,codigo="AJ",nombre="Ajeno",costo_referencia=1,precio_venta=2);db.session.add(p);db.session.commit()
        with pytest.raises(PermissionError): ServicioVentas(db.session.get(Usuario,ids[0])).crear(numero="AJ",bodega_id=ids[1],items=[{"producto_id":p.id,"cantidad":1}])


def test_api_venta_en_espanol(app,client):
    ids=_preparar(app,client)
    r=client.post("/api/ventas",json={"numero":"V-API","bodega_id":ids[1],"items":[{"producto_id":ids[2],"cantidad":2}]})
    assert r.status_code==201 and r.get_json()["estado"]=="borrador"
    assert client.post(f"/api/ventas/{r.get_json()['id']}/reservar").get_json()["estado"]=="reservada"