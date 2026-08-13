"use strict";

const API = Object.freeze({
    resumen: "/api/superadmin/resumen",
    empresas: "/api/superadmin/empresas",
    planes: "/api/superadmin/planes",
    suscripciones: "/api/superadmin/suscripciones",
    pagos: "/api/superadmin/pagos",
    auditoria: "/api/superadmin/auditoria",
});

const titulos = Object.freeze({
    resumen: "Panel global",
    empresas: "Empresas",
    planes: "Planes",
    suscripciones: "Suscripciones",
    pagos: "Pagos",
    auditoria: "Auditoría",
});

const estado = {
    seccion: "resumen",
    cargadas: new Set(),
};

function elemento(id) {
    return document.getElementById(id);
}

function asignarTexto(id, valor) {
    const destino = elemento(id);

    if (destino) {
        destino.textContent = valor ?? "—";
    }
}

function crearElemento(etiqueta, texto = "", clase = "") {
    const nodo = document.createElement(etiqueta);

    if (texto !== "") {
        nodo.textContent = String(texto);
    }

    if (clase) {
        nodo.className = clase;
    }

    return nodo;
}

function limpiar(nodo) {
    while (nodo?.firstChild) {
        nodo.removeChild(nodo.firstChild);
    }
}

function formatearNumero(valor) {
    return new Intl.NumberFormat("es-CL").format(Number(valor || 0));
}

function formatearDinero(valor, moneda = "CLP") {
    return new Intl.NumberFormat("es-CL", {
        style: "currency",
        currency: moneda,
        maximumFractionDigits: moneda === "CLP" ? 0 : 2,
    }).format(Number(valor || 0));
}

function formatearFecha(valor) {
    if (!valor) {
        return "—";
    }

    const fecha = new Date(valor);

    if (Number.isNaN(fecha.getTime())) {
        return "—";
    }

    return new Intl.DateTimeFormat("es-CL", {
        dateStyle: "medium",
        timeStyle: "short",
    }).format(fecha);
}

function notificar(mensaje) {
    const notificacion = elemento("notificacion");

    if (!notificacion) {
        return;
    }

    notificacion.textContent = mensaje;
    notificacion.hidden = false;

    window.clearTimeout(notificar.temporizador);

    notificar.temporizador = window.setTimeout(() => {
        notificacion.hidden = true;
    }, 4500);
}

async function solicitarJson(url, opciones = {}) {
    const respuesta = await fetch(url, {
        credentials: "same-origin",
        headers: {
            Accept: "application/json",
            ...(opciones.headers || {}),
        },
        ...opciones,
    });

    let datos = {};

    try {
        datos = await respuesta.json();
    } catch {
        datos = {};
    }

    if (!respuesta.ok) {
        throw new Error(
            datos.mensaje ||
            datos.error ||
            `La solicitud falló con estado ${respuesta.status}.`
        );
    }

    return datos;
}

function obtenerTokenCsrf() {
    return document.querySelector(
        'input[name="csrf_token"]'
    )?.value || "";
}

async function cambiarEstadoEmpresa(empresa, nuevoEstado) {
    let motivo = "";

    if (nuevoEstado !== "activa") {
        motivo = window.prompt(
            `Indica el motivo para suspender "${empresa.nombre}":`
        )?.trim() || "";

        if (!motivo) {
            notificar("La suspensión requiere un motivo.");
            return;
        }
    }

    const accion = nuevoEstado === "activa"
        ? "reactivar"
        : "suspender";

    const confirmado = window.confirm(
        `¿Confirmas que deseas ${accion} la empresa "${empresa.nombre}"?`
    );

    if (!confirmado) {
        return;
    }

    try {
        await solicitarJson(
            `${API.empresas}/${empresa.id}/estado`,
            {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": obtenerTokenCsrf(),
                },
                body: JSON.stringify({
                    estado: nuevoEstado,
                    motivo,
                }),
            }
        );

        estado.cargadas.delete("empresas");
        estado.cargadas.delete("resumen");

        await cargarEmpresas(true);
        notificar(
            nuevoEstado === "activa"
                ? "Empresa reactivada correctamente."
                : "Empresa suspendida correctamente."
        );
    } catch (error) {
        notificar(error.message);
    }
}

function claseEstado(valor) {
    if (["activa", "activo", "pagado", "prueba"].includes(valor)) {
        return "insignia insignia--exito";
    }

    if (["suspendida", "pendiente"].includes(valor)) {
        return "insignia insignia--advertencia";
    }

    if (["cancelada", "cancelado", "fallido"].includes(valor)) {
        return "insignia insignia--peligro";
    }

    return "insignia";
}

function crearInsignia(valor) {
    const texto = valor || "Sin estado";
    return crearElemento("span", texto, claseEstado(texto));
}

function cerrarMenu() {
    document.body.classList.remove("menu-abierto");
    elemento("abrir-menu")?.setAttribute("aria-expanded", "false");
}

function abrirMenu() {
    document.body.classList.add("menu-abierto");
    elemento("abrir-menu")?.setAttribute("aria-expanded", "true");
}

function mostrarSeccion(nombre) {
    if (!titulos[nombre]) {
        return;
    }

    estado.seccion = nombre;

    document.querySelectorAll("[data-contenido-seccion]").forEach((seccion) => {
        seccion.hidden = seccion.dataset.contenidoSeccion !== nombre;
    });

    document.querySelectorAll("[data-seccion]").forEach((boton) => {
        if (boton.dataset.seccion === nombre) {
            boton.setAttribute("aria-current", "page");
        } else {
            boton.removeAttribute("aria-current");
        }
    });

    asignarTexto("titulo-pagina", titulos[nombre]);
    cerrarMenu();
    cargarSeccion(nombre);
}

async function cargarResumen(forzar = false) {
    if (estado.cargadas.has("resumen") && !forzar) {
        return;
    }

    try {
        const [resumen, empresas, auditoria] = await Promise.all([
            solicitarJson(API.resumen),
            solicitarJson(`${API.empresas}?estado=activa`),
            solicitarJson(`${API.auditoria}?limite=6`),
        ]);

        asignarTexto("metrica-empresas", formatearNumero(resumen.empresas));
        asignarTexto(
            "metrica-empresas-activas",
            formatearNumero(resumen.empresas_activas)
        );
        asignarTexto(
            "metrica-usuarios",
            formatearNumero(resumen.usuarios_empresariales)
        );
        asignarTexto(
            "metrica-suscripciones",
            formatearNumero(resumen.suscripciones_activas)
        );
        asignarTexto(
            "metrica-pagos",
            formatearNumero(resumen.pagos_confirmados)
        );
        asignarTexto(
            "metrica-ingresos",
            formatearDinero(resumen.ingresos_confirmados)
        );

        renderizarEmpresasResumen((empresas.empresas || []).slice(0, 6));
        renderizarActividad(auditoria.auditoria || []);

        estado.cargadas.add("resumen");
    } catch (error) {
        notificar(error.message);
    }
}

function renderizarEmpresasResumen(empresas) {
    const cuerpo = elemento("resumen-empresas");

    if (!cuerpo) {
        return;
    }

    limpiar(cuerpo);

    if (!empresas.length) {
        const fila = crearElemento("tr");
        const celda = crearElemento(
            "td",
            "No existen empresas activas.",
            "tabla__vacio"
        );

        celda.colSpan = 3;
        fila.appendChild(celda);
        cuerpo.appendChild(fila);
        return;
    }

    empresas.forEach((empresa) => {
        const fila = crearElemento("tr");
        fila.appendChild(crearElemento("td", empresa.nombre || "—"));
        fila.appendChild(
            crearElemento("td", empresa.identificacion_fiscal || "—")
        );

        const estadoCelda = crearElemento("td");
        estadoCelda.appendChild(crearInsignia(empresa.estado));
        fila.appendChild(estadoCelda);

        cuerpo.appendChild(fila);
    });
}

function renderizarActividad(registros) {
    const lista = elemento("resumen-actividad");

    if (!lista) {
        return;
    }

    limpiar(lista);

    if (!registros.length) {
        lista.appendChild(
            crearElemento(
                "li",
                "No existe actividad registrada.",
                "estado-carga"
            )
        );
        return;
    }

    registros.forEach((registro) => {
        const item = crearElemento("li", "", "actividad");
        const punto = crearElemento("span", "", "actividad__punto");
        punto.setAttribute("aria-hidden", "true");

        const contenido = crearElemento("div");
        contenido.appendChild(
            crearElemento(
                "p",
                registro.accion || "Actividad registrada",
                "actividad__titulo"
            )
        );
        contenido.appendChild(
            crearElemento(
                "p",
                `${registro.modulo || "sistema"} · ${formatearFecha(registro.fecha)}`,
                "actividad__detalle"
            )
        );

        item.appendChild(punto);
        item.appendChild(contenido);
        lista.appendChild(item);
    });
}

async function cargarEmpresas(forzar = false) {
    if (estado.cargadas.has("empresas") && !forzar) {
        return;
    }

    const parametros = new URLSearchParams();
    const buscar = elemento("filtro-empresa-buscar")?.value.trim();
    const estadoEmpresa = elemento("filtro-empresa-estado")?.value;

    if (buscar) {
        parametros.set("buscar", buscar);
    }

    if (estadoEmpresa) {
        parametros.set("estado", estadoEmpresa);
    }

    const cuerpo = elemento("tabla-empresas");

    if (cuerpo) {
        limpiar(cuerpo);
        const fila = crearElemento("tr");
        const celda = crearElemento(
            "td",
            "Cargando empresas…",
            "estado-carga"
        );

        celda.colSpan = 5;
        fila.appendChild(celda);
        cuerpo.appendChild(fila);
    }

    try {
        const consulta = parametros.toString();
        const url = consulta
            ? `${API.empresas}?${consulta}`
            : API.empresas;

        const datos = await solicitarJson(url);

        renderizarEmpresas(datos.empresas || []);
        estado.cargadas.add("empresas");
    } catch (error) {
        renderizarErrorTabla(
            "tabla-empresas",
            5,
            error.message
        );
        notificar(error.message);
    }
}

function renderizarEmpresas(empresas) {
    const cuerpo = elemento("tabla-empresas");

    if (!cuerpo) {
        return;
    }

    limpiar(cuerpo);

    if (!empresas.length) {
        const fila = crearElemento("tr");
        const celda = crearElemento(
            "td",
            "No se encontraron empresas.",
            "tabla__vacio"
        );

        celda.colSpan = 5;
        fila.appendChild(celda);
        cuerpo.appendChild(fila);
        return;
    }

    empresas.forEach((empresa) => {
        const fila = crearElemento("tr");

        fila.appendChild(
            crearElemento("td", empresa.nombre || "—")
        );

        fila.appendChild(
            crearElemento("td", empresa.email || "—")
        );

        fila.appendChild(
            crearElemento(
                "td",
                empresa.identificacion_fiscal || "—"
            )
        );

        const celdaEstado = crearElemento("td");
        celdaEstado.appendChild(crearInsignia(empresa.estado));
        fila.appendChild(celdaEstado);

        const celdaAcciones = crearElemento("td");
        const detalle = empresa.motivo_suspension
            ? `Motivo: ${empresa.motivo_suspension}`
            : "Sin observaciones";

        const boton = crearElemento(
            "button",
            "Ver estado",
            "boton boton--secundario boton--pequeno"
        );

        boton.type = "button";
        boton.addEventListener("click", () => {
            notificar(
                `${empresa.nombre}: ${empresa.estado}. ${detalle}`
            );
        });

        celdaAcciones.appendChild(boton);

const botonEstado = crearElemento(
    "button",
    empresa.estado === "activa" ? "Suspender" : "Reactivar",
    empresa.estado === "activa"
        ? "boton boton--peligro boton--pequeno"
        : "boton boton--primario boton--pequeno"
);

botonEstado.type = "button";

botonEstado.addEventListener("click", () => {
    cambiarEstadoEmpresa(
        empresa,
        empresa.estado === "activa" ? "suspendida" : "activa"
    );
});

celdaAcciones.appendChild(botonEstado);
fila.appendChild(celdaAcciones);
        cuerpo.appendChild(fila);
    });
}

function renderizarErrorTabla(id, columnas, mensaje) {
    const cuerpo = elemento(id);

    if (!cuerpo) {
        return;
    }

    limpiar(cuerpo);

    const fila = crearElemento("tr");
    const celda = crearElemento(
        "td",
        mensaje || "No fue posible cargar la información.",
        "tabla__vacio"
    );

    celda.colSpan = columnas;
    fila.appendChild(celda);
    cuerpo.appendChild(fila);
}

async function cargarPlanes(forzar = false) {
    if (estado.cargadas.has("planes") && !forzar) {
        return;
    }

    const contenedor = elemento("lista-planes");

    if (contenedor) {
        limpiar(contenedor);
        contenedor.appendChild(
            crearElemento(
                "article",
                "Cargando planes…",
                "tarjeta estado-carga"
            )
        );
    }

    try {
        const datos = await solicitarJson(API.planes);
        renderizarPlanes(datos.planes || []);
        estado.cargadas.add("planes");
    } catch (error) {
        renderizarErrorPlanes(error.message);
        notificar(error.message);
    }
}

function renderizarPlanes(planes) {
    const contenedor = elemento("lista-planes");

    if (!contenedor) {
        return;
    }

    limpiar(contenedor);

    if (!planes.length) {
        contenedor.appendChild(
            crearElemento(
                "article",
                "No existen planes configurados.",
                "tarjeta estado-carga"
            )
        );
        return;
    }

    planes.forEach((plan) => {
        const tarjeta = crearElemento(
            "article",
            "",
            "tarjeta"
        );

        const cabecera = crearElemento(
            "div",
            "",
            "tarjeta__cabecera"
        );

        const encabezado = crearElemento("div");

        encabezado.appendChild(
            crearElemento(
                "h3",
                plan.nombre || plan.codigo || "Plan",
                "tarjeta__titulo"
            )
        );

        encabezado.appendChild(
            crearElemento(
                "p",
                plan.codigo || "Sin código",
                "tarjeta__descripcion"
            )
        );

        cabecera.appendChild(encabezado);
        cabecera.appendChild(
            crearInsignia(plan.activo ? "activo" : "inactivo")
        );

        tarjeta.appendChild(cabecera);

        const precioMensual = crearElemento(
            "p",
            formatearDinero(plan.precio_mensual),
            "metrica__valor"
        );

        tarjeta.appendChild(precioMensual);

        tarjeta.appendChild(
            crearElemento(
                "p",
                `${formatearDinero(plan.precio_anual)} al año`,
                "metrica__detalle"
            )
        );

        const limites = crearElemento(
            "ul",
            "",
            "lista-actividad"
        );

        agregarDetallePlan(
            limites,
            "Productos",
            formatearLimite(plan.limite_productos)
        );

        agregarDetallePlan(
            limites,
            "Usuarios",
            formatearLimite(plan.limite_usuarios)
        );

        agregarDetallePlan(
            limites,
            "Movimientos mensuales",
            formatearLimite(plan.limite_movimientos_mes)
        );

        agregarDetallePlan(
            limites,
            "Sucursales",
            formatearLimite(plan.limite_sucursales)
        );

        agregarDetallePlan(
            limites,
            "Bodegas",
            formatearLimite(plan.limite_bodegas)
        );

        tarjeta.appendChild(limites);

        const funcionesActivas = Object.entries(plan.funciones || {})
            .filter(([, habilitada]) => habilitada === true)
            .map(([funcion]) => funcion.replaceAll("_", " "));

        tarjeta.appendChild(
            crearElemento(
                "p",
                funcionesActivas.length
                    ? `Funciones: ${funcionesActivas.join(", ")}`
                    : "Sin funciones adicionales habilitadas.",
                "tarjeta__descripcion"
            )
        );

        contenedor.appendChild(tarjeta);
    });
}

function agregarDetallePlan(lista, nombre, valor) {
    const item = crearElemento("li", "", "actividad");
    const punto = crearElemento(
        "span",
        "",
        "actividad__punto"
    );

    punto.setAttribute("aria-hidden", "true");

    const contenido = crearElemento("div");

    contenido.appendChild(
        crearElemento(
            "p",
            nombre,
            "actividad__titulo"
        )
    );

    contenido.appendChild(
        crearElemento(
            "p",
            valor,
            "actividad__detalle"
        )
    );

    item.appendChild(punto);
    item.appendChild(contenido);
    lista.appendChild(item);
}

function formatearLimite(valor) {
    if (valor === null || valor === undefined) {
        return "Ilimitado";
    }

    return formatearNumero(valor);
}

function renderizarErrorPlanes(mensaje) {
    const contenedor = elemento("lista-planes");

    if (!contenedor) {
        return;
    }

    limpiar(contenedor);

    contenedor.appendChild(
        crearElemento(
            "article",
            mensaje || "No fue posible cargar los planes.",
            "tarjeta estado-carga"
        )
    );
}

async function cargarSuscripciones(forzar = false) {
    if (estado.cargadas.has("suscripciones") && !forzar) {
        return;
    }

    mostrarCargaTabla(
        "tabla-suscripciones",
        7,
        "Cargando suscripciones…"
    );

    try {
        const datos = await solicitarJson(API.suscripciones);
        renderizarSuscripciones(datos.suscripciones || []);
        estado.cargadas.add("suscripciones");
    } catch (error) {
        renderizarErrorTabla(
            "tabla-suscripciones",
            7,
            error.message
        );
        notificar(error.message);
    }
}

function renderizarSuscripciones(suscripciones) {
    const cuerpo = elemento("tabla-suscripciones");

    if (!cuerpo) {
        return;
    }

    limpiar(cuerpo);

    if (!suscripciones.length) {
        agregarFilaVacia(
            cuerpo,
            7,
            "No existen suscripciones registradas."
        );
        return;
    }

    suscripciones.forEach((suscripcion) => {
        const fila = crearElemento("tr");

        fila.appendChild(
            crearElemento("td", suscripcion.id ?? "—")
        );

        fila.appendChild(
            crearElemento("td", suscripcion.empresa_id ?? "—")
        );

        fila.appendChild(
            crearElemento("td", suscripcion.plan_id ?? "—")
        );

        const celdaEstado = crearElemento("td");
        celdaEstado.appendChild(
            crearInsignia(suscripcion.estado)
        );
        fila.appendChild(celdaEstado);

        fila.appendChild(
            crearElemento("td", suscripcion.ciclo || "—")
        );

        fila.appendChild(
            crearElemento(
                "td",
                formatearFecha(suscripcion.fecha_inicio)
            )
        );

        fila.appendChild(
            crearElemento(
                "td",
                formatearFecha(suscripcion.fecha_fin)
            )
        );

        cuerpo.appendChild(fila);
    });
}

function mostrarCargaTabla(id, columnas, mensaje) {
    const cuerpo = elemento(id);

    if (!cuerpo) {
        return;
    }

    limpiar(cuerpo);

    const fila = crearElemento("tr");
    const celda = crearElemento(
        "td",
        mensaje,
        "estado-carga"
    );

    celda.colSpan = columnas;
    fila.appendChild(celda);
    cuerpo.appendChild(fila);
}

function agregarFilaVacia(cuerpo, columnas, mensaje) {
    const fila = crearElemento("tr");
    const celda = crearElemento(
        "td",
        mensaje,
        "tabla__vacio"
    );

    celda.colSpan = columnas;
    fila.appendChild(celda);
    cuerpo.appendChild(fila);
}

async function cargarPagos(forzar = false) {
    if (estado.cargadas.has("pagos") && !forzar) {
        return;
    }

    mostrarCargaTabla(
        "tabla-pagos",
        6,
        "Cargando pagos…"
    );

    try {
        const datos = await solicitarJson(API.pagos);
        renderizarPagos(datos.pagos || []);
        estado.cargadas.add("pagos");
    } catch (error) {
        renderizarErrorTabla(
            "tabla-pagos",
            6,
            error.message
        );
        notificar(error.message);
    }
}

function renderizarPagos(pagos) {
    const cuerpo = elemento("tabla-pagos");

    if (!cuerpo) {
        return;
    }

    limpiar(cuerpo);

    if (!pagos.length) {
        agregarFilaVacia(
            cuerpo,
            6,
            "No existen pagos registrados."
        );
        return;
    }

    pagos.forEach((pago) => {
        const fila = crearElemento("tr");

        fila.appendChild(
            crearElemento("td", pago.id ?? "—")
        );

        fila.appendChild(
            crearElemento("td", pago.empresa_id ?? "—")
        );

        fila.appendChild(
            crearElemento("td", pago.proveedor || "—")
        );

        fila.appendChild(
            crearElemento(
                "td",
                pago.referencia_externa || "—"
            )
        );

        const celdaEstado = crearElemento("td");
        celdaEstado.appendChild(
            crearInsignia(pago.estado)
        );
        fila.appendChild(celdaEstado);

        fila.appendChild(
            crearElemento(
                "td",
                formatearDinero(
                    pago.monto,
                    pago.moneda || "CLP"
                )
            )
        );

        cuerpo.appendChild(fila);
    });
}

async function cargarAuditoria(forzar = false) {
    if (estado.cargadas.has("auditoria") && !forzar) {
        return;
    }

    mostrarCargaTabla(
        "tabla-auditoria",
        6,
        "Cargando auditoría…"
    );

    try {
        const datos = await solicitarJson(
            `${API.auditoria}?limite=200`
        );

        renderizarAuditoria(datos.auditoria || []);
        estado.cargadas.add("auditoria");
    } catch (error) {
        renderizarErrorTabla(
            "tabla-auditoria",
            6,
            error.message
        );
        notificar(error.message);
    }
}

function renderizarAuditoria(registros) {
    const cuerpo = elemento("tabla-auditoria");

    if (!cuerpo) {
        return;
    }

    limpiar(cuerpo);

    if (!registros.length) {
        agregarFilaVacia(
            cuerpo,
            6,
            "No existen eventos de auditoría registrados."
        );
        return;
    }

    registros.forEach((registro) => {
        const fila = crearElemento("tr");

        fila.appendChild(
            crearElemento(
                "td",
                formatearFecha(registro.fecha)
            )
        );

        fila.appendChild(
            crearElemento(
                "td",
                registro.accion || "—"
            )
        );

        fila.appendChild(
            crearElemento(
                "td",
                registro.modulo || "—"
            )
        );

        fila.appendChild(
            crearElemento(
                "td",
                registro.empresa_id ?? "Global"
            )
        );

        fila.appendChild(
            crearElemento(
                "td",
                registro.usuario_id ?? "Sistema"
            )
        );

        const entidad = registro.entidad_tipo
            ? `${registro.entidad_tipo} #${registro.entidad_id ?? "—"}`
            : "—";

        fila.appendChild(
            crearElemento("td", entidad)
        );

        cuerpo.appendChild(fila);
    });
}

function cargarSeccion(nombre, forzar = false) {
 const cargadores = {
    resumen: cargarResumen,
    empresas: cargarEmpresas,
    planes: cargarPlanes,
    suscripciones: cargarSuscripciones,
    pagos: cargarPagos,
    auditoria: cargarAuditoria,
};

    const cargador = cargadores[nombre];

    if (cargador) {
        cargador(forzar);
    }
}

function registrarEventos() {
    document.querySelectorAll("[data-seccion]").forEach((boton) => {
        boton.addEventListener("click", () => {
            mostrarSeccion(boton.dataset.seccion);
        });
    });

    document.querySelectorAll("[data-actualizar]").forEach((boton) => {
        boton.addEventListener("click", () => {
            cargarSeccion(boton.dataset.actualizar, true);
        });
    });

    elemento("buscar-empresas")?.addEventListener("click", () => {
    estado.cargadas.delete("empresas");
    cargarEmpresas(true);
});

elemento("filtro-empresa-buscar")?.addEventListener(
    "keydown",
    (evento) => {
        if (evento.key === "Enter") {
            evento.preventDefault();
            estado.cargadas.delete("empresas");
            cargarEmpresas(true);
        }
    }
);

elemento("filtro-empresa-estado")?.addEventListener(
    "change",
    () => {
        estado.cargadas.delete("empresas");
        cargarEmpresas(true);
    }
);

    elemento("abrir-menu")?.addEventListener("click", abrirMenu);
    elemento("cerrar-menu")?.addEventListener("click", cerrarMenu);

    window.addEventListener("keydown", (evento) => {
        if (evento.key === "Escape") {
            cerrarMenu();
        }
    });
}

document.addEventListener("DOMContentLoaded", () => {
    registrarEventos();
    mostrarSeccion("resumen");
});