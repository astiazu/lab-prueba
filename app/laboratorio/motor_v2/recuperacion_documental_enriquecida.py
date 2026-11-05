"""Enriquecimiento local mínimo; el módulo original no fue adjuntado."""
from html.parser import HTMLParser
from app.laboratorio.interfaz_v2.descubrimiento_youtube import identificar_video


def fuente_url(url):
    return 'YOUTUBE' if identificar_video(url) else 'WEB'


class _TextoHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.textos = []

    def handle_data(self, data):
        if data.strip():
            self.textos.append(data.strip())


def enriquecer(candidatos, *, obtener_html, adaptadores_nativos, max_solicitudes,
               al_guardar, fichas_previas):
    documentos, intentadas = [], 0
    for doc in candidatos:
        url = doc['url']
        previa = fichas_previas.get(url)
        if previa and previa.get('estado_recuperacion') == 'RECUPERADO':
            documentos.append(previa)
            continue
        contenido = {}
        estado = 'PENDIENTE'
        errores = []
        try:
            fuente = fuente_url(url)
            if fuente in adaptadores_nativos:
                contenido = adaptadores_nativos[fuente](doc)
                estado = 'RECUPERADO'
            elif intentadas < max_solicitudes:
                intentadas += 1
                parser = _TextoHTML()
                parser.feed(obtener_html(url))
                contenido = {'titulo': doc.get('titulo'), 'descripcion': doc.get('descripcion'),
                             'cuerpo': ' '.join(parser.textos)}
                estado = 'RECUPERADO'
        except Exception as exc:
            estado = 'ERROR'
            errores.append(f'{type(exc).__name__}: {exc}')
        ficha = {'id': doc.get('id'), 'url_solicitada': url, 'estado_recuperacion': estado,
                 'contenido': contenido, 'errores': errores, 'modo': 'STUB_LOCAL'}
        al_guardar(ficha)
        documentos.append(ficha)
    return {'documentos': documentos, 'solicitudes_intentadas': intentadas,
            'modo': 'STUB_LOCAL', 'solicitudes_http_reales': 0}
