import unittest
from dataclasses import replace
from app.laboratorio.motor_v2.contratos import Marco
from app.laboratorio.motor_v2.evaluador_contextual import evaluar_publicacion
from app.laboratorio.motor_v2.politica_emm import PoliticaEMM, SCORE_MAX_SIN_ENTIDAD


class EvaluadorTests(unittest.TestCase):
    def test_three_identity_confusions_in_different_contexts_are_capped(self):
        for contexto, otra in [('Actividad Alfa', 'Identidad Beta'), ('Actividad Beta', 'Identidad Gamma'), ('Actividad Gamma', 'Identidad Delta')]:
            resultado = evaluar_publicacion(f'Identidad Alfa; {contexto}; Zona', {'titulo': otra, 'descripcion': f'{contexto} Zona'})
            self.assertFalse(resultado['entidad_principal_presente'])
            self.assertLess(abs(resultado['score_emm'] - SCORE_MAX_SIN_ENTIDAD), 1e-9)
            self.assertEqual(resultado['motivo_descarte'], 'sin_entidad_principal')
        politica = replace(PoliticaEMM(), score_max_sin_entidad=0.25)
        resultado = evaluar_publicacion('Elemento; Proceso; Zona', {'descripcion': 'Proceso Zona'}, politica)
        self.assertLess(abs(resultado['score_emm'] - politica.score_max_sin_entidad), 1e-9)

    def test_penalty_keys_preserve_ascii_contract(self):
        resultado = evaluar_publicacion('Elemento; Proceso; Zona', {'titulo': 'Proceso Zona'})
        self.assertTrue(resultado['penalizaciones'])
        for penalizacion in resultado['penalizaciones']:
            self.assertIn('codigo', penalizacion)
            self.assertNotIn('código', penalizacion)

    def test_document_order_does_not_control_best_territory_and_no_sum(self):
        marco = 'Elemento; Proceso; Sector Local, Área, Región, Zona Amplia'
        doc = {'titulo': 'Elemento', 'descripcion': 'Zona Amplia, Región, Sector Local, Proceso'}
        resultado = evaluar_publicacion(marco, doc)
        self.assertEqual(resultado['detalles']['territorios']['mejor_match'], 'Sector Local')
        self.assertLess(abs(resultado['componentes_score']['territorio'] - PoliticaEMM().peso_territorio), 1e-9)
        self.assertLess(abs(resultado['score_emm'] - 1.0), 1e-9)
        simple = evaluar_publicacion(marco, {'descripcion': 'Elemento Proceso Sector Local'})
        self.assertLess(abs(simple['score_emm'] - resultado['score_emm']), 1e-9)

    def test_marginal_without_territory_is_supported(self):
        resultado = evaluar_publicacion('Elemento; Proceso; Zona', {'descripcion': 'Elemento Proceso'})
        self.assertLess(abs(resultado['score_emm'] - 0.7), 1e-9)
        self.assertIsNone(resultado['motivo_descarte'])

    def test_supertext_sources_and_no_title_requirement(self):
        resultado = evaluar_publicacion('Elemento; Proceso; Zona', {'titulo': 'Otra nota', 'descripcion': 'Zona',
            'cuerpo_extraido': 'Contenido', 'metadatos_youtube': {'titulo': 'Elemento', 'descripcion': 'Proceso'}})
        self.assertLess(abs(resultado['score_emm'] - 1.0), 1e-9)
        self.assertEqual(resultado['ubicacion_entidad'], 'METADATOS_YOUTUBE_TITULO')

    def test_categorical_rejection_reasons(self):
        marco = 'Elemento; Proceso; Sector, Región'
        casos = [({'titulo': 'Proceso Sector'}, PoliticaEMM(), 'sin_entidad_principal'),
                 ({'titulo': 'Elemento'}, PoliticaEMM(), 'entidad_homonima'),
                 ({'titulo': 'Elemento Proceso'}, replace(PoliticaEMM(), umbral_aceptacion=0.8), 'territorio_incorrecto'),
                 ({'titulo': 'Elemento Proceso Región'}, replace(PoliticaEMM(), umbral_aceptacion=0.9, umbral_real=0.9), 'score_bajo')]
        for publicacion, politica, motivo in casos:
            self.assertEqual(evaluar_publicacion(marco, publicacion, politica)['motivo_descarte'], motivo)

    def test_no_identity_created_from_field_boundary_or_other_alternative(self):
        marco = 'Entidad Alfa, Producto; Proceso; Zona'
        for doc in ({'titulo': 'Entidad', 'descripcion': 'Alfa Proceso Zona'}, {'titulo': 'Producto Proceso Zona'}):
            resultado = evaluar_publicacion(marco, doc)
            self.assertFalse(resultado['entidad_principal_presente'])
            self.assertLessEqual(resultado['score_emm'], SCORE_MAX_SIN_ENTIDAD)

    def test_explicit_context_disjunction(self):
        resultado = evaluar_publicacion('Elemento; Proceso OR Diseño; Zona', {'titulo': 'Elemento Diseño Zona'})
        self.assertLess(abs(resultado['score_emm'] - 1.0), 1e-9)
        self.assertEqual(resultado['detalles']['contextos']['evidencia'][0]['alternativas_encontradas'], ['Diseño'])

    def test_textual_territory_matches_are_not_inferred(self):
        resultado = evaluar_publicacion('Elemento; Proceso; Sector, Región', {'titulo': 'Elemento Proceso Sector'})
        self.assertEqual(resultado['match_territorio'], ['Sector'])
        self.assertEqual(resultado['detalles']['territorios']['no_encontrados'], ['Región'])
