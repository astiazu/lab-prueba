"""DuckDuckGo HTML mediante urllib, sin dependencias externas.

consultar devuelve (resultados, cursor) o añade un diagnóstico si se solicita.
Los fallos devuelven resultados vacíos y un aviso; nunca resultados simulados.
"""
import logging
from html.parser import HTMLParser
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen

ENDPOINT = 'https://html.duckduckgo.com/html/'
TIMEOUT = 10
MAX_BYTES = 2 * 1024 * 1024
CAMPOS_CURSOR = frozenset(('q', 's', 'dc', 'v', 'o', 'api', 'vqd', 'nextParams', 'kl', 'df', 'b'))
LOG = logging.getLogger(__name__)


class DDGRespuestaInvalida(ValueError):
    def __init__(self, estado, diagnostico):
        super().__init__(estado)
        self.estado = estado
        self.diagnostico = diagnostico


def _url_resultado(href):
    url = urljoin(ENDPOINT, href)
    partes = urlsplit(url)
    if partes.hostname in ('duckduckgo.com', 'www.duckduckgo.com', 'html.duckduckgo.com'):
        destino = parse_qs(partes.query).get('uddg', [None])[0]
        if not destino:
            return None
        url = destino
        partes = urlsplit(url)
    if partes.scheme not in ('http', 'https') or not partes.hostname or partes.username or partes.password:
        return None
    return urlunsplit((partes.scheme, partes.netloc, partes.path, partes.query, ''))


class _ResultadosHTML(HTMLParser):
    """Extraer enlaces orgánicos y el formulario Next, conservando texto anidado."""
    VACIOS = frozenset(('area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'))

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.pila = []
        self.resultados = []
        self.actual = None
        self.nivel_resultado = None
        self.campo = None
        self.nivel_campo = None
        self.formulario = None
        self.siguiente = None
        self.sin_resultados = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        clases = attrs.get('class', '').split()
        if tag not in self.VACIOS:
            self.pila.append(tag)
        nivel = len(self.pila)
        if 'no-results' in clases or 'result--no-result' in clases:
            self.sin_resultados = True
        if 'result' in clases and tag == 'div':
            self._guardar()
            self.actual = {'url': None, 'title': '', 'description': ''}
            self.nivel_resultado = nivel
        if self.actual is not None:
            if tag == 'a' and 'result__a' in clases:
                self.actual['url'] = _url_resultado(attrs.get('href', ''))
                self.campo, self.nivel_campo = 'title', nivel
            elif 'result__snippet' in clases:
                self.campo, self.nivel_campo = 'description', nivel
        if tag == 'form':
            self.formulario = {'campos': {}, 'next': False}
        if self.formulario is not None and tag == 'input':
            nombre, valor = attrs.get('name'), attrs.get('value', '')
            if nombre in CAMPOS_CURSOR:
                self.formulario['campos'][nombre] = valor
            if attrs.get('type') == 'submit' and valor.strip().lower() == 'next':
                self.formulario['next'] = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VACIOS:
            self.handle_endtag(tag)

    def handle_data(self, data):
        if self.actual is not None and self.campo:
            self.actual[self.campo] += data

    def handle_endtag(self, tag):
        if tag == 'form' and self.formulario is not None:
            if self.formulario['next'] and 's' in self.formulario['campos']:
                self.siguiente = self.formulario['campos']
            self.formulario = None
        if tag not in self.pila:
            return
        indice = len(self.pila) - 1 - self.pila[::-1].index(tag)
        del self.pila[indice:]
        if self.nivel_campo is not None and len(self.pila) < self.nivel_campo:
            self.campo = self.nivel_campo = None
        if self.nivel_resultado is not None and len(self.pila) < self.nivel_resultado:
            self._guardar()

    def _guardar(self):
        if self.actual and self.actual['url'] and self.actual['title'].strip():
            self.actual['title'] = ' '.join(self.actual['title'].split())
            self.actual['description'] = ' '.join(self.actual['description'].split())
            if not any(r['url'] == self.actual['url'] for r in self.resultados):
                self.resultados.append(self.actual)
        self.actual = None
        self.nivel_resultado = self.nivel_campo = self.campo = None

    def close(self):
        super().close()
        self._guardar()


def consultar(consulta, cursor=None, con_diagnostico=False):
    resultados, siguiente = [], None
    diagnostico = {'modo': 'DUCKDUCKGO_HTML_REAL', 'estado': 'OK', 'solicitudes_http': 0}
    try:
        if not isinstance(consulta, str) or not consulta.strip():
            raise ValueError('La consulta debe ser texto no vacío')
        if cursor is not None and (not isinstance(cursor, dict) or
                                   any(k not in CAMPOS_CURSOR or not isinstance(v, str) for k, v in cursor.items())):
            raise ValueError('Cursor de DuckDuckGo inválido')
        campos = {**(cursor or {}), 'q': consulta}
        headers = {'User-Agent': 'Mozilla/5.0 (compatible; EMM-Laboratorio/1.0)',
                   'Accept': 'text/html', 'Accept-Encoding': 'identity'}
        if cursor is None:
            solicitud = Request(ENDPOINT + '?' + urlencode(campos), headers=headers)
        else:
            solicitud = Request(ENDPOINT, data=urlencode(campos).encode('utf-8'), headers=headers)
        diagnostico['solicitudes_http'] = 1
        with urlopen(solicitud, timeout=TIMEOUT) as respuesta:
            diagnostico['http_status'] = respuesta.status
            cuerpo = respuesta.read(MAX_BYTES + 1)
            if len(cuerpo) > MAX_BYTES:
                raise ValueError('Respuesta HTML demasiado grande')
            html = cuerpo.decode(respuesta.headers.get_content_charset() or 'utf-8', errors='replace')
        if diagnostico['http_status'] in (202, 429) or any(m in html.lower() for m in ('anomaly.js', 'challenge-form', 'anomaly-modal')):
            diagnostico.update(estado='LIMITADO', aviso='DuckDuckGo solicitó una verificación o limitó la búsqueda; no se reintentó.')
        else:
            parser = _ResultadosHTML()
            parser.feed(html)
            parser.close()
            resultados, siguiente = parser.resultados, parser.siguiente
            if not resultados and not parser.sin_resultados:
                diagnostico.update(estado='ERROR_EXTRACCION', aviso='DuckDuckGo devolvió HTML sin resultados reconocibles.')
                siguiente = None
            elif not resultados:
                diagnostico['estado'] = 'SIN_RESULTADOS'
    except HTTPError as exc:
        diagnostico.update(estado='LIMITADO' if exc.code in (202, 403, 429) else 'ERROR_HTTP',
                           http_status=exc.code, aviso=f'DuckDuckGo devolvió HTTP {exc.code}.')
        exc.close()
    except (URLError, OSError, TimeoutError, HTTPException) as exc:
        diagnostico.update(estado='ERROR_HTTP', aviso=f'No se pudo conectar con DuckDuckGo ({type(exc).__name__}).')
    except (ValueError, LookupError):
        diagnostico.update(estado='ERROR_EXTRACCION', aviso='Consulta, cursor o respuesta HTML de DuckDuckGo inválidos.')
    if diagnostico.get('aviso'):
        LOG.warning('%s', diagnostico['aviso'])
        resultados, siguiente = [], None
    if con_diagnostico:
        return resultados, siguiente, diagnostico
    return resultados, siguiente
