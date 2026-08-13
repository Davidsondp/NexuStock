from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required

from ...permisos import requerir_permiso
from ...services.superadministracion import ErrorSuperAdministracion, ServicioSuperAdministracion

superadministracion_bp = Blueprint("superadministracion", __name__, url_prefix="/api/superadmin")


def _error(exc): return jsonify({"codigo": exc.codigo, "mensaje": str(exc)}), 400
def _empresa(e): return {"id": e.id, "nombre": e.nombre, "email": e.email,
    "identificacion_fiscal": e.identificacion_fiscal, "estado": e.estado,
    "motivo_suspension": e.motivo_suspension}
def _plan(p): return {"id": p.id, "codigo": p.codigo, "nombre": p.nombre,
    "precio_mensual": str(p.precio_mensual), "precio_anual": str(p.precio_anual),
    "limite_productos": p.limite_productos, "limite_usuarios": p.limite_usuarios,
    "limite_movimientos_mes": p.limite_movimientos_mes, "limite_sucursales": p.limite_sucursales,
    "limite_bodegas": p.limite_bodegas, "funciones": p.funciones, "activo": p.activo}


@superadministracion_bp.get("/resumen")
@login_required
@requerir_permiso("superadmin.dashboard")
def resumen(): return jsonify(ServicioSuperAdministracion(current_user).resumen())

@superadministracion_bp.get("/empresas")
@login_required
@requerir_permiso("superadmin.empresas")
def empresas():
    try: return jsonify({"empresas": [_empresa(e) for e in ServicioSuperAdministracion(current_user).listar_empresas(
        estado=request.args.get("estado"), buscar=request.args.get("buscar"))]})
    except ErrorSuperAdministracion as exc: return _error(exc)

@superadministracion_bp.post("/empresas/<int:empresa_id>/estado")
@login_required
@requerir_permiso("superadmin.empresas")
def cambiar_estado_empresa(empresa_id):
    try:
        d=request.get_json(silent=True) or {}
        return jsonify(_empresa(ServicioSuperAdministracion(current_user).cambiar_estado_empresa(
            empresa_id, estado=d.get("estado"), motivo=d.get("motivo"))))
    except ErrorSuperAdministracion as exc: return _error(exc)

@superadministracion_bp.get("/planes")
@login_required
@requerir_permiso("superadmin.planes")
def planes(): return jsonify({"planes": [_plan(p) for p in ServicioSuperAdministracion(current_user).listar_planes()]})

@superadministracion_bp.patch("/planes/<int:plan_id>")
@login_required
@requerir_permiso("superadmin.planes")
def editar_plan(plan_id):
    try: return jsonify(_plan(ServicioSuperAdministracion(current_user).editar_plan(plan_id, **(request.get_json(silent=True) or {}))))
    except ErrorSuperAdministracion as exc: return _error(exc)

@superadministracion_bp.get("/suscripciones")
@login_required
@requerir_permiso("superadmin.suscripciones")
def suscripciones():
    datos=ServicioSuperAdministracion(current_user).listar_suscripciones(
        empresa_id=request.args.get("empresa_id",type=int),estado=request.args.get("estado"))
    return jsonify({"suscripciones":[{"id":s.id,"empresa_id":s.empresa_id,"plan_id":s.plan_id,
        "estado":s.estado,"ciclo":s.ciclo,"fecha_inicio":s.fecha_inicio.isoformat(),
        "fecha_fin":s.fecha_fin.isoformat() if s.fecha_fin else None} for s in datos]})

@superadministracion_bp.get("/pagos")
@login_required
@requerir_permiso("superadmin.pagos")
def pagos():
    datos=ServicioSuperAdministracion(current_user).listar_pagos(empresa_id=request.args.get("empresa_id",type=int),
        estado=request.args.get("estado"),proveedor=request.args.get("proveedor"))
    return jsonify({"pagos":[{"id":p.id,"empresa_id":p.empresa_id,"proveedor":p.proveedor,
        "referencia_externa":p.referencia_externa,"estado":p.estado,"monto":str(p.monto),
        "moneda":p.moneda} for p in datos]})

@superadministracion_bp.get("/auditoria")
@login_required
@requerir_permiso("superadmin.auditoria")
def auditoria():
    datos=ServicioSuperAdministracion(current_user).listar_auditoria(empresa_id=request.args.get("empresa_id",type=int),
        accion=request.args.get("accion"),limite=request.args.get("limite",200))
    return jsonify({"auditoria":[{"id":a.id,"empresa_id":a.empresa_id,"usuario_id":a.usuario_id,
        "accion":a.accion,"modulo":a.modulo,"entidad_tipo":a.entidad_tipo,"entidad_id":a.entidad_id,
        "fecha":a.fecha.isoformat()} for a in datos]})