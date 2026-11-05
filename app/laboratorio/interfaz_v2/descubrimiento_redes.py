"""Compatibilidad local de redes; no implementa el adaptador original no adjunto."""


def identidad(url, red):
    # Los documentos example.com del stub no son evidencias de redes sociales.
    return None


def descubrir(marco, red, presupuesto, consultar, desde, hasta, clave, consultas_previas):
    # Ejecuta el proveedor inyectado y registra la auditoría, sin inventar identidades sociales.
    consultas, brutas, errores = [], [], []
    propuestas = [f'"{e}" site:{red.lower()}.com' for e in marco.entidades]
    omitidas = sum(q in consultas_previas for q in propuestas)
    seleccion = [q for q in propuestas if q not in consultas_previas][:presupuesto]
    for q in seleccion:
        try:
            data = consultar(q, desde, hasta, clave)
            brutas.append({'consulta': q, 'respuesta': data, 'modo': 'STUB_LOCAL'})
            consultas.append({'proveedor': f'{red}_INDEXADO_BRAVE', 'estrategia': 'stub_local',
                             'consulta': q, 'pagina': 1, 'resultados': 0, 'nuevas_urls': 0,
                             'fuera_de_dominio': len((data.get('web') or {}).get('results') or [])})
        except Exception as exc:
            errores.append({'proveedor': f'{red}_INDEXADO_BRAVE', 'error': str(exc)})
    return {'respuestas_brutas': brutas, 'hallazgos': [], 'consultas': consultas,
            'errores': errores, 'intentadas': len(seleccion), 'planificadas': len(propuestas),
            'omitidas_ya_ejecutadas': omitidas, 'ejecutadas': len(consultas), 'fallidas': len(errores),
            'pendientes': max(0, len(propuestas) - omitidas - len(seleccion)),
            'auditoria_truncada': False, 'publicaciones_o_enlaces': 0, 'perfiles': 0}
