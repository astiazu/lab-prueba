"""Orquestación Brave exclusiva, consolidación e histórico inmutable."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.laboratorio.interfaz_v2 import descubrimiento_integrado as motor
from app.laboratorio.motor_v2.contratos import Marco

PAYLOAD = {'marco': 'Entidad libre; Contexto; Territorio',
           'periodo': {'desde': '2025-01-01', 'hasta': '2025-12-31'}, 'max_brave': 2, 'max_documentos_enriquecer': 0}
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
                self.assertEqual(primero['solicitudes_por_proveedor'], {'BRAVE_WEB': 2, 'RECUPERACION_DOCUMENTAL': 0, 'YOUTUBE_DATA_API_V3': 0})
                self.assertEqual(proveedor.call_count, 4)
                self.assertEqual(proveedor.call_args.args[0], '"Entidad libre" AND (Territorio)')
                publicacion = primero['publicaciones_descartadas'][0]
                self.assertEqual(publicacion['proveedores'], ['BRAVE_WEB'])
                self.assertEqual(len(publicacion['consultas_origen']), 2)
                self.assertFalse(publicacion['simulado'])
                self.assertEqual(len(json.loads(contenido)['publicaciones_descartadas']), 1)
                self.assertEqual(primero['recuperacion_documental']['pendientes'], 1)
                self.assertEqual(publicacion['evaluacion_contextual']['score_emm'], 0.0)

    def test_old_natural_language_snapshots_are_not_inherited(self):
        with tempfile.TemporaryDirectory() as temporal:
            destino = Path(temporal) / 'datos' / 'ejecuciones' / 'brave'
            destino.mkdir(parents=True)
            anterior = {'modo': 'BRAVE_SEARCH_REAL', 'marco': PAYLOAD['marco'], 'periodo': PAYLOAD['periodo'],
                        'publicaciones': [{'url': 'https://example.org/anterior', 'simulado': False, 'proveedores': ['BRAVE_WEB']}]}
            (destino / 'busqueda_integrada_anterior.json').write_text(json.dumps(anterior))
            with patch.object(motor, 'DESTINO', destino):
                resultado = motor.ejecutar_busqueda(PAYLOAD, brave_consultar=lambda *args: {'web': {'results': []}})
            self.assertEqual(resultado['publicaciones'], [])
            self.assertEqual(resultado['historico']['urls_heredadas'], 0)
            self.assertTrue((destino / 'busqueda_integrada_anterior.json').exists())

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

    def test_stages_and_pagination_collect_more_than_twenty(self):
        def proveedor(q, desde, hasta, clave, *, offset=0):
            etapa = 0 if 'Contexto)' in q else 1 if 'Territorio)' in q else 2
            cantidad = 20 if offset == 0 else 1
            return {'query': {'more_results_available': offset == 0}, 'web': {'results': [
                {'url': f'https://example.org/{etapa}/{offset}/{i}', 'title': 'Entidad libre'} for i in range(cantidad)]}}
        with tempfile.TemporaryDirectory() as temporal, patch.object(motor, 'DESTINO', Path(temporal) / 'datos' / 'ejecuciones' / 'brave'):
            resultado = motor.ejecutar_busqueda({**PAYLOAD, 'max_brave': 10, 'paginas_brave': 3}, brave_consultar=proveedor)
        self.assertEqual(resultado['total_urls_unicas'], 63)
        self.assertEqual(resultado['solicitudes_intentadas'], 6)
        self.assertEqual(resultado['consultas_pendientes'], 0)
        self.assertEqual({r['estrategia'] for r in resultado['consultas_ejecutadas']}, {'contexto', 'territorio', 'exploracion'})
        self.assertEqual({r['pagina'] for r in resultado['consultas_ejecutadas']}, {1, 2})
        self.assertEqual(len(resultado['publicaciones_descartadas']), 63)
        for doc in resultado['publicaciones_descartadas']:
            self.assertEqual(doc['fuente_especifica'], 'WEB')
            self.assertEqual(doc['metodo_recuperacion'], 'SNIPPET_BRAVE')
            self.assertTrue(doc['hallazgos_brave'][0]['recuperado_en'])
            self.assertIn('ubicacion_entidad', doc)

    def test_youtube_api_success_skips_html_and_keeps_trace(self):
        vid = 'abcDEF12345'
        respuesta = {'web': {'results': [{'url': f'https://youtu.be/{vid}', 'title': 'Entidad libre', 'description': 'Resumen de Brave'}]}}
        def detalles(ids, clave):
            self.assertEqual(ids, [vid])
            return {vid: {'metricas': {'vistas': 100, 'likes': 2, 'comentarios': None, 'fecha_publicacion': '2025-01-01T00:00:00Z'},
                          'descripcion': 'Contexto Territorio'}}
        with tempfile.TemporaryDirectory() as temporal, patch.object(motor, 'DESTINO', Path(temporal) / 'datos' / 'ejecuciones' / 'brave'):
            resultado = motor.ejecutar_busqueda({**PAYLOAD, 'max_brave': 3}, brave_consultar=lambda *args: respuesta,
                youtube_detalles=detalles, documental_obtener_html=lambda url: self.fail('No debe descargar HTML tras éxito API'))
        doc = resultado['publicaciones'][0]
        self.assertEqual(doc['metricas']['vistas'], 100)
        self.assertEqual(doc['fuente_especifica'], 'YOUTUBE')
        self.assertEqual(doc['metodo_recuperacion'], 'API_OFICIAL')
        self.assertEqual(doc['ubicacion_entidad'], 'TITULO')
        self.assertEqual(doc['descripcion'], 'Resumen de Brave')
        self.assertEqual(doc['cuerpo_extraido'], 'Contexto Territorio')
        self.assertEqual(resultado['recuperacion_documental']['solicitudes_intentadas'], 0)
        self.assertEqual(resultado['youtube_api']['solicitudes_intentadas'], 1)
        self.assertEqual(len(doc['hallazgos_brave']), 3)

    def test_empty_context_and_territory_fall_through_to_exploration(self):
        def proveedor(q, *args):
            return RESPUESTA if q == '"Entidad libre"' else {'web': {'results': []}}
        with tempfile.TemporaryDirectory() as temporal, patch.object(motor, 'DESTINO', Path(temporal) / 'datos' / 'ejecuciones' / 'brave'):
            resultado = motor.ejecutar_busqueda({**PAYLOAD, 'max_brave': 3}, brave_consultar=proveedor)
        self.assertEqual(resultado['total_urls_unicas'], 1)
        self.assertEqual(resultado['solicitudes_intentadas'], 3)
        self.assertEqual(resultado['publicaciones_descartadas'][0]['hallazgos_brave'][0]['estrategia'], 'exploracion')

    def test_backend_sorts_splits_and_preserves_rejected_history(self):
        payload = {**PAYLOAD, 'marco': 'Elemento; Proceso; Zona', 'max_brave': 1, 'max_documentos_enriquecer': None}
        entradas = [('a', 'Elemento', 'Proceso Zona'), ('b', 'Elemento', 'Elemento Proceso Zona'),
                    ('c', 'Elemento', 'Proceso'), ('d', 'Elemento', ''),
                    ('e', 'Tema diferente', 'Elemento Proceso Zona'), ('f', 'Sin relación', 'Texto ajeno')]
        cuerpos = {f'https://example.org/{id}': cuerpo for id, titulo, cuerpo in entradas}
        respuesta = {'web': {'results': [{'url': f'https://example.org/{id}', 'title': titulo} for id, titulo, cuerpo in entradas]}}
        with tempfile.TemporaryDirectory() as temporal, patch.object(motor, 'DESTINO', Path(temporal) / 'datos' / 'ejecuciones' / 'brave'):
            resultado = motor.ejecutar_busqueda(payload, brave_consultar=lambda *args: respuesta,
                documental_obtener_html=lambda url: '<body>' + cuerpos[url] + '</body>')
            snapshot = next(motor.DESTINO.glob('busqueda_integrada_*.json'))
            previo = snapshot.read_bytes()
            repetido = motor.ejecutar_busqueda(payload, brave_consultar=lambda *args: {'web': {'results': []}},
                documental_obtener_html=lambda url: '<body>' + cuerpos[url] + '</body>')
            self.assertEqual(snapshot.read_bytes(), previo)
        self.assertEqual([p['score_emm'] for p in resultado['publicaciones']], [1.0, 0.8, 0.8])
        self.assertEqual([p['score_emm'] for p in resultado['publicaciones_descartadas']], [0.4, 0.2, 0.0])
        self.assertEqual(resultado['total_urls_unicas'], 6)
        self.assertEqual(resultado['total_publicaciones_aceptadas'], 3)
        self.assertEqual(resultado['total_publicaciones_descartadas'], 3)
        self.assertEqual(repetido['historico']['urls_heredadas'], 6)
        self.assertEqual(len(repetido['publicaciones_descartadas']), 3)

    def test_exact_threshold_is_kept_in_main_array(self):
        with tempfile.TemporaryDirectory() as temporal, patch.object(motor, 'DESTINO', Path(temporal) / 'datos' / 'ejecuciones' / 'brave'), patch.object(motor, 'evaluar_publicacion', return_value={'score_emm': 0.5, 'ubicacion_entidad': None}):
            resultado = motor.ejecutar_busqueda(PAYLOAD, brave_consultar=lambda *args: RESPUESTA)
        self.assertEqual(len(resultado['publicaciones']), 1)
        self.assertEqual(resultado['publicaciones'][0]['score_emm'], 0.5)
        self.assertEqual(resultado['publicaciones_descartadas'], [])

    def test_generic_policy_change_reevaluates_existing_inventory(self):
        payload = {**PAYLOAD, 'marco': 'Proyecto Alfa; Diseño; Localidad, Región Amplia', 'max_brave': 1}
        respuesta = {'web': {'results': [{'url': 'https://example.org/politica', 'title': 'Una nota', 'description': 'Proyecto Alfa Diseño Región Amplia'}]}}
        with tempfile.TemporaryDirectory() as temporal, patch.object(motor, 'DESTINO', Path(temporal) / 'datos' / 'ejecuciones' / 'brave'):
            primero = motor.ejecutar_busqueda(payload, brave_consultar=lambda *args: respuesta)
            segundo = motor.ejecutar_busqueda({**payload, 'territorios_genericos': ['Región Amplia']}, brave_consultar=lambda *args: {'web': {'results': []}})
        self.assertEqual(primero['publicaciones'][0]['score_emm'], 0.8)
        self.assertEqual(segundo['historico']['urls_heredadas'], 1)
        self.assertEqual(segundo['publicaciones'], [])
        self.assertEqual(segundo['publicaciones_descartadas'][0]['score_emm'], 0.4)
