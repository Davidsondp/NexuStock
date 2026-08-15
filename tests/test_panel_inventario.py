from app.models import Usuario, UsuarioSucursal, db
from tests.test_autenticacion import REGISTRO


def registrar_empresa(client):
    return client.post(
        "/autenticacion/registro",
        data=REGISTRO,
    )


def crear_superadmin(app):
    with app.app_context():
        usuario = Usuario(
            empresa_id=None,
            nombre="Super",
            apellido="Administrador",
            email="inventario.global@nexustock.cl",
            rol="super_admin",
            activo=True,
        )
        usuario.set_password("ClaveSuperAdmin123")

        db.session.add(usuario)
        db.session.commit()


def iniciar_superadmin(client):
    return client.post(
        "/autenticacion/ingresar",
        data={
            "email":
                "inventario.global@nexustock.cl",
            "password": "ClaveSuperAdmin123",
        },
    )


def test_panel_inventario_exige_autenticacion(
    client,
):
    respuesta = client.get("/panel/inventario")

    assert respuesta.status_code == 302
    assert (
        "/autenticacion/ingresar"
        in respuesta.location
    )


def test_usuario_empresarial_puede_ver_inventario(
    client,
):
    registrar_empresa(client)

    respuesta = client.get("/panel/inventario")

    assert respuesta.status_code == 200
    assert (
        "Inventario".encode("utf-8")
        in respuesta.data
    )
    assert (
        REGISTRO["empresa_nombre"].encode("utf-8")
        in respuesta.data
    )


def test_superadmin_no_accede_a_inventario_empresarial(
    app,
    client,
):
    crear_superadmin(app)
    iniciar_superadmin(client)

    respuesta = client.get("/panel/inventario")

    assert respuesta.status_code == 403


def test_panel_empresarial_enlaza_inventario(client):
    registrar_empresa(client)

    respuesta = client.get("/panel")

    assert respuesta.status_code == 200
    assert b"/panel/inventario" in respuesta.data


def test_pagina_inventario_referencia_apis_y_recursos(
    client,
):
    registrar_empresa(client)

    respuesta = client.get("/panel/inventario")

    assert respuesta.status_code == 200
    assert (
        b"/api/inventario/movimientos"
        in respuesta.data
    )
    assert (
        b"/api/inventario/stock"
        in respuesta.data
    )
    assert (
        b"/api/inventario/movimientos"
        in respuesta.data
    )
    assert b"/api/productos" in respuesta.data
    assert (
        b"css/panel_empresarial.css"
        in respuesta.data
    )
    assert b"css/inventario.css" in respuesta.data
    assert b"js/inventario.js" in respuesta.data
    assert b'id="resumen-inventario"' in respuesta.data
    assert b'id="buscar-inventario"' in respuesta.data
    assert b'id="tabla-stock"' in respuesta.data
    assert b'id="tabla-movimientos"' in respuesta.data
    assert b'id="nuevo-movimiento"' in respuesta.data
    assert b'id="modal-movimiento"' in respuesta.data
    assert b'id="formulario-movimiento"' in respuesta.data
    assert b'id="movimiento-tipo"' in respuesta.data
    assert b'id="movimiento-producto"' in respuesta.data
    assert b'id="movimiento-cantidad"' in respuesta.data
    assert b'id="movimiento-stock-final"' in respuesta.data
    assert b'id="movimiento-costo-unitario"' in respuesta.data
    assert b'id="movimiento-precio-unitario"' in respuesta.data
    assert b'id="movimiento-motivo"' in respuesta.data
    assert (
        b' name="csrf_token"'
        in respuesta.data
    )


def test_empleado_conserva_operaciones_autorizadas(
    app,
    client,
):
    registrar_empresa(client)

    with app.app_context():
        administrador = db.session.scalar(
            db.select(Usuario).where(
                Usuario.email == REGISTRO["email"]
            )
        )

        empleado = Usuario(
            empresa_id=administrador.empresa_id,
            nombre="Empleado",
            apellido="Inventario",
            email=
                "empleado.inventario@nexustock.cl",
            rol="empleado",
            activo=True,
        )
        empleado.set_password("ClaveEmpleado123")

        db.session.add(empleado)
        db.session.flush()

        asignacion_principal = db.session.scalar(
            db.select(UsuarioSucursal).where(
                UsuarioSucursal.empresa_id
                == administrador.empresa_id,
                UsuarioSucursal.usuario_id
                == administrador.id,
                UsuarioSucursal.es_principal.is_(True),
            )
        )

        db.session.add(
            UsuarioSucursal(
                empresa_id=administrador.empresa_id,
                usuario_id=empleado.id,
                sucursal_id=
                    asignacion_principal.sucursal_id,
                es_principal=True,
            )
        )

        db.session.commit()

    client.post("/autenticacion/salir")

    client.post(
        "/autenticacion/ingresar",
        data={
            "email":
                "empleado.inventario@nexustock.cl",
            "password": "ClaveEmpleado123",
        },
    )

    respuesta = client.get("/panel/inventario")

    assert respuesta.status_code == 200
    assert (
        b'data-permiso-entrada="true"'
        in respuesta.data
    )
    assert (
        b'data-permiso-salida="true"'
        in respuesta.data
    )
    assert (
        b'data-permiso-ajuste="false"'
        in respuesta.data
    )
    assert (
        b'data-permiso-devolucion="true"'
        in respuesta.data
    )
