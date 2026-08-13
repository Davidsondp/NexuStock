# NexuStock v2

Reconstrucción limpia del SaaS de inventario según el Prompt Maestro.

## Desarrollo

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
flask --app run.py db upgrade
flask --app run.py seed-planes
flask --app run.py run
```

No uses `db.create_all()` como reemplazo de migraciones.

La carpeta `migrations/` ya forma parte del proyecto. `db init` y la migración inicial no se
repiten. Cuando cambien los modelos, genera una revisión nueva, revísala y pruébala antes de
aplicarla:

```bash
flask --app run.py db migrate -m "descripción del cambio"
flask --app run.py db upgrade
```

## Producción en Render

El archivo `render.yaml` provisiona PostgreSQL y el servicio web. Antes de cada despliegue,
Render ejecuta las migraciones y configura idempotentemente los planes. La sonda de vida es
`/estado`; `/estado/preparacion` además verifica la conexión a PostgreSQL.

Consulta [docs/DESPLIEGUE_RENDER.md](docs/DESPLIEGUE_RENDER.md) para configurar secretos,
crear el primer Super Admin, verificar el despliegue y recuperar una versión anterior.

## Flujo de compras

Las órdenes siguen el ciclo `borrador → creada → enviada → parcialmente_recibida → recibida`.
También pueden cancelarse antes de la primera recepción. Cada recepción confirmada actualiza
inventario y costo promedio en una única transacción, registra movimientos y auditoría, y
valida lotes, vencimientos y números de serie cuando el producto los exige.

## Flujo de ventas

Las ventas siguen `borrador → reservada → confirmada`. La reserva reduce la disponibilidad
sin alterar el stock físico; la confirmación libera la reserva y genera la salida definitiva.
Cancelar una venta reservada devuelve inmediatamente la disponibilidad.

## Motor de alertas

El motor evalúa por producto y bodega el stock bajo, sobrestock, riesgo de agotamiento,
falta de movimientos y recomendaciones de compra. Las reglas usan stock disponible,
umbrales configurados, consumo real de 30 días y plazo de entrega del proveedor. Mantiene
una sola alerta activa por regla y conserva el historial de alertas resueltas o ignoradas.

## Reportes y analítica

Los reportes básicos exponen productos, stock y movimientos dentro de las bodegas autorizadas.
La analítica avanzada calcula ventas confirmadas, ingresos, costo de ventas, margen bruto,
productos más vendidos, sobrestock, productos sin movimiento, valor actual y cobertura.
La rotación operativa se identifica expresamente como aproximación hasta disponer de snapshots
históricos que permitan calcular el inventario promedio contable.

## Exportaciones

Los reportes autorizados pueden descargarse en CSV UTF-8 o Excel XLSX. La exportación reutiliza
los filtros multiempresa y por bodega del servicio de reportes, exige la función comercial
correspondiente, registra auditoría y neutraliza entradas que una hoja de cálculo podría
interpretar como fórmulas.

## Gestión de usuarios

Los administradores empresariales crean y gestionan usuarios dentro del límite del plan, asignan
sucursales y aplican permisos especiales validados por el catálogo central. No pueden crear
Super Admin ni habilitar funciones ausentes del plan. Los cambios sensibles incrementan la
versión de sesión para cerrar accesos existentes y siempre se conserva un administrador activo.

## Configuración empresarial

La empresa administra su identidad comercial, ubicación, moneda, idioma, zona horaria,
personalización y preferencias de alertas mediante campos validados. El plan, los límites,
el estado comercial y la facturación se muestran como información de solo lectura y no pueden
modificarse desde la configuración empresarial.

## Pagos y suscripciones

Una empresa solicita un plan y ciclo con precio congelado, inicia un pago con referencia única
y espera la confirmación firmada del proveedor. El webhook verifica firma y antigüedad, valida
monto y moneda, procesa idempotentemente el evento y activa la suscripción en una sola
transacción. La capa de permisos únicamente consulta el resultado de esa suscripción.

## Super Administración

El Super Admin consulta indicadores globales, empresas, planes, suscripciones, pagos y auditoría.
Puede suspender o reactivar empresas y editar planes con validaciones, pero no elimina empresas,
modifica pagos confirmados ni opera inventarios empresariales. Cada cambio global queda auditado
y la suspensión de una empresa revoca las sesiones existentes de sus usuarios.

## Seguridad transversal

La aplicación aplica CSRF a formularios y APIs basadas en sesión, exige JSON en operaciones API,
limita rutas de autenticación mediante contadores persistentes anonimizados, genera identificadores
de solicitud y devuelve errores sin detalles internos. Todas las respuestas incorporan CSP,
protección contra marcos, `nosniff`, política de referente y restricciones de capacidades. En
producción también se exige HSTS, hosts autorizados y secretos independientes para webhooks y límites.
