from datetime import timedelta

from sqlalchemy.exc import IntegrityError

from ..models import (Bodega, ConfiguracionEmpresa, Empresa, PlanSaaS, Sucursal,
                      Suscripcion, Usuario, UsuarioSucursal, db, utcnow)
from .auditoria import registrar_auditoria


class ErrorRegistro(ValueError):
    pass


def registrar_empresa(*, empresa_nombre: str, identificacion_fiscal: str | None,
                      nombre: str, apellido: str | None, email: str, password: str) -> Usuario:
    """Crea el tenant inicial completo en una única transacción."""
    plan = db.session.execute(
        db.select(PlanSaaS).where(PlanSaaS.codigo == "prueba", PlanSaaS.activo.is_(True))
    ).scalar_one_or_none()
    if not plan:
        raise ErrorRegistro("El plan de prueba no está configurado")

    email = email.strip().lower()
    if db.session.scalar(db.select(Usuario.id).where(Usuario.email == email)):
        raise ErrorRegistro("El correo ya está registrado")

    try:
        empresa = Empresa(nombre=empresa_nombre.strip(), identificacion_fiscal=(identificacion_fiscal or None),
                          email=email, estado="activa")
        db.session.add(empresa)
        db.session.flush()

        ahora = utcnow()
        suscripcion = Suscripcion(
            empresa_id=empresa.id, plan_id=plan.id, estado="prueba", ciclo="prueba",
            fecha_inicio=ahora, fecha_fin=ahora + timedelta(days=plan.dias_prueba),
        )
        sucursal = Sucursal(empresa_id=empresa.id, codigo="PRINCIPAL", nombre="Sucursal principal")
        configuracion = ConfiguracionEmpresa(empresa_id=empresa.id, nombre_comercial=empresa.nombre)
        db.session.add_all([suscripcion, sucursal, configuracion])
        db.session.flush()

        bodega = Bodega(empresa_id=empresa.id, sucursal_id=sucursal.id,
                        codigo="PRINCIPAL", nombre="Bodega principal")
        usuario = Usuario(empresa_id=empresa.id, nombre=nombre.strip(), apellido=(apellido or "").strip() or None,
                          email=email, rol="admin_empresa", activo=True)
        usuario.set_password(password)
        db.session.add_all([bodega, usuario])
        db.session.flush()
        db.session.add(UsuarioSucursal(empresa_id=empresa.id, usuario_id=usuario.id,
                                      sucursal_id=sucursal.id, es_principal=True))
        registrar_auditoria(
            accion="empresa.registro", modulo="autenticacion", empresa_id=empresa.id,
            usuario_id=usuario.id, entidad_tipo="Empresa", entidad_id=empresa.id,
            descripcion="Registro inicial de empresa y administrador",
        )
        db.session.commit()
        return usuario
    except IntegrityError as exc:
        db.session.rollback()
        raise ErrorRegistro("El correo o la identificación fiscal ya están registrados") from exc
    except Exception:
        db.session.rollback()
        raise

