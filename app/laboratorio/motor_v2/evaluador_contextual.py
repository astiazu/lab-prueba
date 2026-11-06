"""Evaluación EMM exacta por palabras, sin diccionarios de dominio ni descartes."""
import re
import unicodedata

from app.laboratorio.motor_v2.contratos import Marco


def _tokens(texto):
    # Conservar acentos: la única equivalencia solicitada es de mayúsculas.
    return re.findall(r'[^\W_]+', unicodedata.normalize('NFC', texto).casefold())


def evaluar_publicacion(marco, publicacion):
    if isinstance(marco, str):
        marco = Marco.desde_input(marco)
    textos = [publicacion.get(campo) for campo in ('titulo', 'cuerpo_extraido')]
    tokens = set(_tokens(' '.join(t for t in textos if isinstance(t, str))))
    detalles = {}
    matches = {}
    for dimension, valores in (('entidades', marco.entidades), ('contextos', marco.contextos), ('territorios', marco.territorios)):
        encontrados, faltantes, palabras = [], [], []
        for valor in valores:
            terminos = _tokens(valor)
            for palabra in terminos:
                if palabra not in palabras:
                    palabras.append(palabra)
            # Una alternativa compuesta debe aportar todas sus palabras.
            (encontrados if terminos and all(t in tokens for t in terminos) else faltantes).append(valor)
        detalles[dimension] = {
            'encontrados': encontrados, 'no_encontrados': faltantes,
            'palabras_encontradas': [p for p in palabras if p in tokens],
            'palabras_no_encontradas': [p for p in palabras if p not in tokens],
        }
        matches[dimension] = encontrados
    entidad, contexto, territorio = (matches[d] for d in ('entidades', 'contextos', 'territorios'))
    score = 0.0 if not entidad else (1.0 if contexto and territorio else 0.6 if contexto else 0.3)
    dimensiones = [('entidad', entidad), ('contexto', contexto), ('territorio', territorio)]
    presentes = [f'{nombre}: {", ".join(valores)}' for nombre, valores in dimensiones if valores]
    faltantes = [nombre for nombre, valores in dimensiones if not valores]
    justificacion = 'Encontrado: ' + ('; '.join(presentes) or 'ninguna dimensión') + '. '
    justificacion += 'Falta: ' + (', '.join(faltantes) or 'ninguna dimensión') + '.'
    return {'score_emm': score, 'detalles': detalles, 'match_entidad': entidad,
            'match_contexto': contexto, 'match_territorio': territorio, 'justificacion': justificacion}
