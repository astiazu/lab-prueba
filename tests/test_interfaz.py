import inspect
from pathlib import Path
import unittest
from app.laboratorio.motor_v2.contratos import Marco


class InterfazTests(unittest.TestCase):
    def test_removed_input_not_in_schema_or_ui(self):
        raiz = Path(__file__).resolve().parents[1]
        retirado = '_'.join(('territorios', 'genericos'))
        etiqueta = 'Territorios' + ' ' + 'genéricos'
        self.assertEqual(set(Marco.__dataclass_fields__), {'entidades', 'contextos', 'territorios'})
        self.assertNotIn(retirado, inspect.signature(Marco.desde_input).parameters)
        for ruta in ('front/index.html', 'front/busqueda.js', 'app/laboratorio/interfaz_v2/descubrimiento_integrado.py'):
            contenido = (raiz / ruta).read_text()
            self.assertNotIn(retirado, contenido)
            self.assertNotIn(etiqueta, contenido)
