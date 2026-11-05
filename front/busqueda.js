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
        texto(panel, "h2", "Resultados de descubrimiento");
        texto(panel, "p", datos.advertencia);
        texto(panel, "p", `Período: ${datos.periodo.desde} a ${datos.periodo.hasta}`);
        const kpis = document.createElement("div");
        kpis.className = "kpis";
        texto(kpis, "article", `URLs únicas: ${datos.total_urls_unicas}`);
        texto(kpis, "article", `${datos.simulado ? "Operaciones exitosas (modo mixto/prueba)" : "Solicitudes exitosas"}: ${datos.solicitudes_exitosas}`);
        panel.append(kpis);
        const origenes = Array.isArray(datos.origenes)
            ? datos.origenes.join(", ")
            : Object.entries(datos.origenes).map(([origen, cantidad]) => `${origen}: ${cantidad}`).join(", ");
        texto(panel, "p", `Orígenes: ${origenes}`);
        for (const aviso of [...datos.avisos, ...datos.errores]) {
            texto(panel, "p", typeof aviso === "string" ? aviso : `${aviso.proveedor || "Motor"}: ${aviso.error || JSON.stringify(aviso)}`);
        }
        for (const publicacion of datos.publicaciones) {
            const articulo = document.createElement("article");
            articulo.className = "pub";
            texto(articulo, "h3", publicacion.titulo);
            texto(articulo, "p", `${publicacion.origen} · ${publicacion.fecha || publicacion.fecha_indice || publicacion.youtube?.publicado_en || "Fecha no disponible"}`);
            texto(articulo, "p", publicacion.resumen || publicacion.descripcion || "Sin descripción");
            if (publicacion.simulado ?? datos.simulado) {
                texto(articulo, "p", "URL ficticia (sin navegación): " + publicacion.url);
                panel.append(articulo);
                continue;
            }
            const url = new URL(publicacion.url);
            if (["https:", "http:"].includes(url.protocol)) {
                const enlace = texto(articulo, "a", "Ver publicación");
                enlace.href = url.href;
                enlace.target = "_blank";
                enlace.rel = "noopener noreferrer";
            }
            if (publicacion.evaluacion_contextual) {
                const evaluacion = publicacion.evaluacion_contextual;
                texto(articulo, "p", `Score EMM: ${evaluacion.score_emm}`);
                texto(articulo, "p", evaluacion.justificacion);
                texto(articulo, "p", `Recuperación: ${publicacion.recuperacion?.estado || "Sin información"}`);
                const detalle = document.createElement("details");
                texto(detalle, "summary", "Cuerpo extraído");
                texto(detalle, "p", publicacion.cuerpo_extraido || "Sin cuerpo disponible");
                articulo.append(detalle);
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
