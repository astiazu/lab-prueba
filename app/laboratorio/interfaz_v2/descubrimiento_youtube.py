"""Lectura de videos ya descubiertos mediante YouTube Data API v3."""
import json
import os
import re
from datetime import datetime, timezone
from http.client import HTTPException
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener

from app.laboratorio.configuracion import cargar_entorno
from app.laboratorio.interfaz_v2.descubrimiento_brave import _SinRedireccion

VIDEO_ID = re.compile(r'[A-Za-z0-9_-]{11}')
ENDPOINT = 'https://www.googleapis.com/youtube/v3/videos'
MAX_BYTES = 4 * 1024 * 1024
_abrir_url = build_opener(_SinRedireccion()).open


class YouTubeError(RuntimeError):
    def __init__(self, codigo, mensaje):
        super().__init__(mensaje)
        self.codigo = codigo


def clave_youtube():
    if not (os.environ.get('YOUTUBE_API_KEY') or '').strip():
        cargar_entorno()
    return (os.environ.get('YOUTUBE_API_KEY') or '').strip()


def identificar_video(url):
    try:
        partes = urlsplit(url)
        host = (partes.hostname or '').lower().rstrip('.')
        if host == 'youtu.be':
            vid = partes.path.strip('/').split('/')[0]
        elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtube-nocookie.com', 'www.youtube-nocookie.com'):
            if partes.path == '/watch':
                vid = parse_qs(partes.query).get('v', [''])[0]
            elif partes.path.startswith(('/shorts/', '/embed/', '/live/')):
                vid = partes.path.split('/')[2]
            else:
                return None
        else:
            return None
        return vid if VIDEO_ID.fullmatch(vid) else None
    except (TypeError, ValueError, IndexError):
        return None



def _conteo(valor):
    if isinstance(valor, bool) or not isinstance(valor, (str, int)):
        return None
    try:
        numero = int(valor)
        return numero if numero >= 0 else None
    except (ValueError, TypeError):
        return None


def detalles(ids, clave=None):
    """Un lote de hasta 50 IDs. No descubre videos ni fabrica métricas ausentes."""
    ids = list(dict.fromkeys(ids))
    if not ids:
        return {}
    if len(ids) > 50 or any(not isinstance(v, str) or not VIDEO_ID.fullmatch(v) for v in ids):
        raise ValueError('YouTube requiere entre 1 y 50 identificadores válidos')
    clave = clave if clave is not None else clave_youtube()
    if not clave:
        raise YouTubeError('youtube_no_configurado', 'Falta YOUTUBE_API_KEY en el entorno o en .env.')
    # El parámetro key es el mecanismo documentado de YouTube; nunca registrar esta URL.
    parametros = {'part': 'snippet,statistics', 'id': ','.join(ids), 'key': clave}
    solicitud = Request(ENDPOINT + '?' + urlencode(parametros), headers={'Accept': 'application/json', 'Accept-Encoding': 'identity'})
    try:
        with _abrir_url(solicitud, timeout=15) as respuesta:
            cuerpo = respuesta.read(MAX_BYTES + 1)
        if len(cuerpo) > MAX_BYTES:
            raise ValueError
        data = json.loads(cuerpo)
        if not isinstance(data, dict) or not isinstance(data.get('items'), list) or data.get('error'):
            raise ValueError
        salida = {}
        ahora = datetime.now(timezone.utc).isoformat()
        for item in data['items']:
            if not isinstance(item, dict) or item.get('id') not in ids:
                continue
            estadisticas, snippet = item.get('statistics') or {}, item.get('snippet') or {}
            if not isinstance(estadisticas, dict) or not isinstance(snippet, dict):
                raise ValueError
            vid = item['id']
            salida[vid] = {
                'metricas': {'vistas': _conteo(estadisticas.get('viewCount')),
                             'likes': _conteo(estadisticas.get('likeCount')),
                             'comentarios': _conteo(estadisticas.get('commentCount')),
                             'fecha_publicacion': snippet.get('publishedAt'),
                             'recuperado_en': ahora, 'proveedor': 'YOUTUBE_DATA_API_V3', 'video_id': vid},
                'titulo': snippet.get('title'), 'descripcion': snippet.get('description'),
                'canal': snippet.get('channelTitle'), 'canal_id': snippet.get('channelId'),
            }
        return salida
    except HTTPError as exc:
        estado = exc.code
        exc.close()
        raise YouTubeError('youtube_error_http', f'YouTube API devolvió HTTP {estado}; revisa acceso, clave o cuota.') from None
    except (URLError, OSError, HTTPException):
        raise YouTubeError('youtube_error_red', 'No se pudo conectar con YouTube API.') from None
    except (ValueError, UnicodeError):
        raise YouTubeError('youtube_respuesta_invalida', 'YouTube API devolvió una respuesta inválida.') from None


def enriquecer_publicaciones(publicaciones, consultar_detalles=None):
    from app.laboratorio.motor_v2.fuentes import fuente_especifica
    docs, por_id, errores = [], {}, []
    for original in publicaciones:
        doc = dict(original)
        doc['fuente_especifica'] = fuente_especifica(doc.get('url'))
        doc['metodo_recuperacion'] = 'SNIPPET_BRAVE'
        doc['metricas'] = None
        doc['error_metricas'] = None
        doc.pop('metadatos_youtube', None)
        docs.append(doc)
        if doc['fuente_especifica'] == 'YOUTUBE':
            vid = identificar_video(doc.get('url'))
            if vid:
                por_id.setdefault(vid, []).append(doc)
            else:
                doc['error_metricas'] = {'codigo': 'youtube_sin_video_id', 'mensaje': 'La URL no identifica un video de YouTube.'}
    intentadas = exitosas = 0
    if por_id:
        clave = clave_youtube() if consultar_detalles is None else None
        consultar = consultar_detalles or detalles
        ids = list(por_id)
        for inicio in range(0, len(ids), 50):
            lote = ids[inicio:inicio + 50]
            try:
                if consultar_detalles is None and not clave:
                    raise YouTubeError('youtube_no_configurado', 'Falta YOUTUBE_API_KEY en el entorno o en .env.')
                intentadas += 1
                datos = consultar(lote, clave)
                exitosas += 1
            except YouTubeError as exc:
                error = {'codigo': exc.codigo, 'mensaje': str(exc)}
                errores.append({'proveedor': 'YOUTUBE_DATA_API_V3', 'codigo': exc.codigo, 'error': str(exc)})
                for vid in ids[inicio:]:
                    for doc in por_id[vid]:
                        doc['error_metricas'] = dict(error)
                break
            for vid in lote:
                for doc in por_id[vid]:
                    if vid in datos:
                        info = datos[vid]
                        doc['metricas'] = dict(info['metricas'])
                        doc['metadatos_youtube'] = {k: v for k, v in info.items() if k != 'metricas'}
                        doc['fecha_publicacion'] = doc['metricas'].get('fecha_publicacion')
                        doc['metodo_recuperacion'] = 'API_OFICIAL'
                    else:
                        doc['error_metricas'] = {'codigo': 'youtube_video_no_disponible', 'mensaje': 'YouTube API no devolvió este video; no se presumen métricas.'}
    return {'publicaciones': docs, 'solicitudes_intentadas': intentadas,
            'solicitudes_exitosas': exitosas, 'errores': errores}
