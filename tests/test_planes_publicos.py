from pathlib import Path


def test_planes_publicos_no_requieren_sesion(
    client,
):
    respuesta = client.get(
        "/planes"
    )

    assert respuesta.status_code == 200


def test_planes_publicos_exponen_contrato_visual(
    client,
):
    respuesta = client.get(
        "/planes"
    )

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
        "Pr\u00f3ximamente",
        "Preguntas frecuentes",
    )

    for texto in textos:
        assert (
            texto.encode("utf-8")
            in respuesta.data
        )


def test_planes_publicos_incluyen_conversion_transparente(
    client,
):
    respuesta = client.get(
        "/planes"
    )

    contratos = (
        b'data-plan="basico-pago"',
        b'data-plan="profesional-pago"',
        b'data-plan="empresa-pago"',
        b'data-ciclo="mensual"',
        b'data-ciclo="anual"',
        b'class="plan-publico__recomendado"',
        "M\u00e1s elegido".encode("utf-8"),
        b'Comparar capacidades',
        b'Comenzar prueba',
    )

    for contrato in contratos:
        assert contrato in respuesta.data


def test_planes_publicos_enlazan_autenticacion(
    client,
):
    respuesta = client.get(
        "/planes"
    )

    assert (
        b"/autenticacion/ingresar"
        in respuesta.data
    )
    assert (
        b"/autenticacion/registro"
        in respuesta.data
    )


def test_javascript_planes_publicos_conserva_eleccion():
    contenido = Path(
        "app/static/js/planes_publicos.js"
    ).read_text(encoding="utf-8-sig")

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
    contenido = Path(
        "app/static/css/planes_publicos.css"
    ).read_text(encoding="utf-8-sig")

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
