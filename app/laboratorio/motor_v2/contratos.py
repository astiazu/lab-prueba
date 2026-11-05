"""Contrato local compatible con el orquestador adjunto (dependencia no adjunta)."""
from dataclasses import dataclass


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
            raise ValueError('Use entidad(es); contexto(s); territorio(s)')
        dimensiones = [tuple(dict.fromkeys(x.strip() for x in parte.split(',') if x.strip())) for parte in partes]
        if not all(dimensiones):
            raise ValueError('Las tres dimensiones del Marco son obligatorias')
        return cls(*dimensiones)
