"""Datos deterministas locales. No contiene clientes HTTP ni consulta credenciales."""
from hashlib import sha256
from html import escape
from urllib.parse import urlsplit


def resultados_web(consulta, desde='2000-01-01'):
    # Una identidad estable por entidad permite probar la consolidación entre consultas.
    entidad = consulta.split('"')[1] if '"' in consulta else consulta
    identidad = sha256(entidad.encode()).hexdigest()[:16]
    return [
        {'url': f'https://example.com/emm-local/{identidad}/{i}',
         'title': f'[SIMULADO] Documento {i}: {entidad}',
         'description': f'Dato local de prueba para la consulta: {consulta}',
         'page_age': desde}
        for i in (1, 2)
    ]


def obtener_html(url):
    partes = urlsplit(url)
    if partes.hostname != 'example.com' or not partes.path.startswith('/emm-local/'):
        raise ValueError('El recuperador local solo acepta documentos de prueba')
    return f'<html><head><title>[SIMULADO] Documento local</title></head><body><p>Contenido ficticio para {escape(url)}.</p></body></html>'
