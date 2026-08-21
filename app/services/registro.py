from datetime import timedelta
from decimal import Decimal

from sqlalchemy.exc import IntegrityError

from ..models import (
    Bodega,
    ConfiguracionEmpresa,
    Empresa,
    PlanSaaS,
    SolicitudCambioPlan,
    Sucursal,
    Suscripcion,
    Usuario,
    UsuarioSucursal,
    db,
    utcnow,
)
from .auditoria import registrar_auditoria
from .perfiles_empresa import CAPACIDADES_POR_RUBRO
from ..validaciones import normalizar_rut, normalizar_telefono


class ErrorRegistro(ValueError):
    pass


def _plan_comercial(
    plan_codigo: str | None,
    ciclo: str | None,
) -> tuple[PlanSaaS | None, str | None]:
    if plan_codigo is None and ciclo is None:
        return None, None

    codigo = str(plan_codigo or "").strip().lower()
    ciclo_normalizado = str(ciclo or "").strip().lower()

    if ciclo_normalizado not in {
        "mensual",
        "anual",
    }:
        raise ErrorRegistro("El ciclo comercial no es válido")

    plan = db.session.scalar(
        db.select(PlanSaaS).where(
            PlanSaaS.codigo == codigo,
            PlanSaaS.activo.is_(True),
            PlanSaaS.codigo != "prueba",
        )
    )

    if not plan:
        raise ErrorRegistro("El plan comercial no está disponible")

    return plan, ciclo_normalizado


def registrar_empresa(
    *,
    empresa_nombre: str,
    identificacion_fiscal: str | None,
    nombre: str,
    apellido: str | None,
    email: str,
    password: str,
    empresa_identificacion_fiscal: str | None = None,
    telefono: str | None = None,
    empresa_telefono: str | None = None,
    rubro: str | None = "general",
    plan_codigo: str | None = None,
    ciclo: str | None = None,
) -> Usuario:
    """Crea el tenant inicial completo en una transacción."""

    plan_prueba = db.session.scalar(
        db.select(PlanSaaS).where(
            PlanSaaS.codigo == "prueba",
            PlanSaaS.activo.is_(True),
        )
    )

    if not plan_prueba:
        raise ErrorRegistro("El plan de prueba no está configurado")

    plan_comercial, ciclo_comercial = _plan_comercial(
        plan_codigo,
        ciclo,
    )

    codigo_rubro = str(rubro or "general").strip().lower()

    if codigo_rubro not in CAPACIDADES_POR_RUBRO:
        raise ErrorRegistro("El rubro de la empresa no es válido")

    email = email.strip().lower()

    if db.session.scalar(db.select(Usuario.id).where(Usuario.email == email)):
        raise ErrorRegistro("El correo ya está registrado")

    try:
        empresa = Empresa(
            nombre=empresa_nombre.strip(),
            identificacion_fiscal=normalizar_rut(empresa_identificacion_fiscal),
            email=email,
            telefono=normalizar_telefono(empresa_telefono),
            estado="activa",
        )
        db.session.add(empresa)
        db.session.flush()

        ahora = utcnow()

        suscripcion = Suscripcion(
            empresa_id=empresa.id,
            plan_id=plan_prueba.id,
            estado="prueba",
            ciclo="prueba",
            fecha_inicio=ahora,
            fecha_fin=(ahora + timedelta(days=plan_prueba.dias_prueba)),
        )
        sucursal = Sucursal(
            empresa_id=empresa.id,
            codigo="PRINCIPAL",
            nombre="Sucursal principal",
        )
        configuracion = ConfiguracionEmpresa(
            empresa_id=empresa.id,
            nombre_comercial=empresa.nombre,
            opciones={
                "rubro": codigo_rubro,
                "capacidades": {},
            },
        )

        db.session.add_all(
            [
                suscripcion,
                sucursal,
                configuracion,
            ]
        )
        db.session.flush()

        bodega = Bodega(
            empresa_id=empresa.id,
            sucursal_id=sucursal.id,
            codigo="PRINCIPAL",
            nombre="Bodega principal",
        )
        usuario = Usuario(
            empresa_id=empresa.id,
            nombre=nombre.strip(),
            apellido=((apellido or "").strip() or None),
            identificacion_fiscal=normalizar_rut(identificacion_fiscal),
            telefono=normalizar_telefono(telefono),
            email=email,
            rol="jefe",
            activo=True,
        )
        usuario.set_password(password)

        db.session.add_all(
            [
                bodega,
                usuario,
            ]
        )
        db.session.flush()

        db.session.add(
            UsuarioSucursal(
                empresa_id=empresa.id,
                usuario_id=usuario.id,
                sucursal_id=sucursal.id,
                es_principal=True,
            )
        )

        if plan_comercial and ciclo_comercial:
            precio = (
                plan_comercial.precio_mensual
                if ciclo_comercial == "mensual"
                else plan_comercial.precio_anual
            )
            monto = Decimal(precio).quantize(Decimal("0.01"))

            solicitud = SolicitudCambioPlan(
                empresa_id=empresa.id,
                plan_solicitado_id=(plan_comercial.id),
                solicitada_por_id=usuario.id,
                estado="pendiente",
                ciclo=ciclo_comercial,
                monto_esperado=monto,
                moneda=plan_comercial.moneda,
            )
            db.session.add(solicitud)
            db.session.flush()

            registrar_auditoria(
                accion="suscripcion.solicitada",
                modulo="suscripciones",
                empresa_id=empresa.id,
                usuario_id=usuario.id,
                entidad_tipo=("SolicitudCambioPlan"),
                entidad_id=solicitud.id,
                datos_nuevos={
                    "plan": plan_comercial.codigo,
                    "ciclo": ciclo_comercial,
                    "monto": str(monto),
                },
            )

        registrar_auditoria(
            accion="empresa.registro",
            modulo="autenticacion",
            empresa_id=empresa.id,
            usuario_id=usuario.id,
            entidad_tipo="Empresa",
            entidad_id=empresa.id,
            descripcion=("Registro inicial de empresa " "y su jefatura"),
        )

        db.session.commit()
        return usuario

    except IntegrityError as exc:
        db.session.rollback()
        raise ErrorRegistro("El correo o la identificación fiscal " "ya están registrados") from exc

    except ValueError as exc:
        db.session.rollback()
        raise ErrorRegistro(str(exc)) from exc

    except Exception:
        db.session.rollback()
        raise
