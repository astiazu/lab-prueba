"""Recuperación HTTP y extracción estructural del body, sin reglas de dominio."""
import re
from bs4 import BeautifulSoup
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

TIMEOUT = 10
MAX_BYTES = 2 * 1024 * 1024
MAX_CARACTERES = 5000


class ErrorRecuperacion(RuntimeError):
    def __init__(self, codigo, mensaje):
        super().__init__(mensaje)
        self.codigo = codigo


def descargar_html(url):
    try:
        partes = urlsplit(url)
        if partes.scheme not in ('http', 'https') or not partes.hostname or partes.username or partes.password:
            raise ValueError
    except (ValueError, TypeError):
        raise ErrorRecuperacion('url_invalida', 'La publicación no tiene una URL HTTP válida.') from None
    solicitud = Request(url, headers={'User-Agent': 'EMM-Laboratorio/1.0',
                                     'Accept': 'text/html,application/xhtml+xml',
                                     'Accept-Encoding': 'identity'})
    try:
        with urlopen(solicitud, timeout=TIMEOUT) as respuesta:
            if respuesta.headers.get_content_type() not in ('text/html', 'application/xhtml+xml'):
                raise ErrorRecuperacion('tipo_no_soportado', 'El recurso no es HTML.')
            cuerpo = respuesta.read(MAX_BYTES + 1)
            if len(cuerpo) > MAX_BYTES:
                raise ErrorRecuperacion('documento_demasiado_grande', 'El HTML supera el límite de 2 MiB.')
            codificacion = respuesta.headers.get_content_charset()
        if not codificacion:
            declaracion = re.search(br'charset\s*=\s*[\"\x27]?([a-zA-Z0-9_-]+)', cuerpo[:4096], re.I)
            codificacion = declaracion.group(1).decode('ascii') if declaracion else 'utf-8'
        return cuerpo.decode(codificacion, errors='replace')
    except HTTPError as exc:
        estado = exc.code
        exc.close()
        raise ErrorRecuperacion('error_http', f'El documento devolvió HTTP {estado}.') from None
    except (URLError, OSError, HTTPException):
        raise ErrorRecuperacion('error_red', 'No se pudo descargar el documento.') from None
    except LookupError:
        raise ErrorRecuperacion('codificacion_invalida', 'El HTML declara una codificación desconocida.') from None


def extraer_cuerpo(html):
    sopa = BeautifulSoup(html, 'html.parser')
    cuerpo = sopa.body
    if cuerpo is None:
        return ''
    for elemento in reversed(cuerpo.select('script, style, noscript, template, svg, [hidden], [aria-hidden="true"]')):
        elemento.decompose()
    for elemento in reversed(cuerpo.find_all(style=True)):
        if re.search(r'(?:display\s*:\s*none|visibility\s*:\s*hidden)', elemento.get('style', ''), re.I):
            elemento.decompose()
    # Limpiar solo por estructura HTML; no clasificar vocabulario o temas.
    texto = ' '.join(cuerpo.get_text(separator=' ', strip=True).split())
    return texto[:MAX_CARACTERES]


def enriquecer(candidatos, *, obtener_html=None, max_solicitudes=None):
    obtener = obtener_html or descargar_html
    publicaciones, intentadas, recuperadas = [], 0, 0
    for original in candidatos:
        doc = dict(original)
        descripcion = doc.get('descripcion')
        doc['cuerpo_extraido'] = descripcion[:MAX_CARACTERES] if isinstance(descripcion, str) else ''
        doc['recuperacion'] = {'estado': 'PENDIENTE', 'error': None, 'fuente_texto': 'DESCRIPCION_BRAVE' if doc['cuerpo_extraido'] else 'SIN_TEXTO'}
        if doc.get('metodo_recuperacion') == 'API_OFICIAL':
            texto_api = (doc.get('metadatos_youtube') or {}).get('descripcion')
            if isinstance(texto_api, str) and texto_api.strip():
                doc['cuerpo_extraido'] = texto_api[:MAX_CARACTERES]
                doc['recuperacion']['fuente_texto'] = 'YOUTUBE_API'
            doc['recuperacion']['estado'] = 'RECUPERADO'
            recuperadas += bool(doc['cuerpo_extraido'])
            publicaciones.append(doc)
            continue
        doc['metodo_recuperacion'] = 'SNIPPET_BRAVE'
        if max_solicitudes is None or intentadas < max_solicitudes:
            intentadas += 1
            try:
                texto = extraer_cuerpo(obtener(doc.get('url')))
                doc['recuperacion']['estado'] = 'RECUPERADO' if texto else 'SIN_TEXTO'
                if texto:
                    doc['cuerpo_extraido'] = texto
                    doc['recuperacion']['fuente_texto'] = 'HTML_BODY'
                    doc['metodo_recuperacion'] = 'HTML_SCRAPING'
                    recuperadas += 1
            except ErrorRecuperacion as exc:
                doc['recuperacion'].update(estado='ERROR', error={'codigo': exc.codigo, 'mensaje': str(exc)})
        publicaciones.append(doc)
    return {'publicaciones': publicaciones, 'solicitudes_intentadas': intentadas,
            'documentos_con_texto': recuperadas,
            'pendientes': sum(p['recuperacion']['estado'] == 'PENDIENTE' for p in publicaciones)}
