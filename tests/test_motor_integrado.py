"""Integración de Brave, recuperación, métricas y archivo frío."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.laboratorio.interfaz_v2 import descubrimiento_integrado as motor
from app.laboratorio.motor_v2 import acumulativo

PAYLOAD = {'marco': 'Elemento Alfa; Proceso; Zona', 'periodo': {'desde': '2025-01-01', 'hasta': '2025-12-31'},
           'max_brave': 3, 'max_documentos_enriquecer': 0}


def respuesta(entradas):
    return {'web': {'results': [{'url': f'https://example.org/{k}', 'title': v} for k, v in entradas.items()]}}


class MotorTests(unittest.TestCase):
    def setUp(self):
        self.temporal = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.destino = Path(self.temporal.name) / 'datos' / 'ejecuciones' / 'brave'
        cambio = patch.object(motor, 'DESTINO', self.destino)
        cambio.start()
        self.addCleanup(cambio.stop)

    def test_cold_archive_is_skipped_even_if_brave_rediscovers_it(self):
        entradas = {'nota': 'Elemento Alfa Proceso Zona', 'fria': 'Contenido ajeno', 'activa': 'Elemento Alfa', 'limite': 'Proceso'}
        primero = motor.ejecutar_busqueda(PAYLOAD, brave_consultar=lambda *args: respuesta(entradas))
        archivo = next(self.destino.glob('busqueda_integrada_*.json'))
        previo = archivo.read_bytes()
        frias = {p['url'] for p in primero['publicaciones_archivadas']}
        obtener = Mock(return_value='<body>Elemento Alfa Proceso Zona</body>')
        with patch.object(acumulativo, 'evaluar_publicacion', wraps=acumulativo.evaluar_publicacion) as evaluar:
            segundo = motor.ejecutar_busqueda({**PAYLOAD, 'max_documentos_enriquecer': None},
                brave_consultar=lambda *args: respuesta(entradas), documental_obtener_html=obtener)
        self.assertEqual(archivo.read_bytes(), previo)
        self.assertTrue(all(c.args[0] not in frias for c in obtener.call_args_list))
        self.assertTrue(all(c.args[1]['url'] not in frias for c in evaluar.call_args_list))
        self.assertEqual(segundo['urls_heredadas_archivadas'], len(frias))
        self.assertEqual(segundo['urls_reencontradas_archivadas'], len(frias))
        self.assertEqual(segundo['urls_heredadas_aceptadas_input'], len(primero['publicaciones']))
        self.assertEqual(segundo['urls_heredadas_descartadas_activas'], len(primero['publicaciones_descartadas']))

    def test_pagination_and_stages_collect_more_than_twenty(self):
        def proveedor(q, desde, hasta, clave, *, offset=0):
            etapa = 0 if 'AND Proceso' in q else 1 if 'AND (' in q else 2
            n = 20 if not offset else 2
            return {'query': {'more_results_available': not offset}, 'web': {'results': [
                {'url': f'https://example.org/{etapa}/{offset}/{i}', 'title': 'Elemento Alfa Proceso Zona'} for i in range(n)]}}
        salida = motor.ejecutar_busqueda({**PAYLOAD, 'max_brave': 10}, brave_consultar=proveedor)
        self.assertEqual(salida['total_urls_descubiertas'], 3 * (20 + 2))
        self.assertEqual({r['pagina'] for r in salida['consultas_ejecutadas']}, {1, 2})
        self.assertTrue(all(p['hallazgos_brave'] for p in salida['publicaciones']))

    def test_youtube_metrics_and_native_text_survive_classification(self):
        vid = 'abcDEF12345'
        data = {'web': {'results': [{'url': f'https://youtu.be/{vid}', 'title': 'Elemento Alfa'}]}}
        def detalles(ids, clave):
            return {vid: {'metricas': {'vistas': 123}, 'descripcion': 'Proceso Zona'}}
        salida = motor.ejecutar_busqueda(PAYLOAD, brave_consultar=lambda *args: data, youtube_detalles=detalles)
        self.assertTrue(all(p['metricas']['vistas'] == 123 and p['metodo_recuperacion'] == 'API_OFICIAL' for p in salida['publicaciones']))
        self.assertEqual(salida['recuperacion_documental']['solicitudes_intentadas'], 0)

    def test_error_stops_brave_without_retry(self):
        proveedor = Mock(side_effect=motor.brave.BraveError('brave_limite', 'Cuota', 429))
        salida = motor.ejecutar_busqueda(PAYLOAD, brave_consultar=proveedor)
        proveedor.assert_called_once()
        self.assertEqual(salida['solicitudes_exitosas'], 0)
        self.assertTrue(salida['errores'])

    def test_marginal_and_real_counts_match_actual_scores(self):
        salida = motor.ejecutar_busqueda(PAYLOAD, brave_consultar=lambda *args: respuesta({'alta': 'Elemento Alfa Proceso Zona', 'marginal': 'Elemento Alfa Proceso', 'fria': 'Ajeno'}))
        politica = salida['politica_emm']
        self.assertEqual(salida['aceptadas_reales'], sum(p['score_emm'] >= politica['umbral_real'] for p in salida['publicaciones']))
        self.assertEqual(salida['aceptadas_marginales'], sum(politica['umbral_aceptacion'] <= p['score_emm'] < politica['umbral_real'] for p in salida['publicaciones']))
        self.assertEqual(salida['total_urls_activas'], len(salida['publicaciones']) + len(salida['publicaciones_descartadas']))
