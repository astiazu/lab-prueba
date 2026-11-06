import unittest
from app.laboratorio.motor_v2.contratos import Marco
from app.laboratorio.motor_v2.evaluador_contextual import evaluar_publicacion


class EvaluadorTests(unittest.TestCase):
    def test_score_matrix_and_missing_dimensions(self):
        marco = Marco.desde_input('Entidad Alfa; Contexto Beta; Territorio Gamma')
        casos = [('', 0.0), ('Contexto Beta Territorio Gamma', 0.0),
                 ('Entidad Alfa', 0.3), ('Entidad Alfa Territorio Gamma', 0.3),
                 ('Entidad Alfa Contexto Beta', 0.6),
                 ('Entidad Alfa Contexto Beta Territorio Gamma', 1.0)]
        for texto, esperado in casos:
            with self.subTest(texto=texto):
                resultado = evaluar_publicacion(marco, {'cuerpo_extraido': texto})
                self.assertEqual(resultado['score_emm'], esperado)
                self.assertIn('Falta:', resultado['justificacion'])

    def test_exact_words_casefold_and_string_marco(self):
        resultado = evaluar_publicacion('Organización Delta; Investigación; Región Central', {
            'titulo': 'ORGANIZACIÓN DELTA', 'cuerpo_extraido': 'INVESTIGACIÓN región central'})
        self.assertEqual(resultado['score_emm'], 1.0)
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
        self.assertEqual(resultado['score_emm'], 0.3)

    def test_only_marco_changes_interpretation(self):
        publicacion = {'titulo': 'Materiales Nébula', 'cuerpo_extraido': 'Diseños Delta Región Prisma'}
        completo = Marco.desde_input('Materiales Nébula; Diseños Delta; Región Prisma')
        ajeno = Marco.desde_input('Organización Distinta; Otra Actividad; Otra Ubicación')
        self.assertEqual(evaluar_publicacion(completo, publicacion)['score_emm'], 1.0)
        self.assertEqual(evaluar_publicacion(ajeno, publicacion)['score_emm'], 0.0)
