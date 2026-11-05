"""Recuperación HTTP y extracción estructural del body, sin reglas de dominio."""
import re
from html.parser import HTMLParser
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


class _BodyHTML(HTMLParser):
    VACIOS = frozenset(('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'))
    OMITIR = frozenset(('script', 'style', 'noscript', 'template', 'nav', 'header', 'footer', 'aside', 'form', 'svg'))
    BLOQUES = frozenset(('p', 'div', 'section', 'article', 'main', 'li', 'ul', 'ol', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'br', 'table', 'tr', 'td', 'blockquote'))

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pila = []
        self.textos = {'body': [], 'main': [], 'article': []}

    def _agregar(self, texto):
        etiquetas = [tag for tag, _ in self.pila]
        if 'body' not in etiquetas or any(oculto for _, oculto in self.pila):
            return
        self.textos['body'].append(texto)
        for region in ('main', 'article'):
            if region in etiquetas:
                self.textos[region].append(texto)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag not in self.VACIOS:
            oculto = tag in self.OMITIR or 'hidden' in attrs or attrs.get('aria-hidden', '').lower() == 'true'
            self.pila.append((tag, oculto))
        if tag in self.BLOQUES:
            self._agregar(' ')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VACIOS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in self.BLOQUES:
            self._agregar(' ')
        for i in range(len(self.pila) - 1, -1, -1):
            if self.pila[i][0] == tag:
                del self.pila[i:]
                break

    def handle_data(self, data):
        self._agregar(data)


def extraer_cuerpo(html):
    parser = _BodyHTML()
    parser.feed(html)
    parser.close()
    # Prioridad estructural; nunca se interpreta el tema o vocabulario del texto.
    for region in ('main', 'article', 'body'):
        texto = ' '.join(''.join(parser.textos[region]).split())
        if texto:
            return texto[:MAX_CARACTERES]
    return ''


def enriquecer(candidatos, *, obtener_html=None, max_solicitudes=8):
    obtener = obtener_html or descargar_html
    publicaciones, intentadas, recuperadas = [], 0, 0
    for original in candidatos:
        doc = dict(original)
        doc['cuerpo_extraido'] = ''
        doc['recuperacion'] = {'estado': 'PENDIENTE', 'error': None}
        if intentadas < max_solicitudes:
            intentadas += 1
            try:
                doc['cuerpo_extraido'] = extraer_cuerpo(obtener(doc.get('url')))
                doc['recuperacion']['estado'] = 'RECUPERADO' if doc['cuerpo_extraido'] else 'SIN_TEXTO'
                recuperadas += bool(doc['cuerpo_extraido'])
            except ErrorRecuperacion as exc:
                doc['recuperacion'] = {'estado': 'ERROR', 'error': {'codigo': exc.codigo, 'mensaje': str(exc)}}
        publicaciones.append(doc)
    return {'publicaciones': publicaciones, 'solicitudes_intentadas': intentadas,
            'documentos_con_texto': recuperadas,
            'pendientes': sum(p['recuperacion']['estado'] == 'PENDIENTE' for p in publicaciones)}
