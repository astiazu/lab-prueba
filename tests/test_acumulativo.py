import unittest
from unittest.mock import patch
from app.laboratorio.motor_v2.acumulativo import Inventario, cerrar_corrida
from app.laboratorio.motor_v2.contratos import Marco
from app.laboratorio.motor_v2.politica_emm import PoliticaEMM


class AcumulativoTests(unittest.TestCase):
    def test_two_runs_keep_archive_cold_and_exclude_it_from_denominator(self):
        marco, politica = Marco.desde_input('Elemento; Proceso; Zona'), PoliticaEMM()
        textos = {'aceptada': 'Elemento Proceso Zona', 'activa': 'Elemento', 'fria': 'Contenido ajeno', 'limite': 'Proceso'}
        inv = Inventario(activas={f'https://example.org/{k}': {'url': f'https://example.org/{k}', 'titulo': v, 'origen': 'example.org'} for k, v in textos.items()})
        inv.nuevas = set(inv.activas)
        primero = cerrar_corrida(inv, list(inv.activas.values()), marco, politica, {})
        frias = {p['url'] for p in primero['publicaciones_archivadas']}
        activos_anteriores = primero['publicaciones'] + primero['publicaciones_descartadas']
        segundo_inv = Inventario.desde_salida(primero)
        nueva = 'https://example.org/nueva'
        segundo_inv.activas[nueva] = {'url': nueva, 'titulo': 'Zona', 'origen': 'example.org'}
        segundo_inv.nuevas.add(nueva)
        from app.laboratorio.motor_v2 import acumulativo
        with patch.object(acumulativo, 'evaluar_publicacion', wraps=acumulativo.evaluar_publicacion) as evaluar:
            segundo = cerrar_corrida(segundo_inv, list(segundo_inv.activas.values()), marco, politica, {})
        self.assertTrue(all(c.args[1]['url'] not in frias for c in evaluar.call_args_list))
        self.assertEqual(segundo['urls_heredadas_archivadas'], len(frias))
        self.assertEqual(segundo['total_urls_activas'], len(activos_anteriores) + segundo['urls_nuevas_activas'])
        self.assertEqual(segundo['total_urls_activas'], segundo['urls_nuevas_activas'] + segundo['urls_heredadas_activas_al_cierre'])
        self.assertAlmostEqual(segundo['ratio_aceptadas_activas'], len(segundo['publicaciones']) / segundo['total_urls_activas'])
        self.assertTrue(all(p['score_emm'] < politica.umbral_archivado for p in primero['publicaciones_archivadas']))
        limite = next(p for p in primero['publicaciones_descartadas'] if p['url'].endswith('/limite'))
        self.assertLess(abs(limite['score_emm'] - politica.umbral_archivado), 1e-9)
        self.assertFalse(limite['archivado'])
        self.assertEqual(primero['publicaciones_archivadas'], segundo['publicaciones_archivadas'])

    def test_empty_denominator_is_null_and_never_archives_accepted(self):
        marco, politica = Marco.desde_input('Elemento; Proceso; Zona'), PoliticaEMM()
        inv = Inventario(activas={'https://example.org/a': {'url': 'https://example.org/a', 'titulo': 'Ajeno'}})
        salida = cerrar_corrida(inv, list(inv.activas.values()), marco, politica, {})
        self.assertEqual(salida['total_urls_activas'], 0)
        self.assertIsNone(salida['ratio_aceptadas_activas'])
        self.assertTrue(salida['publicaciones_archivadas'])

    def test_configurable_thresholds_and_real_marginal_categories(self):
        marco = Marco.desde_input('Elemento; Proceso; Zona')
        politica = PoliticaEMM.desde_config({'umbral_archivado': 0.4})
        docs = [{'url': f'https://example.org/{i}', 'titulo': texto, 'origen': 'example.org'} for i, texto in enumerate(('Elemento Proceso Zona', 'Elemento Proceso', 'Elemento', 'Proceso'))]
        salida = cerrar_corrida(Inventario(), docs, marco, politica, {})
        self.assertTrue(all(p['score_emm'] < politica.umbral_archivado for p in salida['publicaciones_archivadas']))
        self.assertTrue(all(p['score_emm'] >= politica.umbral_archivado for p in salida['publicaciones_descartadas']))
        self.assertTrue(all(not p['archivado'] for p in salida['publicaciones']))
        self.assertEqual(salida['aceptadas_reales'], sum(p['score_emm'] >= politica.umbral_real for p in salida['publicaciones']))
        self.assertEqual(salida['aceptadas_marginales'], sum(politica.umbral_aceptacion <= p['score_emm'] < politica.umbral_real for p in salida['publicaciones']))
