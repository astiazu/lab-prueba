import unittest
from app.laboratorio.motor_v2.contratos import Marco
from app.laboratorio.motor_v2.evaluador_contextual import evaluar_publicacion


class EvaluadorTests(unittest.TestCase):
    def test_score_matrix_and_missing_dimensions(self):
        marco = Marco.desde_input('Entidad Alfa; Contexto Beta; Territorio Gamma')
        casos = [('', 0.0), ('Contexto Beta Territorio Gamma', 0.0),
                 ('Entidad Alfa', 0.4), ('Entidad Alfa Territorio Gamma', 0.6),
                 ('Entidad Alfa Contexto Beta', 0.6),
                 ('Entidad Alfa Contexto Beta Territorio Gamma', 0.8)]
        for texto, esperado in casos:
            with self.subTest(texto=texto):
                resultado = evaluar_publicacion(marco, {'cuerpo_extraido': texto})
                self.assertEqual(resultado['score_emm'], esperado)
                self.assertIn('Falta:', resultado['justificacion'])

    def test_exact_words_casefold_and_string_marco(self):
        resultado = evaluar_publicacion('Organización Delta; Investigación; Región Central', {
            'titulo': 'ORGANIZACIÓN DELTA', 'cuerpo_extraido': 'INVESTIGACIÓN región central'})
        self.assertEqual(resultado['score_emm'], 0.8)
        self.assertEqual(resultado['detalles']['entidades']['palabras_encontradas'], ['organización', 'delta'])
        self.assertEqual(resultado['detalles']['territorios']['no_encontrados'], [])
        for titulo in ('Organizaciones Delta', 'Organizacion Delta', 'Organizacióm Delta'):
            with self.subTest(titulo=titulo):
                self.assertEqual(evaluar_publicacion('Organización Delta; Investigación; Región Central', {'titulo': titulo})['score_emm'], 0.0)

    def test_description_is_used_only_via_recovery_fallback(self):
        marco = 'Entidad; Contexto; Territorio'
        self.assertEqual(evaluar_publicacion(marco, {'descripcion': 'Entidad Contexto Territorio'})['score_emm'], 0.0)
        parcial = evaluar_publicacion('Entidad Alfa; Contexto; Territorio', {'titulo': 'Entidad'})
        self.assertEqual(parcial['detalles']['entidades']['palabras_encontradas'], ['entidad'])
        self.assertEqual(parcial['detalles']['entidades']['palabras_no_encontradas'], ['alfa'])

    def test_token_boundaries_full_names_and_alternatives(self):
        marco = Marco.desde_input('Ana Sol, Proyecto Azul; Contexto; Zona')
        self.assertEqual(evaluar_publicacion(marco, {'titulo': 'ventana solar'})['match_entidad'], [])
        self.assertEqual(evaluar_publicacion(marco, {'titulo': 'Ana'})['match_entidad'], [])
        resultado = evaluar_publicacion(marco, {'titulo': 'Proyecto Azul', 'descripcion': None})
        self.assertEqual(resultado['match_entidad'], ['Proyecto Azul'])
        self.assertEqual(resultado['score_emm'], 0.4)

    def test_only_marco_changes_interpretation(self):
        publicacion = {'titulo': 'Materiales Nébula', 'cuerpo_extraido': 'Diseños Delta Región Prisma'}
        completo = Marco.desde_input('Materiales Nébula; Diseños Delta; Región Prisma')
        ajeno = Marco.desde_input('Organización Distinta; Otra Actividad; Otra Ubicación')
        self.assertEqual(evaluar_publicacion(completo, publicacion)['score_emm'], 0.8)
        self.assertEqual(evaluar_publicacion(ajeno, publicacion)['score_emm'], 0.0)

    def test_alternatives_and_partial_entity_without_domain_assumptions(self):
        marco = 'Proyecto Nébula Azul, Producto; Prueba técnica, Diseño modular; Zona Norte, Región Sur'
        resultado = evaluar_publicacion(marco, {'titulo': 'Nébula presenta Azul', 'cuerpo_extraido': 'Diseño modular en Región Sur'})
        self.assertEqual(resultado['score_emm'], 0.8)
        self.assertEqual(resultado['match_contexto'], ['Diseño modular'])
        self.assertEqual(resultado['match_territorio'], ['Región Sur'])
        self.assertEqual(resultado['detalles']['entidades']['evidencia'][0]['metodo'], 'partes_principales')
        self.assertEqual(resultado['detalles']['contextos']['no_encontrados'], ['Prueba técnica'])

    def test_multiple_mentions_only_reach_one_with_all_dimensions(self):
        marco = 'Proyecto Azul; Diseño; Zona Norte'
        for texto, esperado in [('Proyecto Azul Diseño Zona Norte', 0.8),
                                ('Proyecto Azul Proyecto Azul Diseño Zona Norte', 1.0),
                                ('Proyecto Azul Proyecto Azul Diseño', 0.6),
                                ('Proyecto Azul Proyecto Azul', 0.4),
                                ('Proyecto Azul Diseño Diseño Zona Norte', 0.8)]:
            with self.subTest(texto=texto):
                self.assertEqual(evaluar_publicacion(marco, {'cuerpo_extraido': texto})['score_emm'], esperado)

    def test_partial_parts_must_be_near_and_not_single_generic_token(self):
        marco = 'Proyecto Nébula Azul; Diseño; Zona'
        for texto in ('Proyecto', 'Proyecto ' + 'distancia ' * 20 + 'Nébula'):
            self.assertEqual(evaluar_publicacion(marco, {'cuerpo_extraido': texto})['score_emm'], 0.0)

    def test_entity_location_priority_and_description_fallback(self):
        marco = 'Entidad Alfa; Contexto; Territorio'
        for publicacion, esperado in [
            ({'titulo': 'Entidad Alfa', 'cuerpo_extraido': 'Entidad Alfa'}, 'TITULO'),
            ({'titulo': 'Texto', 'cuerpo_extraido': 'Entidad Alfa'}, 'CUERPO'),
            ({'descripcion': 'Entidad Alfa'}, 'DESCRIPCION'),
            ({'cuerpo_extraido': 'Entidad Alfa', 'descripcion': 'Entidad Alfa', 'recuperacion': {'fuente_texto': 'DESCRIPCION_BRAVE'}}, 'DESCRIPCION'),
            ({'titulo': 'Texto diferente'}, None),
        ]:
            with self.subTest(publicacion=publicacion):
                self.assertEqual(evaluar_publicacion(marco, publicacion)['ubicacion_entidad'], esperado)
