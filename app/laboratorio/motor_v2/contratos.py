"""Contrato local compatible con el orquestador adjunto (dependencia no adjunta)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Marco:
    entidades: tuple[str, ...]
    contextos: tuple[str, ...]
    territorios: tuple[str, ...]
    territorios_genericos: tuple[str, ...] = ()

    @classmethod
    def desde_input(cls, texto, *, territorios_genericos=None):
        if not isinstance(texto, str):
            raise ValueError('Marco debe ser texto')
        partes = texto.split(';')
        if len(partes) != 3:
            raise ValueError('Use entidad(es); contexto(s); territorio(s)')
        dimensiones = [tuple(dict.fromkeys(x.strip() for x in parte.split(',') if x.strip())) for parte in partes]
        if not all(dimensiones):
            raise ValueError('Las tres dimensiones del Marco son obligatorias')
        genericos = territorios_genericos if territorios_genericos is not None else []
        if not isinstance(genericos, (list, tuple)) or any(not isinstance(v, str) or not v.strip() for v in genericos):
            raise ValueError('territorios_genericos debe ser una lista de alternativas del Marco')
        disponibles = {v.casefold(): v for v in dimensiones[2]}
        if any(v.strip().casefold() not in disponibles for v in genericos):
            raise ValueError('Cada territorio genérico debe pertenecer a los territorios del Marco')
        genericos = tuple(dict.fromkeys(disponibles[v.strip().casefold()] for v in genericos))
        return cls(*dimensiones, territorios_genericos=genericos)
