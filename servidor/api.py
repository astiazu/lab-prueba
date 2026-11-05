"""Transporte HTTP y endpoint inicial de búsqueda."""

import json
from datetime import date
from http.server import SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlsplit

from app.laboratorio.motor import buscar_demo

FRONT = Path(__file__).resolve().parent.parent / "front"
MAX_CUERPO = 1024 * 1024


class ManejadorHTTP(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(FRONT), **kwargs)

    def responder_json(self, estado, contenido):
        cuerpo = json.dumps(contenido, ensure_ascii=False).encode("utf-8")
        self.send_response(estado)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(cuerpo)

    def error_json(self, estado, codigo, mensaje):
        self.responder_json(estado, {"error": {"codigo": codigo, "mensaje": mensaje}})

    def send_error(self, code, message=None, explain=None):
        self.error_json(code, "error_http", message or self.responses.get(code, ("Error HTTP",))[0])

    def do_GET(self):
        if urlsplit(self.path).path.startswith("/api/"):
            self.error_json(405, "metodo_no_permitido", "La API requiere POST /api/buscar.")
            return
        super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path != "/api/buscar":
            self.error_json(404, "ruta_no_encontrada", "La ruta solicitada no existe.")
            return
        if self.headers.get_content_type() != "application/json":
            self.error_json(415, "tipo_no_soportado", "Se requiere application/json.")
            return
        try:
            longitud = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.error_json(400, "longitud_invalida", "Content-Length debe ser un entero.")
            return
        if not 0 < longitud <= MAX_CUERPO:
            self.error_json(413 if longitud > MAX_CUERPO else 400,
                            "cuerpo_invalido", "El cuerpo debe contener entre 1 y 1048576 bytes.")
            return
        try:
            datos = json.loads(self.rfile.read(longitud))
        except (ValueError, UnicodeError):
            self.error_json(400, "json_invalido", "El cuerpo debe ser JSON válido.")
            return
        if not isinstance(datos, dict) or not isinstance(datos.get("marco"), str) or not datos["marco"].strip():
            self.error_json(400, "marco_invalido", "Se requiere un marco de texto no vacío.")
            return
        partes = [parte.strip() for parte in datos["marco"].split(";")]
        if len(partes) != 3 or not all(partes):
            self.error_json(400, "marco_invalido", "Use ENTIDAD ; CONTEXTO ; TERRITORIO.")
            return
        periodo = datos.get("periodo")
        try:
            if not isinstance(periodo, dict):
                raise ValueError
            desde = date.fromisoformat(periodo["desde"])
            hasta = date.fromisoformat(periodo["hasta"])
            if desde > hasta:
                raise ValueError
        except (ValueError, TypeError, KeyError):
            self.error_json(400, "periodo_invalido", "Se requiere periodo con desde y hasta válidos, en orden cronológico.")
            return
        resultado = buscar_demo(datos["marco"].strip(), {"desde": desde.isoformat(), "hasta": hasta.isoformat()})
        self.responder_json(200, resultado)
