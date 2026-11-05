"use strict";

(() => {
    const form = document.getElementById("form");
    const marco = document.getElementById("marco");
    const desde = document.getElementById("desde");
    const hasta = document.getElementById("hasta");
    const estado = document.getElementById("estado-consulta");
    const boton = document.createElement("button");
    boton.id = "buscar";
    boton.type = "submit";
    boton.textContent = "Buscar";
    form.querySelector(".actions").append(boton);

    const panel = document.createElement("section");
    panel.className = "panel";
    panel.id = "resultados";
    panel.setAttribute("aria-live", "polite");
    form.after(panel);
    let buscando = false;
    let version = 0;

    function actualizarBoton() {
        boton.disabled = buscando || !estado.textContent.trim().startsWith("Consulta validada:");
    }

    const observador = new MutationObserver(actualizarBoton);
    observador.observe(estado, { childList: true, characterData: true, subtree: true });
    actualizarBoton();

    for (const campo of [marco, desde, hasta]) {
        campo.addEventListener("input", () => {
            version += 1;
            estado.textContent = "Sin validar";
            panel.replaceChildren();
            actualizarBoton();
        });
    }

    function texto(contenedor, etiqueta, contenido) {
        const elemento = document.createElement(etiqueta);
        elemento.textContent = contenido;
        contenedor.append(elemento);
        return elemento;
    }

    function mostrar(datos) {
        panel.replaceChildren();
        texto(panel, "h2", "Resultados de prueba");
        texto(panel, "p", datos.advertencia);
        texto(panel, "p", `Período: ${datos.periodo.desde} a ${datos.periodo.hasta}`);
        const kpis = document.createElement("div");
        kpis.className = "kpis";
        texto(kpis, "article", `URLs únicas: ${datos.total_urls_unicas}`);
        texto(kpis, "article", `Solicitudes externas exitosas: ${datos.solicitudes_exitosas}`);
        panel.append(kpis);
        texto(panel, "p", `Orígenes: ${datos.origenes.join(", ")}`);
        for (const aviso of [...datos.avisos, ...datos.errores]) {
            texto(panel, "p", aviso);
        }
        for (const publicacion of datos.publicaciones) {
            const articulo = document.createElement("article");
            articulo.className = "pub";
            texto(articulo, "h3", publicacion.titulo);
            texto(articulo, "p", `${publicacion.origen} · ${publicacion.fecha}`);
            texto(articulo, "p", publicacion.resumen);
            const url = new URL(publicacion.url);
            if (["https:", "http:"].includes(url.protocol)) {
                const enlace = texto(articulo, "a", "Enlace de ejemplo");
                enlace.href = url.href;
                enlace.target = "_blank";
                enlace.rel = "noopener noreferrer";
            }
            panel.append(articulo);
        }
    }

    form.addEventListener("submit", async (evento) => {
        evento.preventDefault();
        if (boton.disabled) return;
        buscando = true;
        actualizarBoton();
        const versionSolicitud = version;
        panel.replaceChildren();
        texto(panel, "p", "Buscando…");
        try {
            const respuesta = await fetch("/api/buscar", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    marco: marco.value.trim(),
                    periodo: { desde: desde.value, hasta: hasta.value },
                }),
            });
            const datos = await respuesta.json();
            if (!respuesta.ok) throw new Error(datos.error?.mensaje || "No se pudo realizar la búsqueda.");
            if (versionSolicitud === version) mostrar(datos);
        } catch (error) {
            if (versionSolicitud === version) {
                panel.replaceChildren();
                texto(panel, "p", `Error: ${error.message}`);
            }
        } finally {
            buscando = false;
            actualizarBoton();
        }
    });
})();
