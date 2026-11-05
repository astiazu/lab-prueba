"""Orquestación Brave exclusiva, consolidación e histórico inmutable."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.laboratorio.interfaz_v2 import descubrimiento_integrado as motor
from app.laboratorio.motor_v2.contratos import Marco

PAYLOAD = {'marco': 'Entidad libre; Contexto; Territorio',
           'periodo': {'desde': '2025-01-01', 'hasta': '2025-12-31'}, 'max_brave': 2}
RESPUESTA = {'web': {'results': [{'url': 'https://example.org/nota#fragmento', 'title': 'Nota', 'description': 'Texto'}]}}


class MotorTests(unittest.TestCase):
    def test_brave_only_and_immutable_history(self):
        proveedor = Mock(return_value=RESPUESTA)
        with tempfile.TemporaryDirectory() as temporal:
            destino = Path(temporal) / 'datos' / 'ejecuciones' / 'brave'
            with patch.object(motor, 'DESTINO', destino), patch('socket.socket', side_effect=AssertionError('No debe haber red en tests')):
                primero = motor.ejecutar_busqueda({**PAYLOAD, 'max_ddg': 90, 'max_youtube': 20}, brave_consultar=proveedor)
                snapshot = next(destino.glob('busqueda_integrada_*.json'))
                contenido = snapshot.read_bytes()
                segundo = motor.ejecutar_busqueda(PAYLOAD, brave_consultar=proveedor)
                self.assertEqual(snapshot.read_bytes(), contenido)
                self.assertEqual(len(list(destino.glob('busqueda_integrada_*.json'))), 2)
                self.assertEqual(segundo['historico']['urls_heredadas'], 1)
                self.assertEqual(primero['total_urls_unicas'], 1)
                self.assertEqual(primero['errores'], [])
                self.assertEqual(primero['solicitudes_por_proveedor'], {'BRAVE_WEB': 2})
                self.assertEqual(proveedor.call_count, 4)
                publicacion = primero['publicaciones'][0]
                self.assertEqual(publicacion['proveedores'], ['BRAVE_WEB'])
                self.assertEqual(len(publicacion['consultas_origen']), 2)
                self.assertFalse(publicacion['simulado'])
                self.assertEqual(len(json.loads(contenido)['publicaciones']), 1)
                self.assertNotIn('recuperacion_documental', primero)

    def test_error_stops_provider_without_retry(self):
        proveedor = Mock(side_effect=motor.brave.BraveError('brave_limite', 'Límite alcanzado', 429))
        with tempfile.TemporaryDirectory() as temporal, patch.object(motor, 'DESTINO', Path(temporal) / 'datos' / 'ejecuciones' / 'brave'):
            resultado = motor.ejecutar_busqueda(PAYLOAD, brave_consultar=proveedor)
        self.assertEqual(proveedor.call_count, 1)
        self.assertEqual(resultado['solicitudes_exitosas'], 0)
        self.assertEqual(resultado['publicaciones'], [])
        self.assertEqual(resultado['errores'][0]['codigo'], 'brave_limite')
        self.assertTrue(resultado['avisos'])

    def test_marco_alternatives_and_planning(self):
        marco = Marco.desde_input('Una entidad, Otra entidad; Contexto; Zona')
        plan = motor.planificar(marco)
        self.assertTrue(any('Una entidad' in q for _, q in plan))
        self.assertTrue(any('Otra entidad' in q for _, q in plan))
        self.assertEqual(len(plan), len({q for _, q in plan}))
        with self.assertRaises(ValueError):
            Marco.desde_input('a;b;c;d')
