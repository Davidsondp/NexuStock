"""Gestión empresarial segura de usuarios, roles, permisos y sesiones."""
from __future__ import annotations

from sqlalchemy.exc import IntegrityError

from ..models import Sucursal, Usuario, UsuarioSucursal, db
from ..permisos import (FUNCION_POR_PERMISO, PERMISOS_ROL, ROLES_EMPRESA,
                        evaluar_permiso, permisos_empresariales_conocidos)
from .auditoria import registrar_auditoria


class ErrorUsuario(ValueError):
    codigo = "usuario_invalido"


class LimiteUsuariosAlcanzado(ErrorUsuario):
    codigo = "limite_usuarios"


class ServicioUsuarios:
    def __init__(self, actor):
        self.actor = actor
        if not actor.empresa_id or actor.rol == "super_admin":
            raise PermissionError("Usuario sin ámbito empresarial")

    def listar(self, *, incluir_inactivos=False):
        self._exigir("usuarios.ver")
        consulta = db.select(Usuario).where(
            Usuario.empresa_id == self.actor.empresa_id, Usuario.eliminado.is_(False))
        if not incluir_inactivos:
            consulta = consulta.where(Usuario.activo.is_(True))
        return list(db.session.scalars(consulta.order_by(Usuario.nombre, Usuario.apellido)))

    def obtener(self, usuario_id, *, bloquear=False):
        self._exigir("usuarios.ver")
        consulta = db.select(Usuario).where(
            Usuario.id == usuario_id, Usuario.empresa_id == self.actor.empresa_id,
            Usuario.eliminado.is_(False))
        usuario = db.session.scalar(consulta.with_for_update() if bloquear else consulta)
        if not usuario:
            raise PermissionError("Usuario no autorizado")
        return usuario

    def crear(self, *, nombre, email, password, rol="empleado", apellido=None,
              sucursales_ids=None, permisos_especiales=None):
        self._exigir("usuarios.crear")
        self._validar_limite()
        rol = self._rol(rol)
        if rol == "admin_empresa":
            self._exigir("usuarios.gestionar_roles")
        sucursales = self._sucursales(sucursales_ids)
        permisos = self._permisos(permisos_especiales or {}, rol)
        try:
            usuario = Usuario(
                empresa_id=self.actor.empresa_id, nombre=self._texto(nombre, "El nombre"),
                apellido=(apellido or "").strip() or None, email=(email or "").strip().lower(),
                rol=rol, permisos_especiales=permisos, activo=True,
            )
            usuario.set_password(password)
            db.session.add(usuario); db.session.flush()
            for indice, sucursal in enumerate(sucursales):
                db.session.add(UsuarioSucursal(
                    empresa_id=self.actor.empresa_id, usuario_id=usuario.id,
                    sucursal_id=sucursal.id, es_principal=indice == 0))
            self._auditar(usuario, "creado", {"rol": rol, "sucursales": [s.id for s in sucursales]})
            db.session.commit(); return usuario
        except IntegrityError as exc:
            db.session.rollback(); raise ErrorUsuario("El correo ya está registrado") from exc
        except Exception:
            db.session.rollback(); raise

    def editar(self, usuario_id, *, nombre=None, apellido=None, email=None,
               rol=None, sucursales_ids=None, permisos_especiales=None):
        self._exigir("usuarios.editar")
        usuario = self.obtener(usuario_id, bloquear=True)
        anterior = {"nombre": usuario.nombre, "email": usuario.email, "rol": usuario.rol,
                    "permisos_especiales": dict(usuario.permisos_especiales or {})}
        nuevo_rol = self._rol(rol) if rol is not None else usuario.rol
        if nuevo_rol != usuario.rol:
            self._exigir("usuarios.gestionar_roles")
            if usuario.rol == "admin_empresa" and nuevo_rol != "admin_empresa":
                self._proteger_ultimo_admin(usuario)
        try:
            if nombre is not None: usuario.nombre = self._texto(nombre, "El nombre")
            if apellido is not None: usuario.apellido = (apellido or "").strip() or None
            if email is not None: usuario.email = (email or "").strip().lower()
            usuario.rol = nuevo_rol
            if permisos_especiales is not None:
                self._exigir("usuarios.gestionar_roles")
                usuario.permisos_especiales = self._permisos(permisos_especiales, nuevo_rol)
            if sucursales_ids is not None:
                sucursales = self._sucursales(sucursales_ids)
                usuario.asignaciones.clear(); db.session.flush()
                for indice, sucursal in enumerate(sucursales):
                    usuario.asignaciones.append(UsuarioSucursal(
                        empresa_id=self.actor.empresa_id, sucursal_id=sucursal.id,
                        es_principal=indice == 0))
            usuario.version_sesion += 1
            self._auditar(usuario, "editado", {"anterior": anterior, "rol": usuario.rol})
            db.session.commit(); return usuario
        except IntegrityError as exc:
            db.session.rollback(); raise ErrorUsuario("El correo ya está registrado") from exc
        except Exception:
            db.session.rollback(); raise

    def cambiar_password(self, usuario_id, password):
        self._exigir("usuarios.editar")
        usuario = self.obtener(usuario_id, bloquear=True)
        usuario.set_password(password); usuario.version_sesion += 1
        usuario.intentos_fallidos = 0; usuario.bloqueado_hasta = None
        self._auditar(usuario, "password_cambiada")
        db.session.commit(); return usuario

    def desactivar(self, usuario_id):
        self._exigir("usuarios.desactivar")
        usuario = self.obtener(usuario_id, bloquear=True)
        if usuario.id == self.actor.id:
            raise ErrorUsuario("No puedes desactivar tu propia cuenta")
        if usuario.rol == "admin_empresa": self._proteger_ultimo_admin(usuario)
        usuario.activo = False; usuario.version_sesion += 1
        self._auditar(usuario, "desactivado"); db.session.commit(); return usuario

    def reactivar(self, usuario_id):
        self._exigir("usuarios.editar"); self._validar_limite()
        usuario = self.obtener(usuario_id, bloquear=True)
        usuario.activo = True; usuario.version_sesion += 1
        self._auditar(usuario, "reactivado"); db.session.commit(); return usuario

    def revocar_sesiones(self, usuario_id):
        self._exigir("usuarios.editar")
        usuario = self.obtener(usuario_id, bloquear=True)
        usuario.version_sesion += 1
        self._auditar(usuario, "sesiones_revocadas"); db.session.commit(); return usuario

    def _validar_limite(self):
        limite = self.actor.empresa.suscripcion_actual.plan.limite_usuarios
        cantidad = db.session.scalar(db.select(db.func.count(Usuario.id)).where(
            Usuario.empresa_id == self.actor.empresa_id, Usuario.activo.is_(True),
            Usuario.eliminado.is_(False)))
        if limite is not None and cantidad >= limite:
            raise LimiteUsuariosAlcanzado("Se alcanzó el límite de usuarios activos del plan")

    def _sucursales(self, ids):
        try: ids_limpios = list(dict.fromkeys(int(i) for i in (ids or [])))
        except (TypeError, ValueError) as exc: raise ErrorUsuario("Las sucursales no son válidas") from exc
        if not ids_limpios: raise ErrorUsuario("Debe asignarse al menos una sucursal")
        sucursales = list(db.session.scalars(db.select(Sucursal).where(
            Sucursal.id.in_(ids_limpios), Sucursal.empresa_id == self.actor.empresa_id,
            Sucursal.activa.is_(True), Sucursal.eliminado.is_(False))))
        if len(sucursales) != len(ids_limpios): raise PermissionError("Sucursal fuera del ámbito empresarial")
        por_id = {s.id: s for s in sucursales}; return [por_id[i] for i in ids_limpios]

    def _permisos(self, permisos, rol):
        if not isinstance(permisos, dict): raise ErrorUsuario("Los permisos especiales deben ser un objeto")
        conocidos = permisos_empresariales_conocidos(); resultado = {}
        for permiso, valor in permisos.items():
            if permiso not in conocidos: raise ErrorUsuario(f"Permiso desconocido: {permiso}")
            if not isinstance(valor, bool): raise ErrorUsuario("Cada permiso especial debe ser verdadero o falso")
            if valor is True:
                funcion = FUNCION_POR_PERMISO.get(permiso)
                if funcion and not self.actor.empresa.suscripcion_actual.plan.tiene_funcion(funcion):
                    raise ErrorUsuario(f"El plan no incluye la función requerida por {permiso}")
            resultado[permiso] = valor
        return resultado

    def _proteger_ultimo_admin(self, usuario):
        cantidad = db.session.scalar(db.select(db.func.count(Usuario.id)).where(
            Usuario.empresa_id == self.actor.empresa_id, Usuario.rol == "admin_empresa",
            Usuario.activo.is_(True), Usuario.eliminado.is_(False)))
        if usuario.activo and cantidad <= 1:
            raise ErrorUsuario("La empresa debe conservar al menos un administrador activo")

    @staticmethod
    def _rol(rol):
        if rol not in ROLES_EMPRESA: raise ErrorUsuario("Rol empresarial inválido")
        return rol
    @staticmethod
    def _texto(valor, nombre):
        valor = (valor or "").strip()
        if not valor: raise ErrorUsuario(f"{nombre} es obligatorio")
        return valor
    def _exigir(self, permiso):
        decision = evaluar_permiso(self.actor, permiso, empresa_id=self.actor.empresa_id)
        if not decision.permitido: raise PermissionError(decision.mensaje)
    def _auditar(self, usuario, accion, datos=None):
        registrar_auditoria(accion=f"usuario.{accion}", modulo="usuarios", usuario_id=self.actor.id,
            empresa_id=self.actor.empresa_id, entidad_tipo="Usuario", entidad_id=usuario.id,
            datos_nuevos=datos or {"activo": usuario.activo, "rol": usuario.rol})