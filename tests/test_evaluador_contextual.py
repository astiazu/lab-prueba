import unittest
from app.laboratorio.motor_v2.contratos import Marco
from app.laboratorio.motor_v2.evaluador_contextual import evaluar_publicacion


class EvaluadorTests(unittest.TestCase):
    def test_new_score_matrix(self):
        marco = 'Entidad Alfa; Contexto Beta; Territorio Gamma'
        casos = [('', 0.0), ('Contexto Beta Territorio Gamma', 0.0),
                 ('Entidad Alfa', 0.2), ('Entidad Alfa Contexto Beta', 0.4),
                 ('Entidad Alfa Territorio Gamma', 0.4),
                 ('Entidad Alfa Contexto Beta Territorio Gamma', 0.8),
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
        self.assertEqual(resultado['score_emm'], 0.8)
        self.assertEqual(resultado['ubicacion_entidad'], 'METADATOS_YOUTUBE_TITULO')
        self.assertEqual(set(resultado['fuentes_texto_evaluadas']), {'TITULO', 'DESCRIPCION', 'CUERPO_EXTRAIDO', 'YOUTUBE_TITULO', 'YOUTUBE_DESCRIPCION'})

    def test_description_is_evaluated_without_fallback(self):
        resultado = evaluar_publicacion('Proyecto Alfa; Diseño; Zona Norte', {'descripcion': 'Proyecto Alfa Diseño Zona Norte'})
        self.assertEqual(resultado['score_emm'], 0.8)
        self.assertEqual(resultado['ubicacion_entidad'], 'DESCRIPCION')

    def test_no_title_or_first_500_penalty(self):
        resultado = evaluar_publicacion('Proyecto Alfa; Diseño; Zona Norte', {
            'titulo': 'Una nota real', 'cuerpo_extraido': 'x' * 600 + ' Proyecto Alfa Diseño Zona Norte'})
        self.assertEqual(resultado['score_emm'], 0.8)
        self.assertEqual(resultado['penalizaciones'], [])

    def test_primary_entity_required_and_not_partial_or_homonymous(self):
        marco = 'Proyecto Alfa, Producto; Diseño; Zona Norte'
        for texto in ('Proyecto Beta Diseño Zona Norte', 'Producto Diseño Zona Norte', 'Alfa Diseño Zona Norte'):
            self.assertEqual(evaluar_publicacion(marco, {'cuerpo_extraido': texto})['score_emm'], 0.0)
        self.assertEqual(evaluar_publicacion(marco, {'titulo': 'PROYECTO ALFA', 'descripcion': 'Diseño Zona Norte'})['score_emm'], 0.8)

    def test_alternative_context_or_territory_is_enough_for_cooccurrence(self):
        resultado = evaluar_publicacion('Proyecto Alfa; Diseño, Investigación; Zona Norte, Zona Sur', {'titulo': 'Proyecto Alfa', 'descripcion': 'Investigación Zona Sur'})
        self.assertEqual(resultado['score_emm'], 0.8)
        self.assertEqual(resultado['match_contexto'], ['Investigación'])
        self.assertEqual(resultado['match_territorio'], ['Zona Sur'])
        self.assertTrue(resultado['coocurrencia'])

    def test_generic_territory_is_explicit_and_specific_can_be_one_word(self):
        marco = Marco.desde_input('Proyecto Alfa; Diseño; Localidad, Región Amplia', territorios_genericos=['REGIÓN AMPLIA'])
        generico = evaluar_publicacion(marco, {'titulo': 'Proyecto Alfa', 'descripcion': 'Diseño Región Amplia'})
        self.assertEqual(generico['score_base'], 0.8)
        self.assertEqual(generico['score_emm'], 0.4)
        self.assertEqual(generico['penalizaciones'][0]['codigo'], 'solo_territorio_generico')
        especifico = evaluar_publicacion(marco, {'titulo': 'Proyecto Alfa', 'descripcion': 'Diseño Localidad'})
        self.assertEqual(especifico['score_emm'], 0.8)
        self.assertEqual(especifico['detalles']['territorios']['especificos_encontrados'], ['Localidad'])

    def test_no_generic_inference_without_configuration(self):
        resultado = evaluar_publicacion('Proyecto Alfa; Diseño; Localidad, Región Amplia', {'titulo': 'Proyecto Alfa', 'descripcion': 'Diseño Región Amplia'})
        self.assertEqual(resultado['score_emm'], 0.8)
        self.assertEqual(resultado['detalles']['territorios']['genericos'], [])

    def test_copied_descriptions_do_not_inflate_density(self):
        texto = 'Proyecto Alfa Diseño Zona Norte'
        resultado = evaluar_publicacion('Proyecto Alfa; Diseño; Zona Norte', {
            'descripcion': texto, 'cuerpo_extraido': texto, 'metadatos_youtube': {'descripcion': texto}})
        self.assertEqual(resultado['score_emm'], 0.8)
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
