"""Contrato DDG con HTML y fallos HTTP controlados, sin Internet en los tests."""
from email.message import Message
from io import BytesIO
from http.client import IncompleteRead
from urllib.error import HTTPError, URLError
import unittest
from unittest.mock import patch

from app.laboratorio.interfaz_v2 import descubrimiento_ddg as ddg
from app.laboratorio.interfaz_v2 import descubrimiento_integrado as motor
from pathlib import Path
import tempfile

HTML = '''<html><div class="result results_links web-result">
<h2><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.org%2Fnota%3Fx%3D1%26y%3D2&amp;rut=abc">Título <b>real</b> &amp; texto</a></h2>
<a class="result__snippet">Descripción <b>anidada</b> del resultado.</a>
</div><div class="result"><a class="result__a" href="https://example.net/otra">Otra nota</a>
<div class="result__snippet">Otra descripción</div></div>
<form action="/html/" method="post"><input type="hidden" name="q" value="consulta">
<input name="s" value="30"><input name="vqd" value="token">
<input type="submit" value="Next"></form></html>'''


class Respuesta(BytesIO):
    status = 200
    def __init__(self, html, status=200):
        super().__init__(html.encode('utf-8'))
        self.status = status
        self.headers = Message()
        self.headers['Content-Type'] = 'text/html; charset=utf-8'


class DDGTests(unittest.TestCase):
    def test_extract_redirect_unicode_and_next_page(self):
        with patch.object(ddg, 'urlopen', return_value=Respuesta(HTML)) as abrir:
            resultados, cursor, diagnostico = ddg.consultar('consulta & ñ', None, True)
        self.assertEqual(resultados[0], {'url': 'https://example.org/nota?x=1&y=2', 'title': 'Título real & texto', 'description': 'Descripción anidada del resultado.'})
        self.assertEqual(len(resultados), 2)
        self.assertEqual(cursor['s'], '30')
        self.assertEqual(diagnostico['estado'], 'OK')
        self.assertIn('q=consulta+%26+%C3%B1', abrir.call_args.args[0].full_url)
        self.assertEqual(abrir.call_args.kwargs['timeout'], ddg.TIMEOUT)
        with patch.object(ddg, 'urlopen', return_value=Respuesta(HTML)) as abrir:
            self.assertEqual(len(ddg.consultar('consulta & ñ', cursor)), 2)
        req = abrir.call_args.args[0]
        self.assertEqual(req.get_method(), 'POST')
        self.assertEqual(req.full_url, ddg.ENDPOINT)
        self.assertIn(b's=30', req.data)
        self.assertIn(b'q=consulta+%26+%C3%B1', req.data)

    def test_network_errors_return_empty_with_warning(self):
        for error in (URLError('sin red'), TimeoutError(), IncompleteRead(b'parcial'), HTTPError(ddg.ENDPOINT, 503, 'fallo', {}, BytesIO())):
            with self.subTest(error=error), patch.object(ddg, 'urlopen', side_effect=error), self.assertLogs(ddg.LOG, level='WARNING'):
                resultados, cursor, diagnostico = ddg.consultar('prueba', con_diagnostico=True)
                self.assertEqual((resultados, cursor), ([], None))
                self.assertEqual(diagnostico['estado'], 'ERROR_HTTP')
                self.assertTrue(diagnostico['aviso'])

    def test_challenges_and_rate_limit(self):
        for status, html in ((202, '<html/>'), (200, '<form id="challenge-form">captcha</form>')):
            with self.subTest(status=status), patch.object(ddg, 'urlopen', return_value=Respuesta(html, status)), self.assertLogs(ddg.LOG):
                self.assertEqual(ddg.consultar('prueba', con_diagnostico=True)[2]['estado'], 'LIMITADO')
        with patch.object(ddg, 'urlopen', side_effect=HTTPError(ddg.ENDPOINT, 429, 'limite', {}, BytesIO())), self.assertLogs(ddg.LOG):
            self.assertEqual(ddg.consultar('prueba', con_diagnostico=True)[2]['estado'], 'LIMITADO')

    def test_empty_and_unknown_html_are_distinct(self):
        with patch.object(ddg, 'urlopen', return_value=Respuesta('<div class="no-results">No results.</div>')):
            self.assertEqual(ddg.consultar('prueba', con_diagnostico=True), ([], None, {'modo': 'DUCKDUCKGO_HTML_REAL', 'estado': 'SIN_RESULTADOS', 'solicitudes_http': 1, 'http_status': 200}))
        with patch.object(ddg, 'urlopen', return_value=Respuesta('<html>cambio de formato</html>')), self.assertLogs(ddg.LOG):
            self.assertEqual(ddg.consultar('prueba', con_diagnostico=True)[2]['estado'], 'ERROR_EXTRACCION')

    def test_unsafe_links_and_duplicates(self):
        html = '<div class="result"><a class="result__a" href="javascript:alert(1)">No</a></div>' + HTML + HTML
        with patch.object(ddg, 'urlopen', return_value=Respuesta(html)):
            self.assertEqual(len(ddg.consultar('prueba')[0]), 2)

    def test_invalid_cursor_and_oversized_body(self):
        with patch.object(ddg, 'urlopen') as abrir, self.assertLogs(ddg.LOG):
            self.assertEqual(ddg.consultar('q', {'url': 'http://otro/'})[0], [])
            abrir.assert_not_called()
        with patch.object(ddg, 'MAX_BYTES', 10), patch.object(ddg, 'urlopen', return_value=Respuesta(HTML)), self.assertLogs(ddg.LOG):
            self.assertEqual(ddg.consultar('prueba')[0], [])

    def test_orchestrator_stops_after_network_error(self):
        payload = {'marco': 'Entidad; Contexto; Territorio', 'periodo': {'desde': '2025-01-01', 'hasta': '2025-12-31'},
                   'max_brave': 0, 'max_youtube': 0, 'max_facebook': 0, 'max_instagram': 0, 'max_x': 0}
        with tempfile.TemporaryDirectory() as carpeta, patch.object(motor, 'DESTINO', Path(carpeta) / 'datos' / 'ejecuciones' / 'ddg'), patch.object(ddg, 'urlopen', side_effect=URLError('sin red')) as abrir, self.assertLogs(ddg.LOG):
            datos = motor.ejecutar_busqueda(payload)
        self.assertEqual(abrir.call_count, 1)
        self.assertEqual(datos['publicaciones'], [])
        self.assertEqual(datos['solicitudes_exitosas'], 0)
        self.assertEqual(datos['estado_ddg'], 'ERROR_HTTP')
        self.assertEqual(datos['solicitudes_externas'], 1)
        self.assertTrue(datos['avisos'])

    def test_real_ddg_results_are_marked_real(self):
        payload = {'marco': 'Entidad; Contexto; Territorio', 'periodo': {'desde': '2025-01-01', 'hasta': '2025-12-31'},
                   'max_ddg': 1, 'max_brave': 0, 'max_youtube': 0, 'max_facebook': 0, 'max_instagram': 0, 'max_x': 0,
                   'max_documentos_enriquecer': 0}
        with tempfile.TemporaryDirectory() as carpeta, patch.object(motor, 'DESTINO', Path(carpeta) / 'datos' / 'ejecuciones' / 'ddg'), patch.object(ddg, 'urlopen', return_value=Respuesta(HTML)):
            datos = motor.ejecutar_busqueda(payload)
        self.assertEqual(len(datos['publicaciones']), 2)
        self.assertTrue(all(p['simulado'] is False for p in datos['publicaciones']))
        self.assertEqual(datos['solicitudes_exitosas'], 1)
