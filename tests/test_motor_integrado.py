"""El orquestador adjunto se ejecuta sin permitir ninguna conexión de red."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.laboratorio.interfaz_v2 import descubrimiento_integrado as motor
from app.laboratorio.motor_v2.contratos import Marco


class MotorTests(unittest.TestCase):
    def test_offline_consolidation_and_immutable_history(self):
        payload = {'marco': 'Entidad libre; Contexto; Territorio',
                   'periodo': {'desde': '2025-01-01', 'hasta': '2025-12-31'},
                   'id_ejecucion_documental': 'prueba'}
        with tempfile.TemporaryDirectory() as temporal:
            destino = Path(temporal) / 'datos' / 'ejecuciones' / 'stub'
            with patch.object(motor, 'DESTINO', destino), patch('socket.socket', side_effect=AssertionError('No debe haber red')):
                primero = motor.ejecutar_busqueda(payload)
                snapshots = list(destino.glob('busqueda_integrada_*.json'))
                self.assertEqual(len(snapshots), 1)
                contenido = snapshots[0].read_bytes()
                segundo = motor.ejecutar_busqueda(payload)
                self.assertEqual(snapshots[0].read_bytes(), contenido)
                self.assertEqual(len(list(destino.glob('busqueda_integrada_*.json'))), 2)
                self.assertEqual(segundo['historico']['urls_heredadas'], 3)
                self.assertEqual(primero['total_urls_unicas'], 3)
                self.assertEqual(primero['errores'], [])
                self.assertEqual(primero['youtube_api']['videos_actualizados'], 1)
                web = next(p for p in primero['publicaciones'] if p['origen'] == 'example.com')
                self.assertIn('BRAVE_WEB', web['proveedores'])
                self.assertIn('DUCKDUCKGO_HTML', web['proveedores'])
                self.assertGreater(len(web['consultas_origen']), 1)
                self.assertEqual(segundo['recuperacion_documental']['solicitudes_intentadas'], 0)
                self.assertEqual(primero['recuperacion_documental']['resumen']['documentos_con_texto'], 3)
                self.assertEqual(len(json.loads(contenido)['publicaciones']), 3)

    def test_marco_alternatives_and_planning(self):
        marco = Marco.desde_input('Una entidad, Otra entidad; Contexto; Zona')
        plan = motor.planificar(marco)
        self.assertTrue(any('Una entidad' in q for _, q in plan))
        self.assertTrue(any('Otra entidad' in q for _, q in plan))
        self.assertEqual(len(plan), len({q for _, q in plan}))
        with self.assertRaises(ValueError):
            Marco.desde_input('a;b;c;d')
