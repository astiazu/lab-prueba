"""Consultas derivadas del Marco, sin mezclar contextos mediante OR implícito."""
from app.laboratorio.motor_v2.contratos import Marco, alternativas_contexto


def _literal(valor, *, comillas=False):
    valor = ' '.join(valor.replace('"', ' ').replace('\\', ' ').split())
    if not valor:
        raise ValueError('Una alternativa del Marco quedó vacía')
    if comillas or ' ' in valor or not valor.isalnum() or valor.upper() in ('AND', 'OR', 'NOT'):
        return f'"{valor}"'
    return valor


def planificar_consultas(marco):
    if isinstance(marco, str):
        marco = Marco.desde_input(marco)
    salida, vistos = [], set()
    def agregar(tipo, consulta):
        if consulta not in vistos:
            salida.append((tipo, consulta))
            vistos.add(consulta)
    for contexto in marco.contextos:
        alternativas = alternativas_contexto(contexto)
        grupo = ' OR '.join(_literal(v) for v in alternativas)
        if len(alternativas) > 1:
            grupo = '(' + grupo + ')'
        for entidad in marco.entidades:
            agregar('contexto', f'{_literal(entidad, comillas=True)} AND {grupo}')
    territorios = '(' + ' OR '.join(_literal(v) for v in marco.territorios) + ')'
    for entidad in marco.entidades:
        agregar('territorio', f'{_literal(entidad, comillas=True)} AND {territorios}')
    for entidad in marco.entidades:
        agregar('exploracion', _literal(entidad, comillas=True))
    return salida
