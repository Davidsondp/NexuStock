"use strict";

const cuerpo = document.body;

const apiSuscripciones = (
    cuerpo.dataset.apiSuscripciones
);

const checkoutWebpaySufijo = (
    cuerpo.dataset.checkoutWebpaySufijo
    || "/checkout/webpay"
);

const checkoutMercadoPagoSufijo = (
    cuerpo.dataset.checkoutMercadopagoSufijo
    || "/checkout/mercadopago"
);

const puedeSolicitar = (
    cuerpo.dataset.puedeSolicitar === "true"
);

const estado = {
    suscripcion: null,
    planes_disponibles: [],
    catalogo_capacidades: [],
    solicitudes: [],
};

const etiquetasLimites = Object.freeze({
    productos: "Productos",
    usuarios: "Usuarios",
    movimientos_mes: "Movimientos mensuales",
    sucursales: "Sucursales",
    bodegas: "Bodegas",
    almacenamiento_mb: "Almacenamiento",
});

const etiquetasGrupos = Object.freeze({
    operacion: "Operaci\u00f3n",
    gestion: "Gesti\u00f3n",
    inteligencia: "Inteligencia",
    escala: "Escala empresarial",
});

function elemento(identificador) {
    return document.getElementById(
        identificador,
    );
}

function tokenCsrf() {
    return document.querySelector(
        'input[name="csrf_token"]',
    )?.value || "";
}

async function solicitarJson(
    ruta,
    opciones = {},
) {
    const encabezados = new Headers(
        opciones.headers || {},
    );

    encabezados.set(
        "Accept",
        "application/json",
    );

    if (opciones.body) {
        encabezados.set(
            "Content-Type",
            "application/json",
        );
    }

    const csrf = tokenCsrf();

    if (csrf) {
        encabezados.set(
            "X-CSRFToken",
            csrf,
        );
    }

    const respuesta = await fetch(
        ruta,
        {
            ...opciones,
            headers: encabezados,
        },
    );

    const datos = await respuesta.json()
        .catch(() => ({}));

    if (!respuesta.ok) {
        throw new Error(
            datos.mensaje
            || "No fue posible completar la operaci\u00f3n.",
        );
    }

    return datos;
}

function notificar(
    mensaje,
    tipo = "exito",
) {
    const notificacion = elemento(
        "notificacion",
    );

    if (!notificacion) {
        return;
    }

    notificacion.textContent = mensaje;
    notificacion.dataset.tipo = tipo;
    notificacion.hidden = false;

    window.clearTimeout(
        notificar.temporizador,
    );

    notificar.temporizador = window.setTimeout(
        () => {
            notificacion.hidden = true;
        },
        4500,
    );
}

function actualizarEstadoCheckout(
    mensaje,
    tipo = "procesando",
) {
    const indicador = elemento(
        "estado-checkout",
    );

    if (!indicador) {
        return;
    }

    indicador.textContent = mensaje || "";
    indicador.dataset.tipo = tipo;
    indicador.hidden = !mensaje;
}

function redireccionarAWebpay(datos) {
    const formulario = elemento(
        "formulario-redireccion-webpay",
    );
    const token = elemento(
        "token-ws-webpay",
    );
    const url = String(
        datos?.url_redireccion || "",
    ).trim();
    const tokenWs = String(
        datos?.token || datos?.token_ws || "",
    ).trim();

    if (!formulario || !token || !url || !tokenWs) {
        throw new Error(
            "Webpay no entregó los datos necesarios para continuar.",
        );
    }

    let destino;

    try {
        destino = new URL(url);
    }
    catch (_error) {
        throw new Error(
            "Webpay entregó una dirección de pago inválida.",
        );
    }

    if (destino.protocol !== "https:") {
        throw new Error(
            "La dirección de pago de Webpay no es segura.",
        );
    }

    formulario.action = destino.href;
    token.value = tokenWs;
    actualizarEstadoCheckout(
        "Redirigiendo de forma segura a Webpay...",
    );
    formulario.submit();
}

async function iniciarCheckoutWebpay(
    solicitud,
    boton,
) {
    if (!solicitud?.id) {
        notificar(
            "La solicitud de cambio no es válida.",
            "error",
        );
        return;
    }

    const textoOriginal = boton?.textContent;

    if (boton) {
        boton.disabled = true;
        boton.textContent = "Conectando con Webpay...";
    }

    actualizarEstadoCheckout(
        "Preparando el pago seguro con Webpay...",
    );

    try {
        const pago = await solicitarJson(
            (
                `${apiSuscripciones}/solicitudes/`
                + `${solicitud.id}`
                + checkoutWebpaySufijo
            ),
            {
                method: "POST",
                body: JSON.stringify({}),
            },
        );

        redireccionarAWebpay(pago);
    }
    catch (error) {
        actualizarEstadoCheckout(
            error.message,
            "error",
        );
        notificar(
            error.message,
            "error",
        );

        if (boton) {
            boton.disabled = false;
            boton.textContent = textoOriginal;
        }
    }
}

async function iniciarCheckoutMercadoPago(
    solicitud,
    boton,
) {
    if (!solicitud?.id) {
        notificar(
            "La solicitud de cambio no es válida.",
            "error",
        );
        return;
    }

    const textoOriginal = boton?.textContent;

    if (boton) {
        boton.disabled = true;
        boton.textContent = "Conectando con Mercado Pago...";
    }

    actualizarEstadoCheckout(
        "Preparando el pago seguro con Mercado Pago...",
    );

    try {
        const pago = await solicitarJson(
            (
                `${apiSuscripciones}/solicitudes/`
                + `${solicitud.id}`
                + checkoutMercadoPagoSufijo
            ),
            {
                method: "POST",
                body: JSON.stringify({}),
            },
        );
        const destino = new URL(
            String(pago.url_redireccion || ""),
        );

        if (destino.protocol !== "https:") {
            throw new Error(
                "Mercado Pago entregó una dirección de pago insegura.",
            );
        }

        actualizarEstadoCheckout(
            "Redirigiendo de forma segura a Mercado Pago...",
        );
        window.location.assign(destino.href);
    }
    catch (error) {
        const mensaje = (
            error instanceof TypeError
                ? "Mercado Pago entregó una dirección de pago inválida."
                : error.message
        );
        actualizarEstadoCheckout(mensaje, "error");
        notificar(mensaje, "error");

        if (boton) {
            boton.disabled = false;
            boton.textContent = textoOriginal;
        }
    }
}

function textoCapitalizado(valor) {
    const texto = String(valor || "")
        .replaceAll("_", " ");

    if (!texto) {
        return "Sin informaci\u00f3n";
    }

    return (
        texto.charAt(0).toUpperCase()
        + texto.slice(1)
    );
}

function fechaLocal(valor) {
    if (!valor) {
        return "Sin vencimiento";
    }

    const fecha = new Date(valor);

    if (Number.isNaN(fecha.getTime())) {
        return "Sin vencimiento";
    }

    return new Intl.DateTimeFormat(
        "es-CL",
        {
            day: "2-digit",
            month: "short",
            year: "numeric",
        },
    ).format(fecha);
}

function precioPlan(
    plan,
    ciclo,
) {
    const valor = Number(
        ciclo === "anual"
            ? plan.precio_anual
            : plan.precio_mensual,
    );

    if (!Number.isFinite(valor)) {
        return "Consultar";
    }

    return new Intl.NumberFormat(
        "es-CL",
        {
            style: "currency",
            currency: plan.moneda || "CLP",
            maximumFractionDigits: 0,
        },
    ).format(valor);
}

function limiteVisible(
    codigo,
    valor,
) {
    if (valor === null || valor === undefined) {
        return "Sin l\u00edmite";
    }

    if (codigo === "almacenamiento_mb") {
        if (Number(valor) >= 1024) {
            const gigabytes = (
                Number(valor) / 1024
            );

            return (
                `${gigabytes.toLocaleString("es-CL")} GB`
            );
        }

        return `${valor} MB`;
    }

    return Number(valor).toLocaleString(
        "es-CL",
    );
}

function limpiar(elementoDestino) {
    elementoDestino.replaceChildren();
}

function crear(
    etiqueta,
    clase,
    texto,
) {
    const nodo = document.createElement(
        etiqueta,
    );

    if (clase) {
        nodo.className = clase;
    }

    if (texto !== undefined) {
        nodo.textContent = texto;
    }

    return nodo;
}

function solicitudPendiente() {
    return estado.solicitudes.find(
        (solicitud) => (
            solicitud.estado === "pendiente"
        ),
    );
}

function renderizarResumen() {
    const suscripcion = estado.suscripcion;

    elemento(
        "resumen-plan-actual",
    ).textContent = (
        suscripcion.plan_nombre
        || suscripcion.plan
    );

    elemento(
        "resumen-estado-suscripcion",
    ).textContent = textoCapitalizado(
        suscripcion.estado,
    );

    elemento(
        "resumen-vigencia",
    ).textContent = fechaLocal(
        suscripcion.fecha_fin,
    );

    elemento(
        "resumen-ciclo",
    ).textContent = textoCapitalizado(
        suscripcion.ciclo,
    );
}

function renderizarLimites() {
    const contenedor = elemento(
        "lista-limites-plan",
    );

    limpiar(contenedor);

    for (
        const [codigo, etiqueta]
        of Object.entries(etiquetasLimites)
    ) {
        const tarjeta = crear(
            "article",
            "planes-limite",
        );

        tarjeta.append(
            crear(
                "span",
                "planes-limite__nombre",
                etiqueta,
            ),
            crear(
                "strong",
                "planes-limite__valor",
                limiteVisible(
                    codigo,
                    estado.suscripcion
                        .limites[codigo],
                ),
            ),
        );

        contenedor.append(tarjeta);
    }
}

function capacidadesIncluidas(plan) {
    return plan.capacidades.filter(
        (capacidad) => capacidad.incluida,
    ).length;
}

function botonSolicitar(plan) {
    const boton = crear(
        "button",
        "boton boton--primario",
    );

    boton.type = "button";

    const esActual = (
        plan.codigo
        === estado.suscripcion.plan
    );

    const pendiente = solicitudPendiente();

    if (esActual) {
        boton.textContent = "Plan actual";
        boton.disabled = true;
        return boton;
    }

    if (!puedeSolicitar) {
        boton.textContent = "Sin autorizaci\u00f3n";
        boton.disabled = true;
        return boton;
    }

    if (pendiente) {
        boton.textContent = "Solicitud pendiente";
        boton.disabled = true;
        return boton;
    }

    boton.textContent = "Solicitar cambio";
    boton.dataset.planCodigo = plan.codigo;

    boton.addEventListener(
        "click",
        () => solicitarCambio(plan),
    );

    return boton;
}

function renderizarPlanes() {
    const contenedor = elemento(
        "lista-planes",
    );
    const ciclo = elemento(
        "selector-ciclo",
    ).value;

    limpiar(contenedor);

    for (
        const plan
        of estado.planes_disponibles
    ) {
        const tarjeta = crear(
            "article",
            "plan-tarjeta",
        );

        if (
            plan.codigo
            === estado.suscripcion.plan
        ) {
            tarjeta.classList.add(
                "plan-tarjeta--actual",
            );
        }

        if (
            plan.codigo.includes(
                "profesional"
            )
        ) {
            tarjeta.classList.add(
                "plan-tarjeta--destacada",
            );

            tarjeta.append(
                crear(
                    "span",
                    "plan-tarjeta__recomendada",
                    "Más elegido",
                ),
            );
        }

        const cabecera = crear(
            "div",
            "plan-tarjeta__cabecera",
        );

        const identidad = crear("div");

        identidad.append(
            crear(
                "span",
                "plan-tarjeta__codigo",
                plan.codigo,
            ),
            crear(
                "h4",
                "",
                plan.nombre,
            ),
        );

        cabecera.append(
            identidad,
            crear(
                "span",
                "plan-tarjeta__precio",
                precioPlan(plan, ciclo),
            ),
        );

        const descripcion = crear(
            "p",
            "plan-tarjeta__descripcion",
            plan.descripcion
            || "Capacidad empresarial NexuStock.",
        );

        const resumen = crear(
            "div",
            "plan-tarjeta__resumen",
        );

        const incluidas = capacidadesIncluidas(
            plan,
        );

        resumen.append(
            crear(
                "div",
                "plan-tarjeta__cobertura",
                (
                    incluidas
                    + " de "
                    + plan.capacidades.length
                    + " capacidades"
                ),
            ),
        );

        const progreso = crear(
            "div",
            "plan-tarjeta__progreso",
        );

        const progresoActivo = crear(
            "span",
            "",
        );

        progresoActivo.style.width = (
            (
                incluidas
                / plan.capacidades.length
            )
            * 100
            + "%"
        );

        progreso.append(
            progresoActivo,
        );

        resumen.append(
            progreso,
        );

        const lista = crear(
            "ul",
            "plan-tarjeta__funciones",
        );

        for (
            const capacidad
            of plan.capacidades
                .filter(
                    (item) => item.incluida,
                )
                .slice(0, 6)
        ) {
            const item = crear(
                "li",
                "",
                capacidad.nombre,
            );

            lista.append(item);
        }

        tarjeta.append(
            cabecera,
            descripcion,
            resumen,
            lista,
            botonSolicitar(plan),
        );

        contenedor.append(tarjeta);
    }
}

function planesParaComparar() {
    const actual = {
        codigo: estado.suscripcion.plan,
        nombre: (
            estado.suscripcion.plan_nombre
            || estado.suscripcion.plan
        ),
        capacidades:
            estado.suscripcion.capacidades,
    };

    const codigos = new Set([actual.codigo]);

    return [
        actual,
        ...estado.planes_disponibles.filter(
            (plan) => {
                if (codigos.has(plan.codigo)) {
                    return false;
                }

                codigos.add(plan.codigo);
                return true;
            },
        ),
    ];
}

function crearCeldaEstado(capacidad) {
    const celda = crear(
        "div",
        "planes-comparador__estado",
    );

    if (capacidad?.incluida) {
        celda.classList.add(
            "planes-comparador__estado--incluida",
        );
        celda.textContent = "\u2713";
        celda.title = "Incluida";
        return celda;
    }

    if (
        capacidad?.estado
        === "proximamente"
    ) {
        celda.classList.add(
            "planes-comparador__estado--proxima",
        );
        celda.textContent = "Pr\u00f3ximamente";
        return celda;
    }

    celda.textContent = "\u2014";
    celda.title = "No incluida";

    return celda;
}

function renderizarComparador() {
    const contenedor = elemento(
        "comparador-capacidades",
    );
    const planes = planesParaComparar();

    limpiar(contenedor);

    for (
        const [grupo, etiqueta]
        of Object.entries(etiquetasGrupos)
    ) {
        const capacidades = (
            estado.catalogo_capacidades.filter(
                (capacidad) => (
                    capacidad.grupo === grupo
                ),
            )
        );

        if (!capacidades.length) {
            continue;
        }

        const seccion = crear(
            "section",
            "planes-comparador__grupo",
        );

        seccion.append(
            crear(
                "h4",
                "",
                etiqueta,
            ),
        );

        const tabla = crear(
            "div",
            "planes-comparador__tabla",
        );

        const encabezado = crear(
            "div",
            (
                "planes-comparador__fila "
                + "planes-comparador__encabezado"
            ),
        );

        encabezado.style.setProperty(
            "--cantidad-planes",
            String(planes.length),
        );

        encabezado.append(
            crear(
                "strong",
                "",
                "Capacidad",
            ),
        );

        for (const plan of planes) {
            encabezado.append(
                crear(
                    "strong",
                    "",
                    plan.nombre,
                ),
            );
        }

        tabla.append(encabezado);

        for (
            const capacidad
            of capacidades
        ) {
            const fila = crear(
                "div",
                "planes-comparador__fila",
            );

            fila.style.setProperty(
                "--cantidad-planes",
                String(planes.length),
            );

            const descripcion = crear(
                "div",
                "planes-comparador__capacidad",
            );

            descripcion.append(
                crear(
                    "strong",
                    "",
                    capacidad.nombre,
                ),
                crear(
                    "small",
                    "",
                    capacidad.descripcion,
                ),
            );

            fila.append(descripcion);

            for (const plan of planes) {
                const detalle = (
                    plan.capacidades.find(
                        (item) => (
                            item.codigo
                            === capacidad.codigo
                        ),
                    )
                );

                fila.append(
                    crearCeldaEstado(detalle),
                );
            }

            tabla.append(fila);
        }

        seccion.append(tabla);
        contenedor.append(seccion);
    }
}

function nombrePlanPorId(identificador) {
    return (
        estado.planes_disponibles.find(
            (plan) => (
                plan.id === identificador
            ),
        )?.nombre
        || `Plan ${identificador}`
    );
}

function renderizarSolicitudes() {
    const contenedor = elemento(
        "historial-solicitudes",
    );

    limpiar(contenedor);

    if (!estado.solicitudes.length) {
        contenedor.append(
            crear(
                "div",
                "planes-solicitudes__vacio",
                (
                    "No existen solicitudes "
                    + "de cambio registradas."
                ),
            ),
        );
        return;
    }

    for (
        const solicitud
        of estado.solicitudes
    ) {
        const fila = crear(
            "article",
            "solicitud-plan",
        );

        const detalle = crear("div");

        detalle.append(
            crear(
                "strong",
                "",
                nombrePlanPorId(
                    solicitud.plan_solicitado_id,
                ),
            ),
            crear(
                "span",
                "",
                (
                    textoCapitalizado(
                        solicitud.ciclo,
                    )
                    + " \u00b7 "
                    + solicitud.moneda
                    + " "
                    + Number(
                        solicitud.monto_esperado,
                    ).toLocaleString("es-CL")
                ),
            ),
        );

        const etiquetasEstado = {
            pendiente: "Pago pendiente",
            aprobada: "Activado automáticamente",
            rechazada: "Pago rechazado",
            cancelada: "Cancelado",
        };

        const estadoSolicitud = crear(
            "span",
            (
                "solicitud-plan__estado "
                + "solicitud-plan__estado--"
                + solicitud.estado
            ),
            etiquetasEstado[solicitud.estado]
                || textoCapitalizado(solicitud.estado),
        );

        fila.append(
            detalle,
            estadoSolicitud,
        );

        if (
            solicitud.estado === "pendiente"
            && puedeSolicitar
        ) {
            const botonPago = crear(
                "button",
                "boton boton--primario",
                "Pagar con Webpay",
            );

            botonPago.type = "button";
            botonPago.addEventListener(
                "click",
                () => iniciarCheckoutWebpay(
                    solicitud,
                    botonPago,
                ),
            );

            const botonMercadoPago = crear(
                "button",
                "boton boton--mercadopago",
                "Pagar con Mercado Pago",
            );

            botonMercadoPago.type = "button";
            botonMercadoPago.addEventListener(
                "click",
                () => iniciarCheckoutMercadoPago(
                    solicitud,
                    botonMercadoPago,
                ),
            );

            const boton = crear(
                "button",
                "boton boton--peligro",
                "Cancelar",
            );

            boton.type = "button";
            boton.addEventListener(
                "click",
                () => cancelarSolicitud(
                    solicitud,
                ),
            );

            fila.append(
                botonPago,
                botonMercadoPago,
                boton,
            );
        }

        contenedor.append(fila);
    }
}

function renderizarTodo() {
    renderizarResumen();
    renderizarLimites();
    renderizarPlanes();
    renderizarComparador();
    renderizarSolicitudes();

    elemento(
        "estado-planes",
    ).hidden = true;
}

async function cargarPlanes() {
    const indicador = elemento(
        "estado-planes",
    );

    indicador.hidden = false;
    indicador.textContent = (
        "Cargando planes..."
    );

    try {
        const datos = await solicitarJson(
            apiSuscripciones,
        );

        estado.suscripcion = datos.suscripcion;
        estado.planes_disponibles = (
            datos.planes_disponibles || []
        );
        estado.catalogo_capacidades = (
            datos.catalogo_capacidades || []
        );
        estado.solicitudes = (
            datos.solicitudes || []
        );

        renderizarTodo();
    }
    catch (error) {
        indicador.hidden = false;
        indicador.textContent = error.message;
        notificar(
            error.message,
            "error",
        );
    }
}

async function solicitarCambio(plan) {
    const ciclo = elemento(
        "selector-ciclo",
    ).value;

    const confirmado = window.confirm(
        (
            "Solicitar el cambio al plan "
            + plan.nombre
            + " con ciclo "
            + textoCapitalizado(ciclo)
            + "?"
        ),
    );

    if (!confirmado) {
        return;
    }

    try {
        await solicitarJson(
            `${apiSuscripciones}/solicitudes`,
            {
                method: "POST",
                body: JSON.stringify({
                    plan_codigo: plan.codigo,
                    ciclo,
                }),
            },
        );

        notificar(
            "Solicitud de cambio registrada.",
        );

        await cargarPlanes();
    }
    catch (error) {
        notificar(
            error.message,
            "error",
        );
    }
}

async function cancelarSolicitud(
    solicitud,
) {
    const confirmado = window.confirm(
        "Cancelar esta solicitud de cambio?",
    );

    if (!confirmado) {
        return;
    }

    try {
        await solicitarJson(
            (
                `${apiSuscripciones}/solicitudes/`
                + `${solicitud.id}/cancelar`
            ),
            {
                method: "POST",
            },
        );

        notificar(
            "Solicitud cancelada correctamente.",
        );

        await cargarPlanes();
    }
    catch (error) {
        notificar(
            error.message,
            "error",
        );
    }
}

function abrirMenu() {
    cuerpo.classList.add(
        "menu-abierto",
    );

    elemento(
        "abrir-menu",
    )?.setAttribute(
        "aria-expanded",
        "true",
    );
}

function cerrarMenu() {
    cuerpo.classList.remove(
        "menu-abierto",
    );

    elemento(
        "abrir-menu",
    )?.setAttribute(
        "aria-expanded",
        "false",
    );
}

function registrarEventos() {
    elemento(
        "selector-ciclo",
    )?.addEventListener(
        "change",
        renderizarPlanes,
    );

    elemento(
        "actualizar-planes",
    )?.addEventListener(
        "click",
        cargarPlanes,
    );

    elemento(
        "actualizar-planes-cabecera",
    )?.addEventListener(
        "click",
        cargarPlanes,
    );

    elemento(
        "abrir-menu",
    )?.addEventListener(
        "click",
        abrirMenu,
    );

    elemento(
        "cerrar-menu",
    )?.addEventListener(
        "click",
        cerrarMenu,
    );

    window.addEventListener(
        "keydown",
        (evento) => {
            if (evento.key === "Escape") {
                cerrarMenu();
            }
        },
    );
}

document.addEventListener(
    "DOMContentLoaded",
    () => {
        registrarEventos();
        cargarPlanes();
    },
);
