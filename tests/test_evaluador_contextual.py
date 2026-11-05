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

    def test_normalization_roots_similarity_and_all_fields(self):
        marco = Marco.desde_input('Organización Delta; Investigación; Región Central')
        publicacion = {'titulo': 'ORGANIZACIONES DELTA', 'descripcion': 'Investigacion',
                       'cuerpo_extraido': 'region central'}
        resultado = evaluar_publicacion(marco, publicacion)
        self.assertEqual(resultado['score_emm'], 1.0)
        self.assertEqual(resultado['match_entidad'], ['Organización Delta'])
        marco = Marco.desde_input('Laboratorio; Exploración; Territorio')
        self.assertEqual(evaluar_publicacion(marco, {'titulo': 'Laboratprio'})['score_emm'], 0.3)

    def test_token_boundaries_full_names_and_alternatives(self):
        marco = Marco.desde_input('Ana Sol, Proyecto Azul; Contexto; Zona')
        self.assertEqual(evaluar_publicacion(marco, {'titulo': 'ventana solar'})['match_entidad'], [])
        self.assertEqual(evaluar_publicacion(marco, {'titulo': 'Ana'})['match_entidad'], [])
        resultado = evaluar_publicacion(marco, {'titulo': 'Proyecto Azul', 'descripcion': None})
        self.assertEqual(resultado['match_entidad'], ['Proyecto Azul'])
        self.assertEqual(resultado['score_emm'], 0.3)

    def test_only_marco_changes_interpretation(self):
        publicacion = {'titulo': 'Materiales Nébula', 'descripcion': 'Diseños Delta', 'cuerpo_extraido': 'Región Prisma'}
        completo = Marco.desde_input('Materiales Nébula; Diseños Delta; Región Prisma')
        ajeno = Marco.desde_input('Organización Distinta; Otra Actividad; Otra Ubicación')
        self.assertEqual(evaluar_publicacion(completo, publicacion)['score_emm'], 1.0)
        self.assertEqual(evaluar_publicacion(ajeno, publicacion)['score_emm'], 0.0)
