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
    if ruta.is_file():
        valores = dotenv_values(ruta, encoding="utf-8-sig")
        for nombre in ("BRAVE_API_KEY", "BRAVE_SEARCH_API_KEY", "YOUTUBE_API_KEY"):
            if not (os.environ.get(nombre) or "").strip():
                valor = valores.get(nombre)
                if valor and valor.strip():
                    os.environ[nombre] = valor.strip()
    return cargado
