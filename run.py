"""Punto de entrada del servidor local del laboratorio EMM."""

from http.server import ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv

from servidor.api import ManejadorHTTP


def main():
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
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
