import unittest
from app.laboratorio.motor_v2.contratos import Marco
from app.laboratorio.motor_v2.evaluador_contextual import evaluar_publicacion


class EvaluadorTests(unittest.TestCase):
    def test_new_score_matrix(self):
        marco = 'Entidad Alfa; Contexto Beta; Territorio Gamma'
        casos = [('', 0.0), ('Contexto Beta', 0.3), ('Territorio Gamma', 0.3), ('Contexto Beta Territorio Gamma', 0.6),
                 ('Entidad Alfa', 0.4), ('Entidad Alfa Contexto Beta', 0.7),
                 ('Entidad Alfa Territorio Gamma', 0.7),
                 ('Entidad Alfa Contexto Beta Territorio Gamma', 1.0),
                 ('Entidad Alfa Entidad Alfa Contexto Beta Territorio Gamma', 1.0)]
        for texto, esperado in casos:
            with self.subTest(texto=texto):
                resultado = evaluar_publicacion(marco, {'cuerpo_extraido': texto})
                self.assertEqual(resultado['score_emm'], esperado)
                self.assertEqual(resultado['penalizaciones'], [])

    def test_all_sources_contribute_to_supertext(self):
        marco = 'Proyecto Alfa; Diseño modular; Zona Norte'
        resultado = evaluar_publicacion(marco, {
            'titulo': 'Una nota', 'descripcion': 'Zona Norte', 'cuerpo_extraido': 'Información adicional',
            'metadatos_youtube': {'titulo': 'Proyecto Alfa', 'descripcion': 'Diseño modular'}})
        self.assertEqual(resultado['score_emm'], 1.0)
        self.assertEqual(resultado['ubicacion_entidad'], 'METADATOS_YOUTUBE_TITULO')
        self.assertEqual(set(resultado['fuentes_texto_evaluadas']), {'TITULO', 'DESCRIPCION', 'CUERPO_EXTRAIDO', 'YOUTUBE_TITULO', 'YOUTUBE_DESCRIPCION'})

    def test_description_is_evaluated_without_fallback(self):
        resultado = evaluar_publicacion('Proyecto Alfa; Diseño; Zona Norte', {'descripcion': 'Proyecto Alfa Diseño Zona Norte'})
        self.assertEqual(resultado['score_emm'], 1.0)
        self.assertEqual(resultado['ubicacion_entidad'], 'DESCRIPCION')

    def test_no_title_or_first_500_penalty(self):
        resultado = evaluar_publicacion('Proyecto Alfa; Diseño; Zona Norte', {
            'titulo': 'Una nota real', 'cuerpo_extraido': 'x' * 600 + ' Proyecto Alfa Diseño Zona Norte'})
        self.assertEqual(resultado['score_emm'], 1.0)
        self.assertEqual(resultado['penalizaciones'], [])

    def test_any_entity_contributes_without_mandatory_primary(self):
        marco = 'Proyecto Alfa, Producto; Diseño; Zona Norte'
        for texto, esperado in [('Proyecto Beta Diseño Zona Norte', 0.6),
                                ('Producto Diseño Zona Norte', 1.0), ('Alfa Diseño Zona Norte', 0.6)]:
            with self.subTest(texto=texto):
                self.assertEqual(evaluar_publicacion(marco, {'cuerpo_extraido': texto})['score_emm'], esperado)
        resultado = evaluar_publicacion(marco, {'titulo': 'Producto', 'descripcion': 'Diseño Zona Norte'})
        self.assertEqual(resultado['score_emm'], 1.0)
        self.assertFalse(resultado['entidad_principal_presente'])
        self.assertEqual(resultado['match_entidad'], ['Producto'])

    def test_alternative_context_or_territory_is_enough_for_cooccurrence(self):
        resultado = evaluar_publicacion('Proyecto Alfa; Diseño, Investigación; Zona Norte, Zona Sur', {'titulo': 'Proyecto Alfa', 'descripcion': 'Investigación Zona Sur'})
        self.assertEqual(resultado['score_emm'], 1.0)
        self.assertEqual(resultado['match_contexto'], ['Investigación'])
        self.assertEqual(resultado['match_territorio'], ['Zona Sur'])
        self.assertTrue(resultado['coocurrencia'])

    def test_specific_territory_implies_declared_general_territory(self):
        marco = Marco.desde_input('Proyecto Alfa; Diseño; Localidad, Región Amplia', territorios_genericos=['REGIÓN AMPLIA'])
        resultado = evaluar_publicacion(marco, {'titulo': 'Proyecto Alfa', 'descripcion': 'Diseño Localidad'})
        self.assertEqual(resultado['score_emm'], 1.0)
        self.assertEqual(resultado['componentes_score']['territorio'], 0.3)
        self.assertEqual(resultado['match_territorio'], ['Localidad', 'Región Amplia'])
        detalle = resultado['detalles']['territorios']
        self.assertEqual(detalle['encontrados_textuales'], ['Localidad'])
        self.assertEqual(detalle['inferidos'], ['Región Amplia'])
        self.assertEqual(detalle['evidencia'][1]['metodo'], 'inferencia_por_territorio_especifico')
        self.assertEqual(detalle['evidencia'][1]['menciones'], 0)
        self.assertIn('región', detalle['palabras_no_encontradas'])
        solo_general = evaluar_publicacion(marco, {'titulo': 'Proyecto Alfa', 'descripcion': 'Diseño Región Amplia'})
        self.assertEqual(solo_general['score_emm'], 1.0)
        self.assertEqual(solo_general['detalles']['territorios']['inferidos'], [])

    def test_no_generic_inference_without_configuration(self):
        resultado = evaluar_publicacion('Proyecto Alfa; Diseño; Localidad, Región Amplia', {'titulo': 'Proyecto Alfa', 'descripcion': 'Diseño Región Amplia'})
        self.assertEqual(resultado['score_emm'], 1.0)
        self.assertEqual(resultado['detalles']['territorios']['genericos'], [])

    def test_copied_descriptions_do_not_inflate_density(self):
        texto = 'Proyecto Alfa Diseño Zona Norte'
        resultado = evaluar_publicacion('Proyecto Alfa; Diseño; Zona Norte', {
            'descripcion': texto, 'cuerpo_extraido': texto, 'metadatos_youtube': {'descripcion': texto}})
        self.assertEqual(resultado['score_emm'], 1.0)
        self.assertEqual(resultado['detalles']['entidades']['menciones_principal'], 1)

    def test_invalid_metadata_and_generic_configuration(self):
        self.assertEqual(evaluar_publicacion('Elemento; Proceso; Zona', {'metadatos_youtube': None, 'descripcion': 3})['score_emm'], 0.0)
        for genericos in ('Zona', ['No pertenece'], [3]):
            with self.subTest(genericos=genericos), self.assertRaises(ValueError):
                Marco.desde_input('Elemento; Proceso; Zona', territorios_genericos=genericos)

    def test_location_keeps_snippet_provenance(self):
        resultado = evaluar_publicacion('Proyecto Alfa; Diseño; Zona', {'descripcion': 'Proyecto Alfa Diseño Zona',
            'cuerpo_extraido': 'Proyecto Alfa Diseño Zona', 'recuperacion': {'fuente_texto': 'DESCRIPCION_BRAVE'}})
        self.assertEqual(resultado['ubicacion_entidad'], 'DESCRIPCION')
        self.assertNotIn('CUERPO', resultado['ubicaciones_entidad'])

    def test_alternatives_and_repetitions_do_not_add_points_per_word(self):
        resultado = evaluar_publicacion('Elemento, Producto; Proceso, Diseño; Zona, Región', {
            'titulo': 'Elemento Producto', 'descripcion': 'Proceso Diseño Zona Región',
            'cuerpo_extraido': 'Elemento Producto Elemento Producto Proceso Diseño Zona Región'})
        self.assertEqual(resultado['score_emm'], 1.0)
        self.assertEqual(resultado['componentes_score'], {'entidad': 0.4, 'contexto': 0.3, 'territorio': 0.3})
        self.assertEqual(evaluar_publicacion('Elemento; Proceso; Zona', {'titulo': 'Elemento Elemento', 'cuerpo_extraido': 'Elemento'})['score_emm'], 0.4)

    def test_inference_is_not_reversed_or_applied_outside_marco(self):
        marco = Marco.desde_input('Elemento; Proceso; Localidad, Región Amplia, País', territorios_genericos=['Región Amplia', 'País'])
        resultado = evaluar_publicacion(marco, {'descripcion': 'Localidad'})
        self.assertEqual(resultado['score_emm'], 0.3)
        self.assertEqual(resultado['detalles']['territorios']['inferidos'], ['Región Amplia', 'País'])
        inverso = evaluar_publicacion(marco, {'descripcion': 'País'})
        self.assertEqual(inverso['match_territorio'], ['País'])
        self.assertEqual(inverso['detalles']['territorios']['inferidos'], [])
