"""Stub DuckDuckGo: una página local por consulta, sin tráfico HTTP."""
from .stubs import resultados_web


class DDGRespuestaInvalida(ValueError):
    def __init__(self, estado, diagnostico):
        super().__init__(estado)
        self.estado = estado
        self.diagnostico = diagnostico


def consultar(consulta, cursor=None, *, con_diagnostico=False):
    respuesta = (resultados_web(consulta), None)
    if con_diagnostico:
        return (*respuesta, {'modo': 'STUB_LOCAL', 'estado': 'OK'})
    return respuesta
