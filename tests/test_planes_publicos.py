from pathlib import Path

import pytest

from app.commands import PLANES
from app.models import PlanSaaS, db


@pytest.fixture(autouse=True)
def sembrar_planes_comerciales(app):
    with app.app_context():
        db.session.add_all(PlanSaaS(**datos) for datos in PLANES if datos["codigo"] != "prueba")
        db.session.commit()


def test_planes_publicos_no_requieren_sesion(
    client,
):
    respuesta = client.get("/planes")

    assert respuesta.status_code == 200


def test_planes_publicos_exponen_contrato_visual(
    client,
):
    respuesta = client.get("/planes")

    assert respuesta.status_code == 200

    contratos = (
        b'id="portada-planes"',
        b'id="selector-ciclo-publico"',
        b'id="planes-comerciales"',
        b'id="comparacion-publica"',
        b'id="demostracion-producto"',
        b'id="preguntas-planes"',
        b'id="cta-final-planes"',
        b'id="cta-movil-planes"',
        b'data-registro-base="/autenticacion/registro"',
        b"css/planes_publicos.css",
        b"js/planes_publicos.js",
    )

    for contrato in contratos:
        assert contrato in respuesta.data

    textos = (
        "Controla tu inventario",
        "Haz crecer tu negocio",
        "Elige el plan que acompa\u00f1a tu operaci\u00f3n",
        "Prueba NexuStock",
        "Capacidades que crecen contigo",
        "Inteligencia artificial",
        "Disponible",
        "Preguntas frecuentes",
    )

    for texto in textos:
        assert texto.encode("utf-8") in respuesta.data


def test_planes_publicos_incluyen_conversion_transparente(
    client,
):
    respuesta = client.get("/planes")

    contratos = (
        b'data-plan="basico"',
        b'data-plan="profesional"',
        b'data-plan="empresa"',
        b'data-ciclo="mensual"',
        b'data-ciclo="anual"',
        b'class="plan-publico__recomendado"',
        "M\u00e1s elegido".encode("utf-8"),
        b"Comparar capacidades",
        b"Comenzar prueba",
    )

    for contrato in contratos:
        assert contrato in respuesta.data


def test_portada_usa_precios_reales_y_refleja_edicion(app, client):
    respuesta = client.get("/planes")
    assert b'data-precio-mensual="19990.00"' in respuesta.data
    assert "$19.990".encode() in respuesta.data
    assert b'data-precio-mensual="49990.00"' in respuesta.data

    with app.app_context():
        profesional = db.session.scalar(db.select(PlanSaaS).where(PlanSaaS.codigo == "profesional"))
        profesional.precio_mensual = 24990
        profesional.precio_anual = 249900
        db.session.commit()

    actualizada = client.get("/")
    assert b'data-precio-mensual="24990.00"' in actualizada.data
    assert "$24.990".encode() in actualizada.data


def test_plan_publicado_es_aceptado_por_el_registro(client):
    respuesta = client.get("/autenticacion/registro?plan=profesional&ciclo=mensual")
    assert respuesta.status_code == 200
    assert "Profesional".encode() in respuesta.data
    with client.session_transaction() as sesion:
        assert sesion["registro_plan_seleccionado"] == "profesional"
        assert sesion["registro_ciclo_seleccionado"] == "mensual"


def test_planes_publicos_enlazan_autenticacion(
    client,
):
    respuesta = client.get("/planes")

    assert b"/autenticacion/ingresar" in respuesta.data
    assert b"/autenticacion/registro" in respuesta.data


def test_javascript_planes_publicos_conserva_eleccion():
    contenido = Path("app/static/js/planes_publicos.js").read_text(encoding="utf-8-sig")

    contratos = (
        "registroBase",
        "selector-ciclo-publico",
        "data-plan",
        "plan",
        "ciclo",
        "URLSearchParams",
        "planes-comerciales",
        "comparacion-publica",
        "cta-movil-planes",
        "IntersectionObserver",
    )

    for contrato in contratos:
        assert contrato in contenido


def test_css_planes_publicos_es_responsive():
    contenido = Path("app/static/css/planes_publicos.css").read_text(encoding="utf-8-sig")

    contratos = (
        ".pagina-planes",
        ".portada-planes",
        ".plan-publico",
        ".plan-publico--destacado",
        ".comparacion-publica",
        ".cta-movil-planes",
        "@media",
        "prefers-reduced-motion",
    )

    for contrato in contratos:
        assert contrato in contenido
