"""Marco: entidades; contextos; territorios de mayor a menor especificidad."""
from dataclasses import dataclass
import re


def alternativas_contexto(contexto):
    """Solo OR explícito declara disyunción; las comas separan consultas."""
    return tuple(v.strip() for v in re.split(r'\s+OR\s+', contexto))


@dataclass(frozen=True)
class Marco:
    entidades: tuple[str, ...]
    contextos: tuple[str, ...]
    territorios: tuple[str, ...]

    @classmethod
    def desde_input(cls, texto):
        if not isinstance(texto, str):
            raise ValueError('Marco debe ser texto')
        partes = texto.split(';')
        if len(partes) != 3:
            raise ValueError('Use entidad(es); contexto(s); territorios ordenados por especificidad')
        dimensiones = [tuple(dict.fromkeys(x.strip() for x in parte.split(',') if x.strip())) for parte in partes]
        if not all(dimensiones):
            raise ValueError('Las tres dimensiones del Marco son obligatorias')
        return cls(*dimensiones)
