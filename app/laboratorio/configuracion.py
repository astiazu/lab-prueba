"""Carga explícita del .env de la raíz, sin exponer sus valores."""
import os
from pathlib import Path

from dotenv import dotenv_values, load_dotenv

RUTA_ENV = Path(__file__).resolve().parents[2] / ".env"


def cargar_entorno(ruta=None):
    ruta = Path(ruta) if ruta is not None else RUTA_ENV
    # utf-8-sig también acepta archivos UTF-8 normales y elimina un posible BOM.
    cargado = load_dotenv(ruta, override=False, encoding="utf-8-sig")
    # dotenv respeta incluso variables vacías. Para Brave, usar el archivo si
    # la variable del proceso existe pero no contiene una clave utilizable.
    if not (os.environ.get("BRAVE_API_KEY") or "").strip() and ruta.is_file():
        valor = dotenv_values(ruta, encoding="utf-8-sig").get("BRAVE_API_KEY")
        if valor and valor.strip():
            os.environ["BRAVE_API_KEY"] = valor.strip()
    return cargado
