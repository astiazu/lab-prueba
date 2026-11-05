"""Interfaz del futuro motor universal de descubrimiento."""


def buscar(consulta: str) -> dict:
    """Ejecutar una consulta cuando se implemente el motor."""
    raise NotImplementedError("Motor de descubrimiento pendiente")


def buscar_demo(marco: str, periodo: dict) -> dict:
    """Crear datos ficticios para probar la interfaz, sin consultas externas."""
    entidad, contexto, territorio = [parte.strip() for parte in marco.split(";")]
    publicaciones = [
        {
            "titulo": f"[SIMULADO] {titulo}: {entidad}",
            "url": f"https://example.com/publicacion-demo-{numero}",
            "origen": "Demo local",
            "fecha": periodo["desde"],
            "resumen": f"Publicación ficticia sobre {entidad}, en el contexto {contexto}, territorio {territorio}.",
        }
        for numero, titulo in enumerate(("Presentación", "Entrevista", "Actividad"), start=1)
    ]
    return {
        "total_urls_unicas": len(publicaciones),
        "solicitudes_exitosas": 0,
        "origenes": ["Demo local"],
        "publicaciones": publicaciones,
        "errores": [],
        "avisos": ["No se realizaron solicitudes a Brave ni a DDG."],
        "advertencia": "MODO DEMO: todas las publicaciones son ficticias y sus enlaces son ejemplos.",
        "periodo": periodo,
    }
