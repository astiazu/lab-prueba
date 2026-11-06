"""Punto de entrada del servidor local del laboratorio EMM."""

import logging
from http.server import ThreadingHTTPServer
from pathlib import Path

from app.laboratorio.configuracion import cargar_entorno

from servidor.api import ManejadorHTTP


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    cargar_entorno(Path(__file__).resolve().parent / ".env")
    servidor = ThreadingHTTPServer(("127.0.0.1", 8765), ManejadorHTTP)
    print("Laboratorio EMM disponible en http://127.0.0.1:8765", flush=True)
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
