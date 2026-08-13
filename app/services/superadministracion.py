"""Administración global sin acceso operativo a inventario empresarial."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from sqlalchemy.exc import IntegrityError

from ..models import (Auditoria, Empresa, Pago, PlanSaaS, Suscripcion, Usuario,
                      db, utcnow)
from ..permisos import evaluar_permiso
from .auditoria import registrar_auditoria


class ErrorSuperAdministracion(ValueError):
    codigo = "superadministracion_invalida"


class ServicioSuperAdministracion:
    def __init__(self, actor):
        self.actor = actor
        if actor.rol != "super_admin" or actor.empresa_id is not None:
            raise PermissionError("Se requiere una cuenta Super Admin global")

    def resumen(self):
        self._exigir("superadmin.dashboard")
        return {
            "empresas": db.session.scalar(db.select(db.func.count(Empresa.id)).where(Empresa.eliminado.is_(False))),
            "empresas_activas": db.session.scalar(db.select(db.func.count(Empresa.id)).where(
                Empresa.estado == "activa", Empresa.eliminado.is_(False))),
            "usuarios_empresariales": db.session.scalar(db.select(db.func.count(Usuario.id)).where(
                Usuario.empresa_id.is_not(None), Usuario.eliminado.is_(False))),
            "suscripciones_activas": db.session.scalar(db.select(db.func.count(Suscripcion.id)).where(
                Suscripcion.estado.in_(("prueba", "activa")))),
            "pagos_confirmados": db.session.scalar(db.select(db.func.count(Pago.id)).where(Pago.estado == "pagado")),
            "ingresos_confirmados": str(Decimal(db.session.scalar(db.select(
                db.func.coalesce(db.func.sum(Pago.monto), 0)).where(Pago.estado == "pagado")) or 0)),
        }

    def listar_empresas(self, *, estado=None, buscar=None):
        self._exigir("superadmin.empresas")
        q = db.select(Empresa).where(Empresa.eliminado.is_(False))
        if estado:
            if estado not in {"activa", "suspendida", "cancelada"}: raise ErrorSuperAdministracion("Estado inválido")
            q = q.where(Empresa.estado == estado)
        if buscar:
            patron = f"%{buscar.strip()}%"
            q = q.where(db.or_(Empresa.nombre.ilike(patron), Empresa.email.ilike(patron),
                               Empresa.identificacion_fiscal.ilike(patron)))
        return list(db.session.scalars(q.order_by(Empresa.creado_en.desc()).limit(500)))

    def cambiar_estado_empresa(self, empresa_id, *, estado, motivo):
        self._exigir("superadmin.empresas")
        if estado not in {"activa", "suspendida", "cancelada"}: raise ErrorSuperAdministracion("Estado inválido")
        motivo = (motivo or "").strip()
        if estado != "activa" and not motivo: raise ErrorSuperAdministracion("El motivo es obligatorio")
        empresa = db.session.scalar(db.select(Empresa).where(
            Empresa.id == empresa_id, Empresa.eliminado.is_(False)).with_for_update())
        if not empresa: raise ErrorSuperAdministracion("Empresa no encontrada")
        anterior = empresa.estado; empresa.estado = estado
        empresa.motivo_suspension = None if estado == "activa" else motivo
        # Cierra sesiones existentes de todos los usuarios de la empresa.
        for usuario in empresa.usuarios: usuario.version_sesion += 1
        self._auditar("superadmin.empresa_estado", "Empresa", empresa.id,
                      {"estado_anterior": anterior, "estado": estado, "motivo": motivo or None})
        db.session.commit(); return empresa

    def listar_planes(self, *, incluir_inactivos=True):
        self._exigir("superadmin.planes")
        q = db.select(PlanSaaS)
        if not incluir_inactivos: q = q.where(PlanSaaS.activo.is_(True))
        return list(db.session.scalars(q.order_by(PlanSaaS.orden, PlanSaaS.nombre)))

    def editar_plan(self, plan_id, **datos):
        self._exigir("superadmin.planes")
        plan = db.session.get(PlanSaaS, plan_id)
        if not plan: raise ErrorSuperAdministracion("Plan no encontrado")
        permitidos = {"nombre", "descripcion", "precio_mensual", "precio_anual", "dias_prueba",
            "limite_productos", "limite_usuarios", "limite_movimientos_mes", "limite_sucursales",
            "limite_bodegas", "almacenamiento_mb", "funciones", "activo", "orden"}
        desconocidos = set(datos) - permitidos
        if desconocidos: raise ErrorSuperAdministracion(f"Campos de plan no editables: {', '.join(sorted(desconocidos))}")
        anterior = self._plan_dict(plan)
        try:
            for campo in ("precio_mensual", "precio_anual"):
                if campo in datos:
                    valor = Decimal(str(datos[campo]));
                    if valor < 0: raise ErrorSuperAdministracion("Los precios no pueden ser negativos")
                    setattr(plan, campo, valor)
            for campo in ("dias_prueba", "orden"):
                if campo in datos:
                    valor = int(datos[campo]);
                    if valor < 0: raise ErrorSuperAdministracion(f"{campo} no puede ser negativo")
                    setattr(plan, campo, valor)
            for campo in ("limite_productos", "limite_usuarios", "limite_movimientos_mes",
                          "limite_sucursales", "limite_bodegas", "almacenamiento_mb"):
                if campo in datos:
                    valor = None if datos[campo] is None else int(datos[campo])
                    if valor is not None and valor < 0: raise ErrorSuperAdministracion("Los límites no pueden ser negativos")
                    setattr(plan, campo, valor)
            if "nombre" in datos:
                nombre = (datos["nombre"] or "").strip()
                if not nombre: raise ErrorSuperAdministracion("El nombre es obligatorio")
                plan.nombre = nombre
            if "descripcion" in datos: plan.descripcion = (datos["descripcion"] or "").strip() or None
            if "activo" in datos:
                if not isinstance(datos["activo"], bool): raise ErrorSuperAdministracion("activo debe ser booleano")
                if not datos["activo"] and db.session.scalar(db.select(db.exists().where(
                        Suscripcion.plan_id == plan.id, Suscripcion.estado.in_(("prueba", "activa"))))):
                    raise ErrorSuperAdministracion("No se desactiva un plan con suscripciones vigentes")
                plan.activo = datos["activo"]
            if "funciones" in datos:
                if not isinstance(datos["funciones"], dict) or any(not isinstance(v, bool) for v in datos["funciones"].values()):
                    raise ErrorSuperAdministracion("Las funciones deben ser un objeto de booleanos")
                plan.funciones = dict(datos["funciones"])
            self._auditar("superadmin.plan_editado", "PlanSaaS", plan.id,
                          {"anterior": anterior, "nuevo": self._plan_dict(plan)})
            db.session.commit(); return plan
        except (IntegrityError, InvalidOperation, TypeError, ValueError) as exc:
            db.session.rollback()
            if isinstance(exc, ErrorSuperAdministracion): raise
            raise ErrorSuperAdministracion("Datos de plan inválidos o duplicados") from exc

    def listar_suscripciones(self, *, empresa_id=None, estado=None):
        self._exigir("superadmin.suscripciones")
        q = db.select(Suscripcion)
        if empresa_id: q = q.where(Suscripcion.empresa_id == empresa_id)
        if estado: q = q.where(Suscripcion.estado == estado)
        return list(db.session.scalars(q.order_by(Suscripcion.creado_en.desc()).limit(1000)))

    def listar_pagos(self, *, empresa_id=None, estado=None, proveedor=None):
        self._exigir("superadmin.pagos")
        q = db.select(Pago)
        if empresa_id: q = q.where(Pago.empresa_id == empresa_id)
        if estado: q = q.where(Pago.estado == estado)
        if proveedor: q = q.where(Pago.proveedor == proveedor.lower())
        return list(db.session.scalars(q.order_by(Pago.creado_en.desc()).limit(1000)))

    def listar_auditoria(self, *, empresa_id=None, accion=None, limite=200):
        self._exigir("superadmin.auditoria")
        q = db.select(Auditoria)
        if empresa_id is not None: q = q.where(Auditoria.empresa_id == empresa_id)
        if accion: q = q.where(Auditoria.accion == accion)
        return list(db.session.scalars(q.order_by(Auditoria.fecha.desc()).limit(min(max(int(limite), 1), 1000))))

    @staticmethod
    def _plan_dict(p):
        return {"nombre": p.nombre, "precio_mensual": str(p.precio_mensual),
            "precio_anual": str(p.precio_anual), "limite_productos": p.limite_productos,
            "limite_usuarios": p.limite_usuarios, "funciones": dict(p.funciones or {}), "activo": p.activo}
    def _exigir(self, permiso):
        decision = evaluar_permiso(self.actor, permiso)
        if not decision.permitido: raise PermissionError(decision.mensaje)
    def _auditar(self, accion, tipo, id_, datos):
        registrar_auditoria(accion=accion, modulo="superadministracion", usuario_id=self.actor.id,
            empresa_id=None, entidad_tipo=tipo, entidad_id=id_, datos_nuevos=datos)
