import click
from sqlalchemy import text

from .models import PlanSaaS, Usuario, db
from .services.planes import funciones_plan


PLANES = (
    dict(codigo="prueba", nombre="Prueba", descripcion="Prueba con funciones profesionales",
         precio_mensual=0, precio_anual=0, dias_prueba=30, limite_productos=100,
         limite_usuarios=2, limite_movimientos_mes=500, limite_sucursales=1,
         limite_bodegas=1, almacenamiento_mb=500,
         funciones=funciones_plan("prueba"), orden=1),
    dict(codigo="basico", nombre="Básico", descripcion="Para pequeños negocios",
         precio_mensual=9990, precio_anual=99900, dias_prueba=0, limite_productos=500,
         limite_usuarios=2, limite_movimientos_mes=5000, limite_sucursales=1,
         limite_bodegas=1, almacenamiento_mb=2000,
         funciones=funciones_plan("basico"), orden=2),
    dict(codigo="profesional", nombre="Profesional", descripcion="Operación y control avanzado",
         precio_mensual=19990, precio_anual=199900, dias_prueba=0, limite_productos=5000,
         limite_usuarios=10, limite_movimientos_mes=50000, limite_sucursales=3,
         limite_bodegas=3, almacenamiento_mb=5000,
         funciones=funciones_plan("profesional"), orden=3),
    dict(codigo="empresa", nombre="Empresa", descripcion="Control e inteligencia completa",
         precio_mensual=49990, precio_anual=499900, dias_prueba=0, limite_productos=None,
         limite_usuarios=None, limite_movimientos_mes=None, limite_sucursales=None,
         limite_bodegas=None, almacenamiento_mb=20000,
         funciones=funciones_plan("empresa"), orden=4),
)


def registrar_comandos(app):
    @app.cli.command("verificar-produccion")
    def verificar_produccion():
        """Comprueba conexión, migración aplicada y datos esenciales."""
        try:
            db.session.execute(text("SELECT 1"))
            revision = db.session.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
        except Exception as exc:
            db.session.rollback()
            raise click.ClickException(
                "No fue posible verificar la base de datos o su migración"
            ) from exc
        if not revision:
            raise click.ClickException("La base de datos no tiene una revisión de Alembic aplicada")
        codigos = set(db.session.scalars(db.select(PlanSaaS.codigo)))
        faltantes = {datos["codigo"] for datos in PLANES} - codigos
        if faltantes:
            raise click.ClickException(
                "Faltan planes oficiales: " + ", ".join(sorted(faltantes))
            )
        click.echo(f"Producción verificada. Revisión de base de datos: {revision}")

    @app.cli.command("seed-planes")
    def seed_planes():
        """Crea o actualiza idempotentemente los planes oficiales."""
        for datos in PLANES:
            plan = db.session.scalar(db.select(PlanSaaS).where(PlanSaaS.codigo == datos["codigo"]))
            if plan is None:
                db.session.add(PlanSaaS(**datos))
            else:
                for campo, valor in datos.items():
                    setattr(plan, campo, valor)
        db.session.commit()
        click.echo("Planes oficiales configurados.")

    @app.cli.command("crear-super-admin")
    @click.option("--nombre", prompt=True)
    @click.option("--email", prompt=True)
    @click.password_option(confirmation_prompt=True)
    def crear_super_admin(nombre, email, password):
        """Crea una cuenta global fuera de cualquier empresa."""
        email = email.strip().lower()
        if db.session.scalar(db.select(Usuario.id).where(Usuario.email == email)):
            raise click.ClickException("El correo ya está registrado")
        try:
            usuario = Usuario(empresa_id=None, nombre=nombre.strip(), email=email,
                              rol="super_admin", activo=True)
            usuario.set_password(password); db.session.add(usuario); db.session.commit()
            click.echo("Super Admin creado correctamente.")
        except Exception as exc:
            db.session.rollback(); raise click.ClickException(str(exc)) from exc

    @app.cli.command("generar-alertas")
    def generar_alertas():
        """Genera alertas para todas las empresas activas."""
        from .models import Empresa
        from .services.alertas import (
            ServicioAlertas,
        )

        empresa_ids = list(
            db.session.scalars(
                db.select(Empresa.id)
                .where(
                    Empresa.estado == "activa",
                    Empresa.eliminado.is_(False),
                )
                .order_by(Empresa.id)
            )
        )

        procesadas = 0
        omitidas = 0
        errores = 0
        creadas = 0
        actualizadas = 0
        resueltas = 0

        for empresa_id in empresa_ids:
            usuario = db.session.scalar(
                db.select(Usuario)
                .where(
                    Usuario.empresa_id
                    == empresa_id,
                    Usuario.rol.in_(
                        {
                            "admin_empresa",
                            "supervisor",
                        }
                    ),
                    Usuario.activo.is_(True),
                    Usuario.eliminado.is_(False),
                )
                .order_by(
                    (
                        Usuario.rol
                        == "admin_empresa"
                    ).desc(),
                    Usuario.id,
                )
            )

            if usuario is None:
                omitidas += 1
                click.echo(
                    (
                        f"Empresa {empresa_id} omitida: "
                        "no posee un administrador "
                        "o supervisor activo."
                    ),
                    err=True,
                )
                continue

            try:
                resultado = ServicioAlertas(
                    usuario
                ).generar()

                creadas += resultado.creadas
                actualizadas += (
                    resultado.actualizadas
                )
                resueltas += resultado.resueltas
                procesadas += 1
            except Exception as exc:
                db.session.rollback()
                errores += 1
                click.echo(
                    (
                        f"Error en empresa "
                        f"{empresa_id}: {exc}"
                    ),
                    err=True,
                )
            finally:
                db.session.remove()

        click.echo(
            f"Empresas procesadas: {procesadas}"
        )
        click.echo(
            f"Empresas omitidas: {omitidas}"
        )
        click.echo(f"Alertas creadas: {creadas}")
        click.echo(
            f"Alertas actualizadas: {actualizadas}"
        )
        click.echo(
            f"Alertas resueltas: {resueltas}"
        )
        click.echo(f"Errores: {errores}")

        if errores:
            raise click.ClickException(
                (
                    "La generación terminó con "
                    f"{errores} empresa(s) fallida(s)."
                )
            )
