"""Construcción booleana agnóstica: alternativas OR, dimensiones AND."""
from app.laboratorio.motor_v2.contratos import Marco


def _literal(valor, *, comillas=False):
    # Las comillas del usuario no pueden cerrar las de la expresión generada.
    valor = ' '.join(valor.replace('"', ' ').replace('\\', ' ').split())
    if not valor:
        raise ValueError('Una alternativa del Marco quedó vacía')
    if comillas or ' ' in valor or not valor.isalnum() or valor.upper() in ('AND', 'OR', 'NOT'):
        return f'"{valor}"'
    return valor


def construir_consulta(marco):
    if isinstance(marco, str):
        marco = Marco.desde_input(marco)
    grupos = []
    for valores, comillas in ((marco.entidades, False), (marco.contextos, False), (marco.territorios, True)):
        if not valores:
            raise ValueError('Las tres dimensiones del Marco son obligatorias')
        grupos.append('(' + ' OR '.join(_literal(v, comillas=comillas) for v in valores) + ')')
    return ' AND '.join(grupos)


def planificar_consultas(marco):
    """Etapas equilibradas: contexto, territorio y exploración para cada entidad."""
    if isinstance(marco, str):
        marco = Marco.desde_input(marco)
    contextos = '(' + ' OR '.join(_literal(v) for v in marco.contextos) + ')'
    territorios = '(' + ' OR '.join(_literal(v) for v in marco.territorios) + ')'
    salida, vistos = [], set()
    for etapa, grupo in (('contexto', contextos), ('territorio', territorios), ('exploracion', None)):
        for entidad in marco.entidades:
            base = _literal(entidad, comillas=True)
            consulta = f'{base} AND {grupo}' if grupo else base
            if consulta not in vistos:
                salida.append((etapa, consulta))
                vistos.add(consulta)
    return salida
