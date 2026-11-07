import unittest
from app.laboratorio.interfaz_v2.planificador_consultas import planificar_consultas


class PlanificadorTests(unittest.TestCase):
    def test_contexts_are_separate_queries(self):
        plan = planificar_consultas('Elemento Alfa; Proceso, Diseño; Sector, Región')
        contextos = [q for tipo, q in plan if tipo == 'contexto']
        self.assertEqual(contextos, ['"Elemento Alfa" AND Proceso', '"Elemento Alfa" AND Diseño'])
        self.assertTrue(all(' OR ' not in q for q in contextos))
        self.assertIn(('territorio', '"Elemento Alfa" AND (Sector OR Región)'), plan)
        self.assertIn(('exploracion', '"Elemento Alfa"'), plan)

    def test_explicit_or_is_respected(self):
        self.assertEqual(planificar_consultas('Elemento; Proceso OR Diseño; Sector')[0], ('contexto', '"Elemento" AND (Proceso OR Diseño)'))

    def test_quotes_reserved_words_and_invalid_input(self):
        self.assertEqual(planificar_consultas('"Elemento Alfa"; NOT; Sector')[0][1], '"Elemento Alfa" AND "NOT"')
        for marco in ('a;b', 'a;;c', '"";b;c'):
            with self.subTest(marco=marco), self.assertRaises(ValueError):
                planificar_consultas(marco)
