"""Cliente Brave: HTTP, autenticación y errores sin credenciales expuestas."""
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlsplit
import json
import os
import unittest
from unittest.mock import patch

from app.laboratorio.interfaz_v2 import descubrimiento_brave as brave


class BraveTests(unittest.TestCase):
    def setUp(self):
        self.turno = patch.object(brave, '_esperar_turno')
        self.turno.start()
        self.addCleanup(self.turno.stop)

    def test_request_headers_query_and_dates(self):
        respuesta = {'web': {'results': [{'url': 'https://example.org', 'title': 'Título', 'description': 'Descripción'}]}}
        with patch.dict(os.environ, {'BRAVE_API_KEY': 'clave-de-prueba'}), patch.object(brave, '_abrir_url', return_value=BytesIO(json.dumps(respuesta).encode())) as abrir:
            datos = brave._brave('consulta & ñ', '2025-01-01', '2025-12-31')
        self.assertEqual(datos, respuesta)
        req = abrir.call_args.args[0]
        self.assertEqual(req.get_header('X-subscription-token'), 'clave-de-prueba')
        self.assertEqual(urlsplit(req.full_url).netloc, 'api.search.brave.com')
        parametros = parse_qs(urlsplit(req.full_url).query)
        self.assertEqual(parametros['q'], ['consulta & ñ'])
        self.assertEqual(parametros['freshness'], ['2025-01-01to2025-12-31'])
        self.assertEqual(parametros['count'], ['20'])
        self.assertNotIn('clave-de-prueba', req.full_url)
        self.assertEqual(abrir.call_args.kwargs['timeout'], 15)

    def test_missing_key_does_not_connect(self):
        with patch.dict(os.environ, {'BRAVE_API_KEY': ''}), patch.object(brave, 'cargar_entorno'), patch.object(brave, '_abrir_url') as abrir:
            with self.assertRaises(brave.BraveError) as error:
                brave._brave('consulta', '2025-01-01', '2025-12-31')
            self.assertEqual(error.exception.codigo, 'brave_no_configurado')
            abrir.assert_not_called()

    def test_network_and_http_errors_are_controlled(self):
        for error, codigo in [(URLError('detalle privado'), 'brave_error_red'),
                               (TimeoutError(), 'brave_error_red'),
                               (HTTPError(brave.ENDPOINT, 401, 'clave-de-prueba', {}, BytesIO()), 'brave_acceso_denegado'),
                               (HTTPError(brave.ENDPOINT, 429, 'cuota', {}, BytesIO()), 'brave_limite')]:
            with self.subTest(error=type(error).__name__), patch.object(brave, '_abrir_url', side_effect=error):
                with self.assertRaises(brave.BraveError) as resultado:
                    brave._brave('q', '2025-01-01', '2025-12-31', 'clave-de-prueba')
                self.assertEqual(resultado.exception.codigo, codigo)
                self.assertNotIn('clave-de-prueba', str(resultado.exception))
                self.assertNotIn('detalle privado', str(resultado.exception))

    def test_invalid_json_schema_and_size(self):
        for cuerpo in (b'no es json', b'[]', b'{"web":{"results":"no es lista"}}', b'{"web":{"results":[1]}}'):
            with self.subTest(cuerpo=cuerpo), patch.object(brave, '_abrir_url', return_value=BytesIO(cuerpo)):
                with self.assertRaises(brave.BraveError):
                    brave._brave('q', '2025-01-01', '2025-12-31', 'clave-de-prueba')
        with patch.object(brave, 'MAX_BYTES', 2), patch.object(brave, '_abrir_url', return_value=BytesIO(b'{} ')):
            with self.assertRaises(brave.BraveError):
                brave._brave('q', '2025-01-01', '2025-12-31', 'clave-de-prueba')

    def test_redirects_are_not_followed(self):
        self.assertIsNone(brave._SinRedireccion().redirect_request(None, None, 302, '', {}, 'https://otro.example/'))

    def test_page_offset_is_sent_and_validated(self):
        with patch.object(brave, '_abrir_url', return_value=BytesIO(b'{"web":{"results":[]}}')) as abrir:
            brave._brave('q', '2025-01-01', '2025-12-31', 'clave-de-prueba', offset=2)
        self.assertEqual(parse_qs(urlsplit(abrir.call_args.args[0].full_url).query)['offset'], ['2'])
        with self.assertRaises(ValueError):
            brave._brave('q', '2025-01-01', '2025-12-31', 'clave-de-prueba', offset=10)


class BraveRateLimiterTests(unittest.TestCase):
    def test_calls_are_spaced_without_actual_sleep(self):
        with patch.object(brave, '_ultimo_inicio', 100.0), patch.object(brave.time, 'monotonic', side_effect=[100.2, 101.1]), patch.object(brave.time, 'sleep') as dormir:
            brave._esperar_turno()
            self.assertAlmostEqual(dormir.call_args.args[0], 0.9)
            self.assertEqual(brave._ultimo_inicio, 101.1)
