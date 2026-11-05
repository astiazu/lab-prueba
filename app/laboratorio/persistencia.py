"""Ubicación de la futura base de datos SQLite."""

from pathlib import Path

RUTA_BASE_DATOS = Path(__file__).resolve().parents[2] / "datos" / "laboratorio.sqlite3"
