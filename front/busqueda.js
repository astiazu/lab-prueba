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
        texto(kpis, "article", `URLs activas: ${datos.total_urls_activas ?? datos.total_urls_unicas}`);
        if (datos.aceptadas_reales != null) {
            texto(kpis, "article", `Reales: ${datos.aceptadas_reales} · Marginales: ${datos.aceptadas_marginales}`);
            texto(kpis, "article", `Archivadas: ${datos.total_urls_archivadas}`);
        }
        texto(kpis, "article", `${datos.simulado ? "Operaciones exitosas (modo mixto/prueba)" : "Solicitudes exitosas"}: ${datos.solicitudes_exitosas}`);
        panel.append(kpis);
        const origenes = Array.isArray(datos.origenes)
            ? datos.origenes.join(", ")
            : Object.entries(datos.origenes).map(([origen, cantidad]) => `${origen}: ${cantidad}`).join(", ");
        texto(panel, "p", `Orígenes: ${origenes}`);
        for (const aviso of [...datos.avisos, ...datos.errores]) {
            texto(panel, "p", typeof aviso === "string" ? aviso : `${aviso.proveedor || "Motor"}: ${aviso.error || JSON.stringify(aviso)}`);
        }
        const umbral = datos.politica_emm?.umbral_aceptacion ?? 0.5;
        let descartadas = datos.total_publicaciones_descartadas ?? datos.publicaciones_descartadas?.length ?? 0;
        const scorePublicacion = p => p.score_emm ?? p.evaluacion_contextual?.score_emm ?? 0;
        const ordenadas = [...datos.publicaciones].sort((a, b) => scorePublicacion(b) - scorePublicacion(a));
        const descartadasDetalle = [...(datos.publicaciones_descartadas || [])];
        for (const publicacion of ordenadas) {
            const score = publicacion.score_emm ?? publicacion.evaluacion_contextual?.score_emm ?? 0;
            if (typeof score !== "number" || !Number.isFinite(score) || score < umbral) {
                descartadas += 1;
                descartadasDetalle.push(publicacion);
                continue;
            }
            const articulo = document.createElement("article");
            articulo.className = "pub";
            texto(articulo, "h3", publicacion.titulo);
            texto(articulo, "p", `${publicacion.origen} · ${publicacion.fecha || publicacion.fecha_indice || publicacion.youtube?.publicado_en || "Fecha no disponible"}`);
            texto(articulo, "p", publicacion.resumen || publicacion.descripcion || "Sin descripción");
            texto(articulo, "p", `Score EMM: ${score}`);
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
                texto(articulo, "p", evaluacion.justificacion);
                texto(articulo, "p", `Recuperación: ${publicacion.recuperacion?.estado || "Sin información"}`);
                const detalle = document.createElement("details");
                texto(detalle, "summary", "Cuerpo extraído");
                texto(detalle, "p", publicacion.cuerpo_extraido || "Sin cuerpo disponible");
                articulo.append(detalle);
            }
            panel.append(articulo);
        }
        if (descartadasDetalle.length) {
            const detalleDescartes = document.createElement("details");
            texto(detalleDescartes, "summary", "Auditar publicaciones descartadas");
            for (const publicacion of descartadasDetalle) {
                const score = scorePublicacion(publicacion);
                const valor = typeof score === "number" && Number.isFinite(score) ? score : "no disponible";
                texto(detalleDescartes, "p", `Score EMM: ${valor} — ${publicacion.titulo || publicacion.url || "Sin título"}`);
                if (publicacion.evaluacion_contextual?.justificacion) {
                    texto(detalleDescartes, "p", publicacion.evaluacion_contextual.justificacion);
                }
            }
            panel.append(detalleDescartes);
        }
        if (datos.total_urls_archivadas != null) texto(panel, "p", `${datos.total_urls_archivadas} publicaciones archivadas fuera del denominador.`);
        texto(panel, "small", `[${descartadas}] publicaciones descartadas por no cumplir el Marco EMM.`);
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
