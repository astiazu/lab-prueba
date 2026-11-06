from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from io import BytesIO
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from app.laboratorio.motor_v2 import recuperacion_documental_enriquecida as recuperacion
from app.laboratorio.interfaz_v2 import descubrimiento_integrado as motor


class Respuesta(BytesIO):
    def __init__(self, cuerpo, tipo='text/html; charset=utf-8'):
        super().__init__(cuerpo)
        self.headers = Message()
        self.headers['Content-Type'] = tipo


class RecuperacionTests(unittest.TestCase):
    def test_http_download_from_running_server(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                cuerpo = '<html><body><main>Contenido verificado por HTTP</main></body></html>'.encode()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(cuerpo)))
                self.end_headers()
                self.wfile.write(cuerpo)
            def log_message(self, *args):
                pass
        servidor = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
        hilo.start()
        try:
            html = recuperacion.descargar_html(f'http://127.0.0.1:{servidor.server_port}/documento')
            self.assertEqual(recuperacion.extraer_cuerpo(html), 'Contenido verificado por HTTP')
        finally:
            servidor.shutdown()
            servidor.server_close()
            hilo.join()

    def test_body_main_cleanup_and_limit(self):
        html = '<head><title>Fuera</title></head><body><nav>Menú</nav><div>Fuera de main</div><main><h1>Título</h1><p>Texto &amp; <b>detalle</b>.</p><script>script</script><style>style</style><div hidden>oculto</div><footer>Pie</footer></main></body>'
        texto = recuperacion.extraer_cuerpo(html)
        self.assertEqual(texto, 'Menú Fuera de main Título Texto & detalle . Pie')
        self.assertEqual(recuperacion.extraer_cuerpo('<body><p>Texto sin main</p></body>'), 'Texto sin main')
        self.assertEqual(recuperacion.extraer_cuerpo('<body><div style="display:none"><p style="display:none">oculto</p></div>visible</body>'), 'visible')
        self.assertEqual(len(recuperacion.extraer_cuerpo('<body>' + 'a' * 6000 + '</body>')), 5000)

    def test_real_http_request_encoding_and_no_api_header(self):
        cuerpo = '<body>Región</body>'.encode('iso-8859-1')
        with patch.object(recuperacion, 'urlopen', return_value=Respuesta(cuerpo, 'text/html; charset=iso-8859-1')) as abrir:
            html = recuperacion.descargar_html('https://example.org/nota')
        self.assertEqual(recuperacion.extraer_cuerpo(html), 'Región')
        self.assertIsNone(abrir.call_args.args[0].get_header('X-subscription-token'))
        self.assertEqual(abrir.call_args.kwargs['timeout'], recuperacion.TIMEOUT)

    def test_errors_non_html_size_and_invalid_url(self):
        for error in (URLError('privado'), HTTPError('https://example.org', 403, 'privado', {}, BytesIO())):
            with self.subTest(error=type(error).__name__), patch.object(recuperacion, 'urlopen', side_effect=error):
                with self.assertRaises(recuperacion.ErrorRecuperacion) as resultado:
                    recuperacion.descargar_html('https://example.org')
                self.assertNotIn('privado', str(resultado.exception))
        with patch.object(recuperacion, 'urlopen', return_value=Respuesta(b'pdf', 'application/pdf')):
            with self.assertRaises(recuperacion.ErrorRecuperacion):
                recuperacion.descargar_html('https://example.org')
        with patch.object(recuperacion, 'MAX_BYTES', 2), patch.object(recuperacion, 'urlopen', return_value=Respuesta(b'largooo')):
            with self.assertRaises(recuperacion.ErrorRecuperacion):
                recuperacion.descargar_html('https://example.org')
        with self.assertRaises(recuperacion.ErrorRecuperacion):
            recuperacion.descargar_html('file:///tmp/documento')

    def test_failure_and_budget_preserve_every_candidate(self):
        candidatos = [{'url': 'https://example.org/1'}, {'url': 'https://example.org/2'}]
        def falla(url):
            raise recuperacion.ErrorRecuperacion('error_red', 'No disponible')
        resultado = recuperacion.enriquecer(candidatos, obtener_html=falla, max_solicitudes=1)
        self.assertEqual(len(resultado['publicaciones']), 2)
        self.assertEqual([p['cuerpo_extraido'] for p in resultado['publicaciones']], ['', ''])
        self.assertEqual([p['recuperacion']['estado'] for p in resultado['publicaciones']], ['ERROR', 'PENDIENTE'])
        self.assertEqual(resultado['pendientes'], 1)
        self.assertNotIn('cuerpo_extraido', candidatos[0])

    def test_description_fallback_and_103_candidates(self):
        candidatos = [{'url': f'https://example.org/{i}', 'descripcion': 'Entidad Contexto Territorio' + 'x' * 6000} for i in range(103)]
        def falla(url):
            raise recuperacion.ErrorRecuperacion('error_http', 'El documento devolvió HTTP 403.')
        resultado = recuperacion.enriquecer(candidatos, obtener_html=falla)
        self.assertEqual(resultado['solicitudes_intentadas'], 103)
        self.assertEqual(len(resultado['publicaciones']), 103)
        self.assertEqual(resultado['pendientes'], 0)
        for p in resultado['publicaciones']:
            self.assertEqual(p['cuerpo_extraido'], p['descripcion'][:5000])
            self.assertEqual(p['recuperacion']['estado'], 'ERROR')
            self.assertEqual(p['recuperacion']['fuente_texto'], 'DESCRIPCION_BRAVE')

    def test_orchestrator_scores_all_103_and_logs_each_one(self):
        payload = {'marco': 'Entidad; Contexto; Territorio', 'periodo': {'desde': '2025-01-01', 'hasta': '2025-12-31'}, 'max_brave': 1}
        def proveedor(*args):
            return {'web': {'results': [{'url': f'https://example.org/{i}', 'title': 'Entidad', 'description': 'Contexto Territorio'} for i in range(103)]}}
        def falla(url):
            raise recuperacion.ErrorRecuperacion('error_http', 'HTTP 403')
        with tempfile.TemporaryDirectory() as temporal, patch.object(motor, 'DESTINO', Path(temporal) / 'datos' / 'ejecuciones' / 'brave'), self.assertLogs(motor.__name__, level='INFO') as logs:
            resultado = motor.ejecutar_busqueda(payload, brave_consultar=proveedor, documental_obtener_html=falla)
        self.assertEqual(resultado['recuperacion_documental']['solicitudes_intentadas'], 103)
        self.assertEqual(len(resultado['publicaciones']), 103)
        self.assertEqual(len(logs.output), 103)
        self.assertIn('103/103', logs.output[-1])
        self.assertTrue(all(p['score_emm'] == 1.0 for p in resultado['publicaciones']))
        self.assertTrue(all(p['evaluacion_contextual']['detalles'] for p in resultado['publicaciones']))

    def test_end_to_end_retains_zero_score_and_download_failure(self):
        payload = {'marco': 'Entidad Alfa; Contexto Beta; Territorio Gamma',
                   'periodo': {'desde': '2025-01-01', 'hasta': '2025-12-31'}, 'max_brave': 1}
        def proveedor(*args):
            return {'web': {'results': [{'url': f'https://example.org/{i}', 'title': 'Texto de prueba'} for i in range(3)]}}
        def obtener(url):
            if url.endswith('/0'):
                return '<body>Entidad Alfa Contexto Beta Territorio Gamma</body>'
            if url.endswith('/1'):
                return '<body>Contenido diferente</body>'
            raise recuperacion.ErrorRecuperacion('error_red', 'No disponible')
        with tempfile.TemporaryDirectory() as temporal, patch.object(motor, 'DESTINO', Path(temporal) / 'datos' / 'ejecuciones' / 'brave'):
            resultado = motor.ejecutar_busqueda(payload, brave_consultar=proveedor, documental_obtener_html=obtener)
        self.assertEqual(resultado['total_urls_unicas'], 3)
        self.assertEqual(len(resultado['publicaciones']), 1)
        self.assertEqual(resultado['publicaciones'][0]['score_emm'], 1.0)
        self.assertEqual([p['evaluacion_contextual']['score_emm'] for p in resultado['publicaciones_descartadas']], [0.0, 0.0])
        self.assertEqual(resultado['publicaciones_descartadas'][1]['recuperacion']['estado'], 'ERROR')
        self.assertEqual(resultado['recuperacion_documental']['documentos_con_texto'], 2)
        self.assertEqual(resultado['errores'][0]['proveedor'], 'RECUPERACION_DOCUMENTAL')

    def test_recovery_method_html_vs_snippet(self):
        candidato = {'url': 'https://example.org/1', 'descripcion': 'Resumen de Brave'}
        html = recuperacion.enriquecer([candidato], obtener_html=lambda url: '<body>Cuerpo</body>')['publicaciones'][0]
        self.assertEqual(html['metodo_recuperacion'], 'HTML_SCRAPING')
        def falla(url):
            raise recuperacion.ErrorRecuperacion('error_http', 'HTTP 403')
        snippet = recuperacion.enriquecer([candidato], obtener_html=falla)['publicaciones'][0]
        self.assertEqual(snippet['metodo_recuperacion'], 'SNIPPET_BRAVE')
        self.assertEqual(snippet['cuerpo_extraido'], 'Resumen de Brave')
