import unittest
from app.laboratorio.interfaz_v2.planificador_consultas import construir_consulta


class PlanificadorTests(unittest.TestCase):
    def test_boolean_alternatives_and_dimensions(self):
        self.assertEqual(construir_consulta('Proyecto Nébula Azul, Producto; Diseño modular, experimental; Región Sur, Zona Norte'),
                         '("Proyecto Nébula Azul" OR Producto) AND ("Diseño modular" OR experimental) AND ("Región Sur" OR "Zona Norte")')

    def test_single_alternatives_are_not_natural_language(self):
        self.assertEqual(construir_consulta('Elemento; Proceso; Sector'), '(Elemento) AND (Proceso) AND ("Sector")')

    def test_user_quotes_and_reserved_operators_stay_literal(self):
        consulta = construir_consulta('"Proyecto Azul", OR; NOT, Prueba; Zona')
        self.assertEqual(consulta, '("Proyecto Azul" OR "OR") AND ("NOT" OR Prueba) AND ("Zona")')

    def test_invalid_dimensions(self):
        for marco in ('a;b', 'a;;c', '"";b;c'):
            with self.subTest(marco=marco), self.assertRaises(ValueError):
                construir_consulta(marco)
