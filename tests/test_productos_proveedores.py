import pytest

from app.models import Empresa, Inventario, Movimiento, Producto, Proveedor, Usuario, db
from app.services.productos import ErrorProducto, LimiteProductosAlcanzado, ServicioProductos
from app.services.proveedores import ErrorProveedor, ServicioProveedores
from tests.test_autenticacion import REGISTRO


def _preparar(app, client):
    client.post("/autenticacion/registro", data=REGISTRO)
    with app.app_context():
        usuario = db.session.scalar(db.select(Usuario))
        usuario.empresa.suscripcion_actual.plan.funciones = {
            **usuario.empresa.suscripcion_actual.plan.funciones,
            "proveedores.avanzados": True,
        }
        db.session.commit()
        return usuario.id


def test_crear_producto_y_proveedor_auditable(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        usuario = db.session.get(Usuario, usuario_id)
        proveedor = ServicioProveedores(usuario).crear(
            nombre="Proveedor Uno", identificacion_fiscal="76.111.111-1", dias_entrega=5)
        producto = ServicioProductos(usuario).crear(
            codigo="abc-1", nombre="Martillo", proveedor_principal_id=proveedor.id,
            costo_referencia=1000, precio_venta=1800, stock_minimo=2, stock_maximo=20)
        assert producto.codigo == "ABC-1"
        assert producto.proveedor_principal_id == proveedor.id


def test_codigo_producto_unico_por_empresa(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        servicio = ServicioProductos(db.session.get(Usuario, usuario_id))
        servicio.crear(codigo="P-1", nombre="Uno")
        with pytest.raises(ErrorProducto):
            servicio.crear(codigo="P-1", nombre="Duplicado")


def test_mismo_codigo_permitido_en_empresas_distintas(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        usuario = db.session.get(Usuario, usuario_id)
        ServicioProductos(usuario).crear(codigo="COMUN", nombre="Empresa uno")
        otra = Empresa(nombre="Otra", email="otra-producto@nexustock.cl")
        db.session.add(otra); db.session.flush()
        db.session.add(Producto(empresa_id=otra.id, codigo="COMUN", nombre="Empresa dos",
                                costo_referencia=0, precio_venta=0))
        db.session.commit()
        assert db.session.scalar(db.select(db.func.count(Producto.id)).where(
            Producto.codigo == "COMUN")) == 2


def test_proveedor_ajeno_no_se_puede_asignar(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        usuario = db.session.get(Usuario, usuario_id)
        otra = Empresa(nombre="Otra", email="otra-proveedor@nexustock.cl")
        db.session.add(otra); db.session.flush()
        ajeno = Proveedor(empresa_id=otra.id, nombre="Ajeno")
        db.session.add(ajeno); db.session.commit(); ajeno_id = ajeno.id
        with pytest.raises(PermissionError):
            ServicioProductos(usuario).crear(codigo="P-2", nombre="Producto",
                                               proveedor_principal_id=ajeno_id)


def test_limite_productos_no_cuenta_eliminados(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        usuario = db.session.get(Usuario, usuario_id)
        usuario.empresa.suscripcion_actual.plan.limite_productos = 1
        db.session.commit()
        servicio = ServicioProductos(usuario)
        primero = servicio.crear(codigo="P-1", nombre="Primero")
        with pytest.raises(LimiteProductosAlcanzado):
            servicio.crear(codigo="P-2", nombre="Segundo")
        servicio.eliminar_logicamente(primero.id)
        segundo = servicio.crear(codigo="P-2", nombre="Segundo")
        assert segundo.id is not None


def test_producto_con_historial_solo_se_desactiva(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        usuario = db.session.get(Usuario, usuario_id)
        producto = ServicioProductos(usuario).crear(codigo="HIST", nombre="Histórico")
        # Un saldo materializado basta para impedir eliminación lógica.
        from app.models import Bodega
        bodega = db.session.scalar(db.select(Bodega))
        db.session.add(Inventario(empresa_id=usuario.empresa_id, bodega_id=bodega.id,
                                  producto_id=producto.id, cantidad=1,
                                  cantidad_reservada=0, costo_promedio=10))
        db.session.commit()
        with pytest.raises(ErrorProducto):
            ServicioProductos(usuario).eliminar_logicamente(producto.id)
        ServicioProductos(usuario).desactivar(producto.id)
        assert not db.session.get(Producto, producto.id).activo


def test_proveedor_con_producto_no_se_elimina(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        usuario = db.session.get(Usuario, usuario_id)
        proveedor = ServicioProveedores(usuario).crear(nombre="Relacionado")
        ServicioProductos(usuario).crear(codigo="REL", nombre="Relacionado",
                                          proveedor_principal_id=proveedor.id)
        with pytest.raises(ErrorProveedor):
            ServicioProveedores(usuario).eliminar_logicamente(proveedor.id)


def test_api_solo_lista_productos_de_empresa_actual(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        usuario = db.session.get(Usuario, usuario_id)
        ServicioProductos(usuario).crear(codigo="MIO", nombre="Mío")
        otra = Empresa(nombre="Otra", email="otra-api@nexustock.cl")
        db.session.add(otra); db.session.flush()
        db.session.add(Producto(empresa_id=otra.id, codigo="SECRETO", nombre="Secreto",
                                costo_referencia=0, precio_venta=0)); db.session.commit()
    respuesta = client.get("/api/productos")
    codigos = [p["codigo"] for p in respuesta.get_json()["productos"]]
    assert codigos == ["MIO"]


def test_api_crea_producto_sin_aceptar_empresa_id(app, client):
    _preparar(app, client)
    respuesta = client.post("/api/productos", json={
        "empresa_id": 999999, "codigo": "API-1", "nombre": "Desde API",
        "precio_venta": 100,
    })
    assert respuesta.status_code == 201
    with app.app_context():
        producto = db.session.scalar(db.select(Producto).where(Producto.codigo == "API-1"))
        usuario = db.session.scalar(db.select(Usuario))
        assert producto.empresa_id == usuario.empresa_id


def test_edicion_parcial_conserva_campos(app, client):
    usuario_id = _preparar(app, client)
    with app.app_context():
        usuario = db.session.get(Usuario, usuario_id)
        producto = ServicioProductos(usuario).crear(
            codigo="PARCIAL", nombre="Original", precio_venta=100, costo_referencia=50)
        producto_id = producto.id
    respuesta = client.patch(f"/api/productos/{producto_id}", json={"precio_venta": 150})
    assert respuesta.status_code == 200
    with app.app_context():
        producto = db.session.get(Producto, producto_id)
        assert producto.codigo == "PARCIAL"
        assert producto.nombre == "Original"
        assert producto.precio_venta == 150


def test_id_ajeno_en_api_responde_403(app, client):
    _preparar(app, client)
    with app.app_context():
        otra = Empresa(nombre="Ajena", email="ajena-idor@nexustock.cl")
        db.session.add(otra); db.session.flush()
        producto = Producto(empresa_id=otra.id, codigo="IDOR", nombre="Ajeno",
                            costo_referencia=0, precio_venta=0)
        db.session.add(producto); db.session.commit(); producto_id = producto.id
    respuesta = client.patch(f"/api/productos/{producto_id}", json={"nombre": "Hack"})
    assert respuesta.status_code == 403
    with app.app_context():
        assert db.session.get(Producto, producto_id).nombre == "Ajeno"
