"""Carga .env desde la raíz, incluso al ejecutar desde otro directorio."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run
from app.laboratorio import configuracion
from app.laboratorio.interfaz_v2.descubrimiento_brave import clave_brave


class RunTests(unittest.TestCase):
    def test_alias_from_dotenv_and_primary_precedence(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / '.env'
            ruta.write_text('BRAVE_SEARCH_API_KEY=clave-alias-de-prueba\n')
            with patch.dict(os.environ, {'BRAVE_API_KEY': '', 'BRAVE_SEARCH_API_KEY': ''}), patch.object(configuracion, 'RUTA_ENV', ruta):
                self.assertEqual(clave_brave(), 'clave-alias-de-prueba')
                os.environ['BRAVE_API_KEY'] = 'clave-principal-de-prueba'
                self.assertEqual(clave_brave(), 'clave-principal-de-prueba')

    def test_empty_environment_and_bom(self):
        for valor_previo in ('', '   '):
            with self.subTest(vacio=repr(valor_previo)), tempfile.TemporaryDirectory() as temporal:
                ruta = Path(temporal) / '.env'
                ruta.write_text('BRAVE_API_KEY=clave-local-de-prueba\n', encoding='utf-8-sig')
                with patch.dict(os.environ, {'BRAVE_API_KEY': valor_previo}), patch.object(configuracion, 'RUTA_ENV', ruta):
                    self.assertEqual(clave_brave(), 'clave-local-de-prueba')

    def test_file_created_after_startup(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = Path(temporal) / '.env'
            with patch.dict(os.environ, {'BRAVE_API_KEY': ''}), patch.object(configuracion, 'RUTA_ENV', ruta):
                self.assertEqual(clave_brave(), '')
                ruta.write_text('BRAVE_API_KEY=clave-local-de-prueba\n')
                self.assertEqual(clave_brave(), 'clave-local-de-prueba')

    def test_dotenv_path_and_existing_environment(self):
        for valor_previo, esperado in (('', 'clave-local-de-prueba'), ('clave-del-proceso', 'clave-del-proceso')):
            with self.subTest(valor_previo=bool(valor_previo)), tempfile.TemporaryDirectory() as temporal:
                raiz = Path(temporal)
                (raiz / '.env').write_text('BRAVE_API_KEY=clave-local-de-prueba\n')
                with patch.dict(os.environ), patch.object(run, '__file__', str(raiz / 'run.py')), patch.object(run, 'ThreadingHTTPServer') as servidor:
                    if valor_previo:
                        os.environ['BRAVE_API_KEY'] = valor_previo
                    else:
                        os.environ.pop('BRAVE_API_KEY', None)
                    servidor.return_value.serve_forever.side_effect = KeyboardInterrupt
                    run.main()
                    self.assertEqual(os.environ['BRAVE_API_KEY'], esperado)
                    servidor.return_value.server_close.assert_called_once()
