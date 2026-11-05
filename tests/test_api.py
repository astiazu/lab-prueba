"""Pruebas HTTP del contrato de demostración, con Python estándar."""
import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer

from servidor.api import ManejadorHTTP


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), ManejadorHTTP)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, datos):
        conexion = http.client.HTTPConnection(*self.server.server_address)
        try:
            conexion.request('POST', '/api/buscar', json.dumps(datos), {'Content-Type': 'application/json'})
            respuesta = conexion.getresponse()
            return respuesta.status, json.loads(respuesta.read())
        finally:
            conexion.close()

    def test_demo_contract(self):
        periodo = {'desde': '2025-01-01', 'hasta': '2025-12-31'}
        estado, datos = self.post({'marco': 'Entidad libre; Contexto libre; Territorio libre', 'periodo': periodo})
        self.assertEqual(estado, 200)
        self.assertEqual(set(datos), {'total_urls_unicas', 'solicitudes_exitosas', 'origenes', 'publicaciones', 'errores', 'avisos', 'advertencia', 'periodo'})
        self.assertEqual(datos['periodo'], periodo)
        self.assertEqual(len(datos['publicaciones']), 3)
        self.assertEqual(datos['total_urls_unicas'], len({p['url'] for p in datos['publicaciones']}))
        self.assertEqual(datos['solicitudes_exitosas'], 0)
        self.assertIn('DEMO', datos['advertencia'])
        for publicacion in datos['publicaciones']:
            self.assertIn('Entidad libre', publicacion['titulo'])
            self.assertIn('Contexto libre', publicacion['resumen'])
            self.assertIn('Territorio libre', publicacion['resumen'])

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


if __name__ == '__main__':
    unittest.main()
