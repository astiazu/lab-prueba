"""Cliente de la API oficial Brave Search, mediante la librería estándar."""
import json
import os
import threading
import time
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.laboratorio.configuracion import cargar_entorno

ENDPOINT = 'https://api.search.brave.com/res/v1/web/search'
TIMEOUT = 15
MAX_BYTES = 4 * 1024 * 1024
_TURNO = threading.Lock()
_ultimo_inicio = None


def _esperar_turno():
    """Espaciar solicitudes para los planes de Brave con límite de 1/s."""
    global _ultimo_inicio
    with _TURNO:
        ahora = time.monotonic()
        if _ultimo_inicio is not None:
            pausa = max(0, 1.1 - (ahora - _ultimo_inicio))
            if pausa:
                time.sleep(pausa)
        _ultimo_inicio = time.monotonic()


class BraveError(RuntimeError):
    """Error público controlado, sin cuerpos remotos ni credenciales."""
    def __init__(self, codigo, mensaje, http_status=502):
        super().__init__(mensaje)
        self.codigo = codigo
        self.http_status = http_status


class _SinRedireccion(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Evitar reenviar X-Subscription-Token a destinos de redirección.
        return None


_abrir_url = build_opener(_SinRedireccion()).open


def clave_brave():
    if not any((os.environ.get(nombre) or '').strip() for nombre in ('BRAVE_API_KEY', 'BRAVE_SEARCH_API_KEY')):
        # También funciona si se invoca la API sin run.py o se crea .env después
        # de arrancar. No sustituye una clave válida ya definida en el proceso.
        cargar_entorno()
    return ((os.environ.get('BRAVE_API_KEY') or '').strip()
            or (os.environ.get('BRAVE_SEARCH_API_KEY') or '').strip())


def _normalizar_url(url):
    if not isinstance(url, str):
        return None
    try:
        partes = urlsplit(url)
        if partes.scheme not in ('http', 'https') or not partes.hostname or partes.username or partes.password:
            return None
        return urlunsplit((partes.scheme.lower(), partes.netloc.lower(), partes.path or '/', partes.query, ''))
    except ValueError:
        return None


def _brave(consulta, desde, hasta, clave=None, *, offset=0):
    clave = clave if clave is not None else clave_brave()
    if not clave:
        raise BraveError('brave_no_configurado', 'Falta BRAVE_API_KEY o BRAVE_SEARCH_API_KEY en el entorno o en .env.', 503)
    if type(offset) is not int or not 0 <= offset <= 9:
        raise ValueError('offset de Brave fuera de rango (0..9)')
    parametros = {'q': consulta, 'count': 20, 'offset': offset, 'freshness': f'{desde}to{hasta}'}
    solicitud = Request(ENDPOINT + '?' + urlencode(parametros), headers={
        'Accept': 'application/json', 'Accept-Encoding': 'identity',
        'User-Agent': 'EMM-Laboratorio/1.0', 'X-Subscription-Token': clave,
    })
    try:
        _esperar_turno()
        with _abrir_url(solicitud, timeout=TIMEOUT) as respuesta:
            cuerpo = respuesta.read(MAX_BYTES + 1)
        if len(cuerpo) > MAX_BYTES:
            raise BraveError('brave_respuesta_invalida', 'La respuesta de Brave excede el tamaño permitido.')
        datos = json.loads(cuerpo)
        if not isinstance(datos, dict):
            raise ValueError
        web = datos.get('web', {})
        if not isinstance(web, dict) or not isinstance(web.get('results', []), list):
            raise ValueError
        if any(not isinstance(item, dict) for item in web.get('results', [])):
            raise ValueError
        return datos
    except HTTPError as exc:
        estado = exc.code
        exc.close()
        if estado in (401, 403):
            raise BraveError('brave_acceso_denegado', 'Brave rechazó el acceso; revisa la clave, el plan y el acceso de red.') from None
        if estado == 429:
            raise BraveError('brave_limite', 'Brave alcanzó el límite de solicitudes; vuelve a intentar más tarde.', 429) from None
        raise BraveError('brave_error_http', f'Brave devolvió HTTP {estado}.') from None
    except (URLError, OSError, HTTPException):
        raise BraveError('brave_error_red', 'No se pudo conectar con la API de Brave.') from None
    except (ValueError, UnicodeError):
        raise BraveError('brave_respuesta_invalida', 'Brave devolvió una respuesta JSON inválida.') from None
