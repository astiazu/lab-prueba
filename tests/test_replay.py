"""Fixtures genéricas de unidad; no sustituyen la validación sobre una corrida real."""
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.laboratorio.replay import main, reprocesar_corrida
from app.laboratorio.motor_v2 import acumulativo


def entrada():
    return {'marco': 'Otro Elemento; Otro Proceso; Otra Zona',
            'periodo': {'desde': '2025-01-01', 'hasta': '2025-12-31'},
            'publicaciones': [{'url': 'https://example.org/nota', 'titulo': 'Elemento Alfa',
                              'descripcion': 'Proceso', 'cuerpo_extraido': 'Zona Local',
                              'metricas': {'vistas': 10, 'recuperado_en': '2025-01-01T00:00:00Z'}}],
            'publicaciones_descartadas': [{'url': 'https://example.org/otra', 'titulo': 'Otra Identidad', 'descripcion': 'Proceso Zona Local'}],
            'publicaciones_archivadas': [{'url': 'https://example.org/fria', 'titulo': 'Contenido ajeno', 'archivado': True,
                                          'score_emm': 0, 'motivo_descarte': 'sin_entidad_principal'}]}


class ReplayTests(unittest.TestCase):
    def test_replay_uses_new_frame_and_never_calls_network(self):
        original = entrada()
        previo = deepcopy(original)
        with patch('socket.socket', side_effect=AssertionError('No se permite red')), patch('urllib.request.urlopen', side_effect=AssertionError('No se permite HTTP')):
            salida = reprocesar_corrida(original, 'Elemento Alfa; Proceso; Zona Local, Zona Amplia')
        self.assertEqual(original, previo)
        self.assertEqual(salida['modo'], 'REPLAY_SIN_RED')
        self.assertEqual(salida['marco_origen'], original['marco'])
        self.assertEqual(salida['solicitudes_externas'], 0)
        self.assertEqual(salida['solicitudes_por_proveedor']['BRAVE_WEB'], 0)
        self.assertEqual(salida['urls_nuevas_esta_corrida'], 0)
        self.assertTrue(all(p['score_emm'] >= salida['politica_emm']['umbral_aceptacion'] for p in salida['publicaciones']))
        self.assertEqual(salida['publicaciones'][0]['metricas'], original['publicaciones'][0]['metricas'])
        self.assertEqual(salida['publicaciones_archivadas'], original['publicaciones_archivadas'])

    def test_input_and_replay_counts_are_distinct_and_consistent(self):
        original = entrada()
        original['publicaciones'].append(original['publicaciones_descartadas'].pop())
        salida = reprocesar_corrida(original, 'Elemento Alfa; Proceso; Zona Local')
        self.assertNotIn('urls_heredadas_aceptadas', salida)
        self.assertEqual(salida['urls_heredadas_aceptadas_input'], len(original['publicaciones']))
        self.assertEqual(salida['urls_heredadas_aceptadas_replay'], len(salida['publicaciones']))
        self.assertNotEqual(salida['urls_heredadas_aceptadas_input'], salida['urls_heredadas_aceptadas_replay'])
        self.assertEqual(salida['aceptadas_reales'] + salida['aceptadas_marginales'], salida['total_publicaciones_aceptadas'])

    def test_archived_records_are_never_scored(self):
        with patch.object(acumulativo, 'evaluar_publicacion', wraps=acumulativo.evaluar_publicacion) as evaluar:
            salida = reprocesar_corrida(entrada(), 'Elemento Alfa; Proceso; Zona Local')
        urls = {c.args[1]['url'] for c in evaluar.call_args_list}
        self.assertNotIn('https://example.org/fria', urls)
        self.assertEqual(len(urls), salida['urls_heredadas_aceptadas_input'] + salida['urls_heredadas_descartadas_activas'])

    def test_cli_reads_json_and_writes_complete_new_output(self):
        with tempfile.TemporaryDirectory() as temporal:
            origen = Path(temporal) / 'entrada.json'
            destino = Path(temporal) / 'salida.json'
            origen.write_text(json.dumps(entrada()), encoding='utf-8')
            previo = origen.read_bytes()
            with redirect_stdout(io.StringIO()), patch('socket.socket', side_effect=AssertionError('Sin red')):
                codigo = main(['--replay', str(origen), '--marco', 'Elemento Alfa; Proceso; Zona Local', '--salida', str(destino)])
            self.assertEqual(codigo, 0)
            self.assertEqual(origen.read_bytes(), previo)
            salida = json.loads(destino.read_text())
            for campo in ('urls_nuevas_esta_corrida', 'urls_heredadas_aceptadas_input', 'urls_heredadas_descartadas_activas', 'urls_heredadas_archivadas', 'aceptadas_reales', 'aceptadas_marginales', 'publicaciones', 'publicaciones_descartadas', 'publicaciones_archivadas'):
                self.assertIn(campo, salida)
            with redirect_stderr(io.StringIO()):
                self.assertNotEqual(main(['--replay', str(origen), '--marco', 'Elemento Alfa; Proceso; Zona Local', '--salida', str(destino)]), 0)

    def test_invalid_input_is_explicit_error_not_synthetic_fallback(self):
        with tempfile.TemporaryDirectory() as temporal, redirect_stderr(io.StringIO()) as errores:
            codigo = main(['--replay', str(Path(temporal) / 'inexistente.json'), '--marco', 'Elemento; Proceso; Zona'])
        self.assertNotEqual(codigo, 0)
        self.assertEqual(json.loads(errores.getvalue())['error']['codigo'], 'replay_invalido')
