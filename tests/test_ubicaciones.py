import pytest

from app.models import Bodega, Empresa, Inventario, Sucursal, Usuario, UsuarioSucursal, db
from app.services.ubicaciones import (ErrorUbicacion, LimiteBodegasAlcanzado,
                                      LimiteSucursalesAlcanzado, ServicioUbicaciones)
from tests.test_autenticacion import REGISTRO


def _preparar(app, client, funciones=True):
    client.post("/autenticacion/registro", data=REGISTRO)
    with app.app_context():
        usuario = db.session.scalar(db.select(Usuario))
        plan = usuario.empresa.suscripcion_actual.plan
        plan.limite_sucursales = None; plan.limite_bodegas = None
        if funciones:
            plan.funciones = {**plan.funciones, "multisucursal": True, "multibodega": True}
        db.session.commit(); return usuario.id


def test_crear_sucursal_crea_bodega_y_asigna_creador(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        sucursal = ServicioUbicaciones(db.session.get(Usuario, usuario_id)).crear_sucursal(
            codigo="NORTE", nombre="Sucursal Norte")
        assert len(sucursal.bodegas) == 1
        assert db.session.scalar(db.select(db.func.count(UsuarioSucursal.id)).where(
            UsuarioSucursal.sucursal_id == sucursal.id,
            UsuarioSucursal.usuario_id == usuario_id)) == 1


def test_limite_sucursales_y_bodegas(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        usuario = db.session.get(Usuario, usuario_id)
        plan = usuario.empresa.suscripcion_actual.plan
        plan.limite_sucursales = 1; plan.limite_bodegas = 1; db.session.commit()
        servicio = ServicioUbicaciones(usuario)
        with pytest.raises(LimiteSucursalesAlcanzado):
            servicio.crear_sucursal(codigo="DOS", nombre="Dos")
        principal = db.session.scalar(db.select(Sucursal))
        with pytest.raises(LimiteBodegasAlcanzado):
            servicio.crear_bodega(sucursal_id=principal.id, codigo="DOS", nombre="Dos")


def test_plan_sin_multisucursal_rechaza_creacion(app, client):
    usuario_id = _preparar(app, client, funciones=False)
    with app.app_context(), pytest.raises(PermissionError):
        ServicioUbicaciones(db.session.get(Usuario, usuario_id)).crear_sucursal(
            codigo="DOS", nombre="Dos")


def test_no_desactiva_ultima_sucursal_o_bodega(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        servicio = ServicioUbicaciones(db.session.get(Usuario, usuario_id))
        sucursal = db.session.scalar(db.select(Sucursal)); bodega = db.session.scalar(db.select(Bodega))
        with pytest.raises(ErrorUbicacion): servicio.desactivar_sucursal(sucursal.id)
        with pytest.raises(ErrorUbicacion): servicio.desactivar_bodega(bodega.id)


def test_no_desactiva_bodega_con_stock(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        from app.models import Producto
        usuario = db.session.get(Usuario, usuario_id); servicio = ServicioUbicaciones(usuario)
        sucursal = db.session.scalar(db.select(Sucursal))
        bodega = servicio.crear_bodega(sucursal_id=sucursal.id, codigo="DOS", nombre="Dos")
        producto = Producto(empresa_id=usuario.empresa_id, codigo="P", nombre="P",
                            costo_referencia=0, precio_venta=0)
        db.session.add(producto); db.session.flush()
        db.session.add(Inventario(empresa_id=usuario.empresa_id, bodega_id=bodega.id,
                                  producto_id=producto.id, cantidad=1,
                                  cantidad_reservada=0, costo_promedio=0)); db.session.commit()
        with pytest.raises(ErrorUbicacion): servicio.desactivar_bodega(bodega.id)


def test_asignacion_ajena_es_rechazada(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        admin = db.session.get(Usuario, usuario_id)
        otra = Empresa(nombre="Ajena", email="ajena-ubicacion@nexustock.cl")
        db.session.add(otra); db.session.flush()
        ajeno = Usuario(empresa_id=otra.id, nombre="Ajeno", email="ajeno@ubicacion.cl", rol="empleado")
        ajeno.set_password("ClaveAjena123")
        db.session.add(ajeno); db.session.commit(); ajeno_id = ajeno.id
        sucursal = db.session.scalar(db.select(Sucursal).where(Sucursal.empresa_id == admin.empresa_id))
        with pytest.raises(PermissionError):
            ServicioUbicaciones(admin).asignar_usuario(usuario_id=ajeno_id, sucursal_id=sucursal.id)


def test_desasignacion_conserva_una_sucursal(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        usuario = db.session.get(Usuario, usuario_id); servicio = ServicioUbicaciones(usuario)
        principal = db.session.scalar(db.select(Sucursal))
        with pytest.raises(ErrorUbicacion):
            servicio.desasignar_usuario(usuario_id=usuario.id, sucursal_id=principal.id)


def test_api_ignora_empresa_id_y_protege_idor(app, client):
    usuario_id = _preparar(app, client)
    respuesta = client.post("/api/sucursales", json={
        "empresa_id": 999, "codigo": "API", "nombre": "Desde API",
        "crear_bodega_principal": False})
    assert respuesta.status_code == 201
    with app.app_context():
        usuario = db.session.get(Usuario, usuario_id)
        sucursal = db.session.scalar(db.select(Sucursal).where(Sucursal.codigo == "API"))
        assert sucursal.empresa_id == usuario.empresa_id
        otra = Empresa(nombre="Otra", email="otra-ubicacion-api@nexustock.cl")
        db.session.add(otra); db.session.flush()
        ajena = Sucursal(empresa_id=otra.id, codigo="AJENA", nombre="Ajena")
        db.session.add(ajena); db.session.commit(); ajena_id = ajena.id
    assert client.delete(f"/api/sucursales/{ajena_id}").status_code == 403
