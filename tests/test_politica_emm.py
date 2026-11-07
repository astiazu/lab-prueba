import unittest
from app.laboratorio.motor_v2.contratos import Marco
from app.laboratorio.motor_v2.evaluador_contextual import evaluar_publicacion
from app.laboratorio.motor_v2.politica_emm import PoliticaEMM, peso_territorio


class PoliticaTests(unittest.TestCase):
    def test_approved_tables_and_maximum_for_n_one_through_four(self):
        tablas = {1: [0.30], 2: [0.30, 0.15], 3: [0.30, 0.20, 0.10], 4: [0.30, 0.225, 0.15, 0.075]}
        for n, esperados in tablas.items():
            marco = Marco.desde_input('Elemento; Proceso; ' + ', '.join(f'Nivel{i}' for i in range(n)))
            with self.subTest(n=n):
                for t, esperado in zip(marco.territorios, esperados):
                    self.assertLess(abs(peso_territorio(t, marco) - esperado), 1e-9)
                resultado = evaluar_publicacion(marco, {'titulo': 'Elemento Proceso Nivel0'})
                self.assertLess(abs(resultado['score_emm'] - 1.0), 1e-9)

    def test_invariant_and_strict_order_for_many_frame_sizes(self):
        for n in range(1, 21):
            marco = Marco.desde_input('Elemento; Proceso; ' + ', '.join(f'Nivel{i}' for i in range(n)))
            pesos = [peso_territorio(t, marco) for t in marco.territorios]
            self.assertLess(abs(pesos[0] - PoliticaEMM().peso_territorio), 1e-9)
            self.assertTrue(all(a > b for a, b in zip(pesos, pesos[1:])))

    def test_two_frames_order_and_custom_budget(self):
        for texto in ('Elemento; Proceso; Área Local, Región', 'Producto; Diseño; Sector, Área, Zona Amplia'):
            marco = Marco.desde_input(texto)
            pesos = [peso_territorio(t, marco) for t in marco.territorios]
            self.assertGreater(pesos[0], pesos[-1])
        politica = PoliticaEMM.desde_config({'peso_entidad': 0.5, 'peso_contexto': 0.3, 'peso_territorio': 0.2})
        self.assertLess(abs(peso_territorio('Sector', Marco.desde_input('Elemento; Proceso; Sector, Región'), politica) - politica.peso_territorio), 1e-9)

    def test_invalid_configuration(self):
        for config in ({'umbral_archivado': 0.7}, {'score_max_sin_entidad': 0.8}, {'peso_entidad': 0.9}, {'umbral_real': float('nan')}, {'umbral_real': True}, {'desconocido': 1}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                PoliticaEMM.desde_config(config)
