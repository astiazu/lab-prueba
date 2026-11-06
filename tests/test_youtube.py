from io import BytesIO
import json
import os
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit

from app.laboratorio.interfaz_v2 import descubrimiento_youtube as youtube
from app.laboratorio.motor_v2.fuentes import fuente_especifica

ID = 'abcDEF12345'


def api_response():
    return {'items': [{'id': ID, 'snippet': {'title': 'Entidad', 'description': 'Contexto Territorio',
        'publishedAt': '2025-02-03T04:05:06Z', 'channelTitle': 'Canal'},
        'statistics': {'viewCount': '123', 'likeCount': '0'}}]}


class YouTubeTests(unittest.TestCase):
    def test_real_request_stats_missing_counts_and_timestamp(self):
        with patch.dict(os.environ, {'YOUTUBE_API_KEY': 'clave-de-prueba'}), patch.object(youtube, '_abrir_url', return_value=BytesIO(json.dumps(api_response()).encode())) as abrir:
            detalles = youtube.detalles([ID])
        self.assertEqual(abrir.call_args.args[0].full_url.split('?')[0], 'https://www.googleapis.com/youtube/v3/videos')
        parametros = parse_qs(urlsplit(abrir.call_args.args[0].full_url).query)
        self.assertEqual(parametros['part'], ['snippet,statistics'])
        self.assertEqual(parametros['id'], [ID])
        self.assertEqual(parametros['key'], ['clave-de-prueba'])
        metricas = detalles[ID]['metricas']
        self.assertEqual(metricas['vistas'], 123)
        self.assertEqual(metricas['likes'], 0)
        self.assertIsNone(metricas['comentarios'])
        self.assertEqual(metricas['fecha_publicacion'], '2025-02-03T04:05:06Z')
        self.assertTrue(metricas['recuperado_en'])
        self.assertEqual(metricas['proveedor'], 'YOUTUBE_DATA_API_V3')

    def test_errors_do_not_expose_key_or_remote_body(self):
        for error in (URLError('clave-de-prueba'), HTTPError(youtube.ENDPOINT + '?key=clave-de-prueba', 403, 'clave-de-prueba', {}, BytesIO(b'clave-de-prueba'))):
            with self.subTest(error=type(error).__name__), patch.object(youtube, '_abrir_url', side_effect=error):
                with self.assertRaises(youtube.YouTubeError) as resultado:
                    youtube.detalles([ID], 'clave-de-prueba')
                self.assertNotIn('clave-de-prueba', str(resultado.exception))

    def test_video_id_formats_and_hosts(self):
        for url in (f'https://youtu.be/{ID}', f'https://www.youtube.com/watch?v={ID}&t=2',
                    f'https://youtube.com/shorts/{ID}', f'https://youtube.com/live/{ID}',
                    f'https://www.youtube-nocookie.com/embed/{ID}'):
            self.assertEqual(youtube.identificar_video(url), ID)
        for url in (f'https://youtube.com.evil.example/watch?v={ID}', 'https://youtube.com/@canal'):
            self.assertIsNone(youtube.identificar_video(url))

    def test_batching_and_same_id_deduplicated(self):
        ids = [f'{i:011d}' for i in range(51)]
        publicaciones = [{'url': f'https://youtu.be/{vid}'} for vid in ids] + [{'url': f'https://youtube.com/watch?v={ids[0]}'}]
        proveedor = Mock(side_effect=lambda lote, clave: {v: {'metricas': {'vistas': 1}, 'descripcion': 'Texto'} for v in lote})
        resultado = youtube.enriquecer_publicaciones(publicaciones, consultar_detalles=proveedor)
        self.assertEqual(proveedor.call_count, 2)
        self.assertEqual(len(proveedor.call_args_list[0].args[0]), 50)
        self.assertEqual(len(proveedor.call_args_list[1].args[0]), 1)
        self.assertEqual(len(resultado['publicaciones']), 52)
        self.assertTrue(all(p['metodo_recuperacion'] == 'API_OFICIAL' for p in resultado['publicaciones']))

    def test_missing_key_and_video_missing_use_fallback(self):
        publicaciones = [{'url': f'https://youtu.be/{ID}', 'descripcion': 'Resumen de Brave'}]
        with patch.object(youtube, 'clave_youtube', return_value=''), patch.object(youtube, 'detalles') as proveedor:
            resultado = youtube.enriquecer_publicaciones(publicaciones)
            proveedor.assert_not_called()
        self.assertEqual(resultado['solicitudes_intentadas'], 0)
        self.assertIsNone(resultado['publicaciones'][0]['metricas'])
        self.assertEqual(resultado['publicaciones'][0]['error_metricas']['codigo'], 'youtube_no_configurado')
        resultado = youtube.enriquecer_publicaciones(publicaciones, consultar_detalles=lambda *args: {})
        self.assertEqual(resultado['publicaciones'][0]['error_metricas']['codigo'], 'youtube_video_no_disponible')
        self.assertEqual(resultado['publicaciones'][0]['metodo_recuperacion'], 'SNIPPET_BRAVE')

    def test_no_youtube_does_not_read_key_or_call_api(self):
        with patch.object(youtube, 'clave_youtube') as clave:
            resultado = youtube.enriquecer_publicaciones([{'url': 'https://example.org'}])
        clave.assert_not_called()
        self.assertEqual(resultado['solicitudes_intentadas'], 0)
        self.assertEqual(resultado['publicaciones'][0]['fuente_especifica'], 'WEB')

    def test_source_specific_hosts(self):
        casos = [('https://m.youtube.com/watch?v=' + ID, 'YOUTUBE'), ('https://fb.watch/ejemplo', 'FACEBOOK'),
                 ('https://www.facebook.com/x', 'FACEBOOK'), ('https://instagram.com/x', 'INSTAGRAM'),
                 ('https://twitter.com/x/status/1', 'X'), ('https://x.com/x', 'X'),
                 ('https://portal.institucion.gov.ar/a', 'OFICIAL'), ('https://institucion.gob.ar/a', 'OFICIAL'),
                 ('https://gob.ar.evil.example/a', 'WEB'), ('https://example.org/?x=youtube.com', 'WEB')]
        for url, esperado in casos:
            self.assertEqual(fuente_especifica(url), esperado)

    def test_http_error_is_logged_without_authenticated_url(self):
        with patch.object(youtube, '_abrir_url', side_effect=HTTPError(youtube.ENDPOINT + '?key=clave-privada', 403, 'clave-privada', {}, BytesIO())), self.assertLogs(youtube.LOG, level='ERROR') as logs:
            with self.assertRaises(youtube.YouTubeError):
                youtube.detalles([ID], 'clave-privada')
        salida = ' '.join(logs.output)
        self.assertIn('Error HTTP 403', salida)
        self.assertNotIn('clave-privada', salida)
        self.assertNotIn('?key=', salida)

    def test_reserved_characters_in_api_key_are_encoded(self):
        with patch.object(youtube, '_abrir_url', return_value=BytesIO(json.dumps(api_response()).encode())) as abrir:
            youtube.detalles([ID], 'prueba+&=/')
        parametros = parse_qs(urlsplit(abrir.call_args.args[0].full_url).query)
        self.assertEqual(parametros['key'], ['prueba+&=/'])
