"use strict";

const NOMBRE_CABECERA_CSRF = "X-CSRFToken";

const IDENTIFICADORES_ALTERNADORES = Object.freeze([
    "alternar-password",
    "alternar-confirmacion",
]);

function alternarVisibilidad(boton) {
    const objetivoId = boton.dataset.alternarPassword;
    const campo = document.getElementById(objetivoId);

    if (!campo) {
        return;
    }

    const mostrar = campo.type === "password";

    campo.type = mostrar ? "text" : "password";
    boton.textContent = mostrar ? "Ocultar" : "Mostrar";
    boton.setAttribute(
        "aria-pressed",
        mostrar ? "true" : "false",
    );
    boton.setAttribute(
        "aria-label",
        mostrar
            ? "Ocultar contrase?a"
            : "Mostrar contrase?a",
    );
}

function configurarAlternadores() {
    for (
        const identificador
        of IDENTIFICADORES_ALTERNADORES
    ) {
        const boton = document.getElementById(
            identificador,
        );

        if (!boton) {
            continue;
        }

        boton.addEventListener(
            "click",
            () => alternarVisibilidad(boton),
        );
    }
}

function configurarEnvio() {
    for (
        const formulario of document.querySelectorAll(
            ".formulario-autenticacion",
        )
    ) {
        formulario.addEventListener(
            "submit",
            () => {
                const boton = formulario.querySelector(
                    "[type='submit']",
                );

                if (boton) {
                    boton.disabled = true;
                    boton.setAttribute(
                        "aria-busy",
                        "true",
                    );
                }
            },
        );
    }
}

function tokenCsrf() {
    return document.querySelector(
        "meta[name='csrf-token']",
    )?.content || "";
}

window.NexuStockAutenticacion = Object.freeze({
    nombreCabeceraCsrf: NOMBRE_CABECERA_CSRF,
    tokenCsrf,
});

document.addEventListener(
    "DOMContentLoaded",
    () => {
        configurarAlternadores();
        configurarEnvio();
    },
);
