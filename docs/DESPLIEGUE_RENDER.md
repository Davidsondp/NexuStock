# Despliegue de NexuStock en Render

## 1. Crear el servicio

Conecta el repositorio en Render y selecciona **New Blueprint**. El archivo `render.yaml`
crearÃ¡ el servicio web y una base PostgreSQL privada. No copies credenciales al repositorio.

## 2. Completar variables secretas

En el panel del servicio configura:

- `TRUSTED_HOSTS`: dominio pÃºblico exacto de Render, por ejemplo
  `nexustock.onrender.com`. Agrega el dominio propio separado por coma si corresponde.
- `MAIL_SERVER`, `MAIL_USERNAME`, `MAIL_PASSWORD` y `MAIL_DEFAULT_SENDER`.
- Los secretos generados (`SECRET_KEY`, `WEBHOOK_PAGOS_SECRET` y
  `LIMITE_SOLICITUDES_SECRET`) deben conservarse entre despliegues.

`DATABASE_URL` se obtiene automÃ¡ticamente de la base administrada. Nunca la publiques ni la
pegues en incidencias o conversaciones.

## 3. Primera publicaciÃ³n

El paso previo al despliegue ejecuta, en este orden:

```bash
flask --app run.py db upgrade
flask --app run.py seed-planes
```

La migraciÃ³n inicial estÃ¡ diseÃ±ada para una base vacÃ­a. Si ya existe una base con tablas de
una versiÃ³n anterior, no ejecutes `stamp` ni `upgrade` a ciegas: primero exporta Ãºnicamente su
esquema y compara cada tabla con la migraciÃ³n.

## 4. Crear y comprobar la administraciÃ³n

Desde **Shell** del servicio ejecuta:

```bash
flask --app run.py crear-super-admin
flask --app run.py verificar-produccion
```

Comprueba tambiÃ©n:

- `GET /estado` devuelve `200` y `estado: correcto`.
- `GET /estado/preparacion` devuelve `200` y `estado: preparado`.
- El registro del despliegue muestra una sola revisiÃ³n de Alembic aplicada.

## 5. Cambios futuros de base de datos

Genera la migraciÃ³n localmente despuÃ©s de modificar los modelos:

```bash
flask --app run.py db migrate -m "descripciÃ³n breve"
flask --app run.py db upgrade
pytest -q
```

Revisa manualmente `upgrade()` y `downgrade()` y pruÃ©balos en PostgreSQL de staging. SQLite
no sustituye esa prueba porque su emulaciÃ³n de cambios de esquema tiene restricciones distintas.
Versiona la migraciÃ³n junto con el cÃ³digo. No edites una revisiÃ³n ya aplicada en producciÃ³n;
crea una revisiÃ³n nueva.

## 6. RecuperaciÃ³n

Antes de una migraciÃ³n destructiva crea un respaldo de PostgreSQL. Para volver atrÃ¡s, publica
el cÃ³digo anterior y usa `flask --app run.py db downgrade <revision>` solamente si ese
`downgrade()` fue probado sobre PostgreSQL y no elimina informaciÃ³n necesaria. Cuando exista riesgo de pÃ©rdida,
restaura el respaldo en una base nueva y cambia la conexiÃ³n despuÃ©s de validarla.