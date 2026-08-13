from flask import has_request_context, request

from ..models import Auditoria, db


def registrar_auditoria(*, accion: str, modulo: str, usuario_id=None, empresa_id=None,
                        entidad_tipo=None, entidad_id=None, descripcion=None,
                        datos_anteriores=None, datos_nuevos=None) -> Auditoria:
    registro = Auditoria(
        accion=accion, modulo=modulo, usuario_id=usuario_id, empresa_id=empresa_id,
        entidad_tipo=entidad_tipo, entidad_id=entidad_id, descripcion=descripcion,
        datos_anteriores=datos_anteriores, datos_nuevos=datos_nuevos,
        ip=request.remote_addr if has_request_context() else None,
        agente_usuario=str(request.user_agent)[:500] if has_request_context() else None,
        id_solicitud=request.headers.get("X-Request-ID") if has_request_context() else None,
    )
    db.session.add(registro)
    return registro
