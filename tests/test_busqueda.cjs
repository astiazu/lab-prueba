// DOM mínimo para comprobar la integración del observador y el envío sin dependencias.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
class Elemento {
    constructor() { this.textContent = ''; this.value = ''; this.children = []; this.events = {}; }
    append(e) { this.children.push(e); }
    after(e) { this.siguiente = e; }
    setAttribute() {}
    replaceChildren() { this.children = []; }
    addEventListener(tipo, fn) { this.events[tipo] = fn; }
    querySelector() { return acciones; }
}
const acciones = new Elemento();
const elementos = Object.fromEntries(['form', 'marco', 'desde', 'hasta', 'estado-consulta', 'territorios-genericos'].map(id => [id, new Elemento()]));
let observador;
let peticion;
const respuesta = {
    total_urls_unicas: 1, solicitudes_exitosas: 0, origenes: { 'example.com': 1 }, simulado: true,
    publicaciones: [{ score_emm: 0.6, titulo: '[SIMULADO] Prueba', origen: 'Demo local', fecha_indice: '2025-01-01', descripcion: '<script>texto</script>', url: 'https://example.com/demo' }],
    errores: [], avisos: [], advertencia: 'MODO DEMO', periodo: { desde: '2025-01-01', hasta: '2025-12-31' },
};
vm.runInNewContext(fs.readFileSync('front/busqueda.js', 'utf8'), {
    document: { getElementById: id => elementos[id], createElement: () => new Elemento() },
    MutationObserver: class {
        constructor(fn) { observador = fn; }
        observe(target, opciones) { assert.equal(target, elementos['estado-consulta']); assert.equal(opciones.subtree, true); }
    },
    URL,
    fetch: async (url, opciones) => { peticion = { url, opciones }; return { ok: true, json: async () => respuesta }; },
});
(async () => {
    const boton = acciones.children[0];
    assert.equal(boton.disabled, true);
    elementos['estado-consulta'].textContent = 'Consulta validada: a;b;c';
    observador();
    assert.equal(boton.disabled, false);
    elementos.marco.value = 'a;b;c';
    elementos.desde.value = '2025-01-01';
    elementos.hasta.value = '2025-12-31';
    await elementos.form.events.submit({ preventDefault() {} });
    assert.equal(peticion.url, '/api/buscar');
    assert.deepEqual(JSON.parse(peticion.opciones.body), { marco: 'a;b;c', periodo: respuesta.periodo });
    const panel = elementos.form.siguiente;
    assert.equal(panel.children[0].textContent, 'Resultados de descubrimiento');
    assert.equal(panel.children.filter(e => e.className === 'pub').at(-1).children[2].textContent, '<script>texto</script>');
    assert.equal(panel.children[4].textContent, 'Orígenes: example.com: 1');
    assert.ok(panel.children.filter(e => e.className === 'pub').at(-1).children[3].textContent.startsWith('URL ficticia'));
    respuesta.publicaciones[0].simulado = false;
    await elementos.form.events.submit({ preventDefault() {} });
    assert.equal(panel.children.filter(e => e.className === 'pub').at(-1).children[3].textContent, 'Ver publicación');
    assert.equal(panel.children.filter(e => e.className === 'pub').at(-1).children[3].href, 'https://example.com/demo');
    respuesta.publicaciones[0].evaluacion_contextual = { score_emm: 0.6, justificacion: 'Encontrado: entidad y contexto. Falta: territorio.' };
    respuesta.publicaciones[0].recuperacion = { estado: 'RECUPERADO' };
    respuesta.publicaciones[0].cuerpo_extraido = '<script>contenido como texto</script>';
    await elementos.form.events.submit({ preventDefault() {} });
    assert.equal(panel.children.filter(e => e.className === 'pub').at(-1).children[4].textContent, 'Score EMM: 0.6');
    assert.equal(panel.children.filter(e => e.className === 'pub').at(-1).children.at(-1).children[1].textContent, '<script>contenido como texto</script>');
    respuesta.publicaciones.push({ score_emm: 0.4 }, { score_emm: 0 }, { score_emm: 0.49 });
    await elementos.form.events.submit({ preventDefault() {} });
    assert.equal(panel.children.filter(e => e.className === 'pub').length, 1);
    assert.equal(panel.children.at(-1).textContent, '[3] publicaciones descartadas por no cumplir el Marco EMM.');
    respuesta.publicaciones[0].score_emm = 0.5;
    await elementos.form.events.submit({ preventDefault() {} });
    assert.equal(panel.children.filter(e => e.className === 'pub').length, 1);
    respuesta.publicaciones[0].score_emm = 0.4;
    await elementos.form.events.submit({ preventDefault() {} });
    assert.equal(panel.children.filter(e => e.className === 'pub').length, 0);
    assert.equal(panel.children.at(-1).textContent, '[4] publicaciones descartadas por no cumplir el Marco EMM.');
    assert.equal(respuesta.publicaciones.length, 4);
    respuesta.publicaciones = [{ ...respuesta.publicaciones[0], score_emm: 0.6 }];
    respuesta.total_publicaciones_descartadas = 7;
    await elementos.form.events.submit({ preventDefault() {} });
    assert.equal(panel.children.filter(e => e.className === 'pub').length, 1);
    assert.equal(panel.children.at(-1).textContent, '[7] publicaciones descartadas por no cumplir el Marco EMM.');
    respuesta.publicaciones = [
        { ...respuesta.publicaciones[0], titulo: 'Media', score_emm: 0.8 },
        { ...respuesta.publicaciones[0], titulo: 'Alta', score_emm: 1.0 },
        { ...respuesta.publicaciones[0], titulo: 'Baja', score_emm: 0.4 },
    ];
    elementos['territorios-genericos'].value = 'c';
    await elementos.form.events.submit({ preventDefault() {} });
    assert.deepEqual(panel.children.filter(e => e.className === 'pub').map(e => e.children[0].textContent), ['Alta', 'Media']);
    assert.equal(respuesta.publicaciones[0].titulo, 'Media');
    assert.equal(panel.children.at(-1).textContent, '[8] publicaciones descartadas por no cumplir el Marco EMM.');
    assert.deepEqual(JSON.parse(peticion.opciones.body).territorios_genericos, ['c']);
    elementos['territorios-genericos'].events.input();
    assert.equal(boton.disabled, true);
    elementos.marco.events.input();
    assert.equal(boton.disabled, true);
    assert.equal(panel.children.length, 0);
    console.log('OK: observador, habilitación, envío, panel e invalidación al editar.');
})().catch(error => { console.error(error); process.exitCode = 1; });
