"""Stub Brave: respuestas locales; no usa claves ni Internet."""
from urllib.parse import urlsplit, urlunsplit
from .stubs import resultados_web


def clave_brave():
    return 'STUB_LOCAL'


def _normalizar_url(url):
    if not isinstance(url, str):
        return None
    try:
        partes = urlsplit(url)
        if partes.scheme not in ('http', 'https') or not partes.hostname:
            return None
        return urlunsplit((partes.scheme.lower(), partes.netloc.lower(), partes.path or '/', partes.query, ''))
    except ValueError:
        return None


def _brave(consulta, desde, hasta, clave):
    return {'web': {'results': resultados_web(consulta, desde)}}
