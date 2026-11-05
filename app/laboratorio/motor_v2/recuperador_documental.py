"""Sustituto local de recuperación: nunca descarga documentos de Internet."""
from app.laboratorio.interfaz_v2.stubs import obtener_html


def descargar_html(url):
    return obtener_html(url)
