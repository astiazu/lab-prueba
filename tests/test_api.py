"""Pruebas HTTP del contrato de demostración, con Python estándar."""
import builtins
import http.client
import json
import os
import threading
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

from app.laboratorio.interfaz_v2 import descubrimiento_integrado as motor
from http.server import ThreadingHTTPServer

from servidor.api import ManejadorHTTP


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporal = tempfile.TemporaryDirectory()
        cls.destino = patch.object(motor, 'DESTINO', Path(cls.temporal.name) / 'datos' / 'ejecuciones' / 'stub')
        cls.destino.start()
        cls.entorno = patch.dict(os.environ, {'BRAVE_API_KEY': 'clave-de-prueba'})
        cls.entorno.start()
        cls.proveedor = patch.object(motor.brave, '_brave', return_value={'web': {'results': [
            {'url': 'https://example.org/nota', 'title': 'Nota de prueba', 'description': 'Descripción de prueba'}]}})
        cls.proveedor.start()
        from app.laboratorio.motor_v2 import recuperacion_documental_enriquecida as recuperacion
        cls.html = patch.object(recuperacion, 'descargar_html', return_value='<body>Entidad libre Contexto libre Territorio libre</body>')
        cls.html.start()
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), ManejadorHTTP)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.html.stop()
        cls.proveedor.stop()
        cls.entorno.stop()
        cls.destino.stop()
        cls.temporal.cleanup()

    def post(self, datos):
        conexion = http.client.HTTPConnection(*self.server.server_address)
        try:
            conexion.request('POST', '/api/buscar', json.dumps(datos), {'Content-Type': 'application/json'})
            respuesta = conexion.getresponse()
            return respuesta.status, json.loads(respuesta.read())
        finally:
            conexion.close()

    def test_brave_contract(self):
        periodo = {'desde': '2025-01-01', 'hasta': '2025-12-31'}
        estado, datos = self.post({'marco': 'Entidad libre; Contexto libre; Territorio libre', 'periodo': periodo})
        self.assertEqual(estado, 200)
        self.assertTrue(set(datos) >= {'total_urls_unicas', 'solicitudes_exitosas', 'origenes', 'publicaciones', 'errores', 'avisos', 'advertencia', 'periodo'})
        self.assertEqual(datos['periodo'], periodo)
        self.assertEqual(len(datos['publicaciones']), 1)
        self.assertEqual(datos['total_urls_unicas'], len({p['url'] for p in datos['publicaciones']}))
        self.assertGreater(datos['solicitudes_exitosas'], 0)
        self.assertGreater(datos['solicitudes_externas'], 0)
        self.assertFalse(datos['simulado'])
        self.assertTrue(Path(motor.DESTINO).is_dir())
        self.assertEqual(datos['modo'], 'BRAVE_SEARCH_REAL')
        for publicacion in datos['publicaciones']:
            self.assertFalse(publicacion['simulado'])
            self.assertTrue(publicacion['proveedores'])
        self.assertEqual(datos['recuperacion_documental']['documentos_con_texto'], 1)
        self.assertEqual(datos['publicaciones'][0]['evaluacion_contextual']['score_emm'], 0.8)

    def test_invalid_input(self):
        periodo = {'desde': '2025-01-01', 'hasta': '2025-12-31'}
        for marco in ('', 'incompleto', 'a;;c', 7):
            with self.subTest(marco=marco):
                estado, datos = self.post({'marco': marco, 'periodo': periodo})
                self.assertEqual(estado, 400)
                self.assertEqual(datos['error']['codigo'], 'marco_invalido')
        for periodo in (None, 'custom', {}, {'desde': 'incorrecto', 'hasta': '2025-12-31'}, {'desde': '2026-01-01', 'hasta': '2025-01-01'}):
            with self.subTest(periodo=periodo):
                estado, datos = self.post({'marco': 'a;b;c', 'periodo': periodo})
                self.assertEqual(estado, 400)
                self.assertEqual(datos['error']['codigo'], 'periodo_invalido')

    def test_engine_errors_are_json(self):
        payload = {'marco': 'a;b;c', 'periodo': {'desde': '2025-01-01', 'hasta': '2025-12-31'}}
        for error, status, code in [(ImportError('dependencia'), 500, 'motor_no_disponible'),
                                    (ValueError('Presupuesto inválido'), 400, 'entrada_motor_invalida'),
                                    (OSError('ruta interna privada'), 500, 'error_motor')]:
            with self.subTest(error=error), patch.object(motor, 'ejecutar_busqueda', side_effect=error):
                estado, datos = self.post(payload)
                self.assertEqual(estado, status)
                self.assertEqual(datos['error']['codigo'], code)
                self.assertNotIn('ruta interna privada', json.dumps(datos))

    def test_missing_import_is_json(self):
        importar = builtins.__import__
        def sin_motor(nombre, *args, **kwargs):
            if nombre == 'app.laboratorio.interfaz_v2.descubrimiento_integrado':
                raise ImportError('Motor ausente')
            return importar(nombre, *args, **kwargs)
        with patch('builtins.__import__', side_effect=sin_motor):
            estado, datos = self.post({'marco': 'a;b;c', 'periodo': {'desde': '2025-01-01', 'hasta': '2025-12-31'}})
        self.assertEqual(estado, 500)
        self.assertEqual(datos['error']['codigo'], 'motor_no_disponible')

    def test_missing_key_is_json(self):
        with patch.dict(os.environ, {'BRAVE_API_KEY': ''}), patch.object(motor.brave, 'cargar_entorno'):
            estado, datos = self.post({'marco': 'a;b;c', 'periodo': {'desde': '2025-01-01', 'hasta': '2025-12-31'}})
        self.assertEqual(estado, 503)
        self.assertEqual(datos['error']['codigo'], 'brave_no_configurado')

    def test_budget_is_forwarded_to_engine(self):
        estado, datos = self.post({'marco': 'a;b;c', 'periodo': {'desde': '2025-01-01', 'hasta': '2025-12-31'}, 'max_brave': -1})
        self.assertEqual(estado, 400)
        self.assertEqual(datos['error']['codigo'], 'entrada_motor_invalida')


if __name__ == '__main__':
    unittest.main()
