"""Stub YouTube compatible con search/videos, sin claves ni red."""
import re
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import parse_qs, urlsplit

VIDEO_ID = re.compile(r'[A-Za-z0-9_-]{11}')


def clave_youtube():
    return 'STUB_LOCAL'


def identificar_video(url):
    try:
        partes = urlsplit(url)
        host = (partes.hostname or '').lower()
        if host == 'youtu.be':
            vid = partes.path.strip('/').split('/')[0]
        elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
            if partes.path == '/watch':
                vid = parse_qs(partes.query).get('v', [''])[0]
            elif partes.path.startswith(('/shorts/', '/embed/')):
                vid = partes.path.split('/')[2]
            else:
                return None
        else:
            return None
        return vid if VIDEO_ID.fullmatch(vid) else None
    except (TypeError, ValueError, IndexError):
        return None


def planificar(marco):
    return [('entidad', f'"{entidad}"') for entidad in marco.entidades]


def buscar(consulta, desde, hasta, clave, *, page_token=None):
    vid = sha256(consulta.encode()).hexdigest()[:11]
    return {'items': [{'id': {'videoId': vid}, 'snippet': {
        'title': f'[SIMULADO] Video: {consulta}',
        'description': 'Video ficticio generado localmente; no existe evidencia real.',
    }}]}


def detalles(ids, clave):
    return {vid: {'titulo': '[SIMULADO] Video local', 'descripcion': 'Metadatos ficticios.',
                  'canal': 'Canal ficticio', 'canal_id': 'STUB_LOCAL',
                  'publicado_en': None, 'duracion_iso8601': 'PT1M',
                  'visualizaciones': None, 'me_gusta': None, 'comentarios_informados': None,
                  'recuperado_en': datetime.now(timezone.utc).isoformat()}
            for vid in ids}
