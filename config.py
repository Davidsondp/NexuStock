import os
from datetime import timedelta


def normalizar_url_base_datos(url: str) -> str:
    """Adapta las URL de proveedores al controlador Psycopg 3 instalado."""
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


class Configuracion:
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = normalizar_url_base_datos(
        os.getenv("DATABASE_URL", "sqlite:///nexustock.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": int(os.getenv("DATABASE_POOL_RECYCLE", "300")),
    }
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_NAME = "nexustock_sesion"
    SESSION_REFRESH_EACH_REQUEST = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    MAIL_SERVER = os.getenv("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "25"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "false").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "no-responder@nexustock.cl")
    WEBHOOK_PAGOS_SECRET = os.getenv("WEBHOOK_PAGOS_SECRET")
    LIMITE_SOLICITUDES_SECRET = os.getenv("LIMITE_SOLICITUDES_SECRET")
    TRUSTED_HOSTS = [h.strip() for h in os.getenv("TRUSTED_HOSTS", "").split(",") if h.strip()] or None


class ConfiguracionDesarrollo(Configuracion):
    DEBUG = True
    SECRET_KEY = os.getenv("SECRET_KEY", "solo-desarrollo-cambiar")
    SESSION_COOKIE_SECURE = False
    MAIL_SUPPRESS_SEND = True


class ConfiguracionPruebas(Configuracion):
    TESTING = True
    SECRET_KEY = "testing"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    MAIL_SUPPRESS_SEND = True


class ConfiguracionProduccion(Configuracion):
    SESSION_COOKIE_SECURE = True

    @classmethod
    def validar(cls):
        if not cls.SECRET_KEY:
            raise RuntimeError("SECRET_KEY es obligatoria en producciÃ³n")
        if not os.getenv("DATABASE_URL"):
            raise RuntimeError("DATABASE_URL es obligatoria en producciÃ³n")
        if not os.getenv("MAIL_SERVER") or not os.getenv("MAIL_DEFAULT_SENDER"):
            raise RuntimeError("La configuraciÃ³n SMTP es obligatoria en producciÃ³n")
        if not cls.WEBHOOK_PAGOS_SECRET or len(cls.WEBHOOK_PAGOS_SECRET) < 32:
            raise RuntimeError("WEBHOOK_PAGOS_SECRET debe tener al menos 32 caracteres en producciÃ³n")
        if not cls.LIMITE_SOLICITUDES_SECRET or len(cls.LIMITE_SOLICITUDES_SECRET) < 32:
            raise RuntimeError("LIMITE_SOLICITUDES_SECRET debe tener al menos 32 caracteres en producciÃ³n")
        if not cls.TRUSTED_HOSTS:
            raise RuntimeError("TRUSTED_HOSTS es obligatorio en producciÃ³n")


CONFIGURACIONES = {
    "desarrollo": ConfiguracionDesarrollo,
    "pruebas": ConfiguracionPruebas,
    "produccion": ConfiguracionProduccion,
}