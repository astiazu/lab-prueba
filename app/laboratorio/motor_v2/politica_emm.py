"""Política universal configurable del motor; no depende de casos particulares."""
from dataclasses import asdict, dataclass, fields
import math

PESO_ENTIDAD = 0.40
PESO_CONTEXTO = 0.30
PESO_TERRITORIO = 0.30
SCORE_MAX_SIN_ENTIDAD = 0.40
UMBRAL_ARCHIVADO = 0.30
UMBRAL_ACEPTACION = 0.50
UMBRAL_REAL = 0.80


@dataclass(frozen=True)
class PoliticaEMM:
    peso_entidad: float = PESO_ENTIDAD
    peso_contexto: float = PESO_CONTEXTO
    peso_territorio: float = PESO_TERRITORIO
    score_max_sin_entidad: float = SCORE_MAX_SIN_ENTIDAD
    umbral_archivado: float = UMBRAL_ARCHIVADO
    umbral_aceptacion: float = UMBRAL_ACEPTACION
    umbral_real: float = UMBRAL_REAL

    def __post_init__(self):
        for campo in fields(self):
            valor = getattr(self, campo.name)
            if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor) or not 0 <= valor <= 1:
                raise ValueError(f'Parámetro EMM inválido: {campo.name}')
        if not math.isclose(self.peso_entidad + self.peso_contexto + self.peso_territorio, 1.0, abs_tol=1e-9):
            raise ValueError('Los pesos EMM deben sumar 1')
        if not 0 <= self.umbral_archivado <= self.umbral_aceptacion <= self.umbral_real <= 1:
            raise ValueError('Orden de umbrales inválido')
        if not self.score_max_sin_entidad < self.umbral_aceptacion:
            raise ValueError('El cap sin entidad debe ser menor al umbral de aceptación')

    @classmethod
    def desde_config(cls, config=None):
        if config is None:
            return cls()
        if not isinstance(config, dict) or set(config) - {f.name for f in fields(cls)}:
            raise ValueError('Configuración politica_emm inválida')
        return cls(**config)

    def como_dict(self):
        return asdict(self)


def peso_territorio(territorio, marco, politica=None):
    """El orden del Marco determina la especificidad, no el orden del documento."""
    politica = politica or PoliticaEMM()
    territorios = marco.territorios
    n = len(territorios)
    if not n:
        raise ValueError('El Marco requiere territorios')
    posicion = territorios.index(territorio)
    rango = n - posicion
    # Fórmula aprobada: presupuesto territorial * (rango / N).
    # El mejor siempre recibe el presupuesto completo; los matches NO se suman.
    return politica.peso_territorio * (rango / n)
