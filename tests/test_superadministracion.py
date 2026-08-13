import pytest

from app.models import Auditoria, Empresa, Inventario, PlanSaaS, Usuario, db
from app.services.inventario import ServicioInventario
from app.services.superadministracion import ErrorSuperAdministracion, ServicioSuperAdministracion
from tests.test_autenticacion import REGISTRO


def _preparar(app, client):
    client.post("/autenticacion/registro", data=REGISTRO); client.post("/autenticacion/salir")
    with app.app_context():
        empresa = db.session.scalar(db.select(Empresa))
        superadmin = Usuario(empresa_id=None, nombre="Super", email="super@nexustock.cl",
                             rol="super_admin", activo=True)
        superadmin.set_password("ClaveSuper123"); db.session.add(superadmin); db.session.commit()
        return superadmin.id, empresa.id


def _login(client):
    return client.post("/autenticacion/ingresar", data={"email":"super@nexustock.cl","password":"ClaveSuper123"})


def test_resumen_global_no_expone_inventario(app, client):
    ids=_preparar(app,client)
    with app.app_context():
        datos=ServicioSuperAdministracion(db.session.get(Usuario,ids[0])).resumen()
        assert datos["empresas"]==1 and datos["usuarios_empresariales"]==1
        assert "stock" not in datos and "inventario" not in datos


def test_suspender_empresa_revoca_sesiones_y_reactivar(app, client):
    ids=_preparar(app,client)
    with app.app_context():
        servicio=ServicioSuperAdministracion(db.session.get(Usuario,ids[0]))
        usuario=db.session.scalar(db.select(Usuario).where(Usuario.empresa_id==ids[1])); version=usuario.version_sesion
        empresa=servicio.cambiar_estado_empresa(ids[1],estado="suspendida",motivo="Incumplimiento")
        assert empresa.estado=="suspendida" and usuario.version_sesion==version+1
        servicio.cambiar_estado_empresa(ids[1],estado="activa",motivo=None)
        assert empresa.estado=="activa" and empresa.motivo_suspension is None


def test_suspension_exige_motivo(app, client):
    ids=_preparar(app,client)
    with app.app_context(),pytest.raises(ErrorSuperAdministracion):
        ServicioSuperAdministracion(db.session.get(Usuario,ids[0])).cambiar_estado_empresa(
            ids[1],estado="suspendida",motivo="")


def test_editar_plan_valida_precio_limites_y_funciones(app, client):
    ids=_preparar(app,client)
    with app.app_context():
        servicio=ServicioSuperAdministracion(db.session.get(Usuario,ids[0])); plan=db.session.scalar(db.select(PlanSaaS))
        servicio.editar_plan(plan.id,precio_mensual=12345,limite_usuarios=7,
                             funciones={"productos":True,"analitica":False})
        assert plan.precio_mensual==12345 and plan.limite_usuarios==7
        with pytest.raises(ErrorSuperAdministracion): servicio.editar_plan(plan.id,precio_mensual=-1)
        with pytest.raises(ErrorSuperAdministracion): servicio.editar_plan(plan.id,funciones={"api":"sí"})


def test_no_desactiva_plan_con_suscripcion_vigente(app, client):
    ids=_preparar(app,client)
    with app.app_context():
        plan=db.session.scalar(db.select(PlanSaaS)); servicio=ServicioSuperAdministracion(db.session.get(Usuario,ids[0]))
        with pytest.raises(ErrorSuperAdministracion): servicio.editar_plan(plan.id,activo=False)


def test_admin_empresa_no_accede_servicio_global(app, client):
    ids=_preparar(app,client)
    with app.app_context():
        admin=db.session.scalar(db.select(Usuario).where(Usuario.empresa_id==ids[1]))
        with pytest.raises(PermissionError): ServicioSuperAdministracion(admin)


def test_superadmin_no_puede_operar_inventario(app, client):
    ids=_preparar(app,client)
    with app.app_context():
        superadmin=db.session.get(Usuario,ids[0])
        from app.services.contexto import ContextoOperacion
        from app.models import Bodega
        bodega=db.session.scalar(db.select(Bodega))
        with pytest.raises(PermissionError):
            ServicioInventario(superadmin,ContextoOperacion(ids[1],bodega.sucursal,bodega))


def test_auditoria_global_filtra_empresa_sin_modificarla(app, client):
    ids=_preparar(app,client)
    with app.app_context():
        servicio=ServicioSuperAdministracion(db.session.get(Usuario,ids[0]))
        datos=servicio.listar_auditoria(empresa_id=ids[1])
        assert datos and all(a.empresa_id==ids[1] for a in datos)
        registro=datos[0]; registro.accion="manipulada"
        with pytest.raises(ValueError): db.session.commit()
        db.session.rollback()


def test_api_superadmin_y_bloqueo_empresarial(app, client):
    ids=_preparar(app,client); _login(client)
    assert client.get("/api/superadmin/resumen").status_code==200
    assert client.get("/api/productos").status_code==403
    respuesta=client.post(f"/api/superadmin/empresas/{ids[1]}/estado",json={
        "estado":"suspendida","motivo":"Revisión administrativa"})
    assert respuesta.status_code==200 and respuesta.get_json()["estado"]=="suspendida"


def test_admin_empresa_no_accede_rutas_globales(app, client):
    _preparar(app,client)
    client.post("/autenticacion/ingresar",data={"email":REGISTRO["email"],"password":REGISTRO["password"]})
    assert client.get("/api/superadmin/resumen").status_code==403


def test_cli_crea_superadmin_global(app):
    corredor=app.test_cli_runner()
    resultado=corredor.invoke(args=["crear-super-admin","--nombre","Raíz","--email","raiz@nexustock.cl"],
        input="ClaveRaiz123\nClaveRaiz123\n")
    assert resultado.exit_code==0
    with app.app_context():
        usuario=db.session.scalar(db.select(Usuario).where(Usuario.email=="raiz@nexustock.cl"))
        assert usuario.rol=="super_admin" and usuario.empresa_id is None