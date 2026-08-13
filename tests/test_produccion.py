from sqlalchemy import text

from app.models import db
from config import normalizar_url_base_datos


def test_normaliza_urls_postgresql_para_psycopg3():
    assert normalizar_url_base_datos("postgres://u:c@host/base") == (
        "postgresql+psycopg://u:c@host/base"
    )
    assert normalizar_url_base_datos("postgresql://u:c@host/base") == (
        "postgresql+psycopg://u:c@host/base"
    )


def test_estado_preparacion_confirma_base_de_datos(client):
    respuesta = client.get("/estado/preparacion")
    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"estado": "preparado", "servicio": "nexustock"}


def test_verificar_produccion_exige_revision_alembic(app):
    corredor = app.test_cli_runner()
    resultado = corredor.invoke(args=["verificar-produccion"])
    assert resultado.exit_code != 0
    assert "migración" in resultado.output


def test_verificar_produccion_con_revision_y_planes(app):
    with app.app_context():
        db.session.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
        db.session.execute(text(
            "INSERT INTO alembic_version (version_num) VALUES ('revision-prueba')"
        ))
        db.session.commit()
    siembra = app.test_cli_runner().invoke(args=["seed-planes"])
    assert siembra.exit_code == 0
    resultado = app.test_cli_runner().invoke(args=["verificar-produccion"])
    assert resultado.exit_code == 0
    assert "Producción verificada" in resultado.output