from pathlib import Path

from app.models import Usuario, db
from tests.test_autenticacion import REGISTRO


def registrar_empresa(client):
    return client.post(
        "/autenticacion/registro",
        data=REGISTRO,
    )


def convertir_en_empleado(
    app,
    client,
    rol="empleado",
):
    with app.app_context():
        usuario = db.session.scalar(
            db.select(Usuario).where(
                Usuario.email == REGISTRO["email"]
            )
        )
        usuario.rol = rol
        db.session.commit()

    client.post(
        "/autenticacion/salir"
    )

    ingreso = client.post(
        "/autenticacion/ingresar",
        data={
            "email": REGISTRO["email"],
            "password": REGISTRO["password"],
        },
    )

    assert ingreso.status_code == 302


def test_panel_planes_requiere_autenticacion(
    client,
):
    respuesta = client.get(
        "/panel/administracion/planes"
    )

    assert respuesta.status_code == 302
    assert (
        "/autenticacion/ingresar"
        in respuesta.location
    )


def test_panel_planes_incluye_contrato_visual(
    client,
):
    registrar_empresa(client)

    respuesta = client.get(
        "/panel/administracion/planes"
    )

    assert respuesta.status_code == 200

    contratos = (
        b'data-api-suscripciones="/api/suscripciones"',
        b'data-puede-solicitar="true"',
        b'id="resumen-plan-actual"',
        b'id="resumen-estado-suscripcion"',
        b'id="resumen-vigencia"',
        b'id="resumen-ciclo"',
        b'id="lista-limites-plan"',
        b'id="selector-ciclo"',
        b'id="lista-planes"',
        b'id="comparador-capacidades"',
        b'id="historial-solicitudes"',
        b'id="estado-planes"',
        b'id="actualizar-planes"',
        b"css/planes.css",
        b"js/planes.js",
    )

    for contrato in contratos:
        assert contrato in respuesta.data

    textos = (
        "Planes y suscripci\u00f3n",
        (
            "Elige la capacidad que necesita "
            "tu empresa"
        ),
        "Plan actual",
        "Capacidades de NexuStock",
        "Inteligencia artificial",
        "Pr\u00f3ximamente",
    )

    for texto in textos:
        assert (
            texto.encode("utf-8")
            in respuesta.data
        )


def test_panel_planes_rechaza_empleado(
    app,
    client,
):
    registrar_empresa(client)
    convertir_en_empleado(
        app,
        client,
        rol="empleado",
    )

    respuesta = client.get(
        "/panel/administracion/planes"
    )

    assert respuesta.status_code == 403


def test_panel_planes_rechaza_supervisor(
    app,
    client,
):
    registrar_empresa(client)
    convertir_en_empleado(
        app,
        client,
        rol="supervisor",
    )

    respuesta = client.get(
        "/panel/administracion/planes"
    )

    assert respuesta.status_code == 403


def test_panel_principal_enlaza_planes(
    client,
):
    registrar_empresa(client)

    respuesta = client.get(
        "/panel"
    )

    assert respuesta.status_code == 200
    assert (
        b"/panel/administracion/planes"
        in respuesta.data
    )
    assert (
        "Planes y suscripci\u00f3n"
        .encode("utf-8")
        in respuesta.data
    )


def test_javascript_planes_declara_contratos():
    contenido = Path(
        "app/static/js/planes.js"
    ).read_text(encoding="utf-8-sig")

    contratos = (
        "apiSuscripciones",
        "planes_disponibles",
        "catalogo_capacidades",
        "capacidades",
        "plan_codigo",
        "ciclo",
        "/solicitudes",
        "/cancelar",
        "X-CSRFToken",
        "selector-ciclo",
        "comparador-capacidades",
        "historial-solicitudes",
    )

    for contrato in contratos:
        assert contrato in contenido
