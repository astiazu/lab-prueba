"""Carga .env desde la raíz, incluso al ejecutar desde otro directorio."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run


class RunTests(unittest.TestCase):
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
