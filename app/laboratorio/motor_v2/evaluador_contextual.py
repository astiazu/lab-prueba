"""Evaluación EMM determinista: solo se compara el vocabulario del Marco.

Normaliza Unicode, acentos y mayúsculas. Cada término de una expresión del Marco
requiere un token exacto, un prefijo común de al menos cinco caracteres (80% del
más largo) o similitud >= 0.88 para tokens de al menos cinco caracteres.
No hay diccionarios temáticos ni decisiones de descarte.
"""
from difflib import SequenceMatcher
import re
import unicodedata


def _tokens(texto):
    normalizado = unicodedata.normalize('NFKD', texto.casefold())
    normalizado = ''.join(c for c in normalizado if not unicodedata.combining(c))
    return re.findall(r'[^\W_]+', normalizado, flags=re.UNICODE)


def _similares(termino, token):
    if termino == token:
        return True
    if min(len(termino), len(token)) < 5 or not termino.isalpha() or not token.isalpha():
        return False
    comun = 0
    for a, b in zip(termino, token):
        if a != b:
            break
        comun += 1
    if comun >= 5 and comun / max(len(termino), len(token)) >= 0.8:
        return True
    return SequenceMatcher(None, termino, token, autojunk=False).ratio() >= 0.88


def evaluar_publicacion(marco, publicacion):
    textos = [publicacion.get(campo) for campo in ('titulo', 'descripcion', 'cuerpo_extraido')]
    tokens = set(_tokens(' '.join(t for t in textos if isinstance(t, str))))

    def encontrados(valores):
        salida = []
        for valor in valores:
            terminos = _tokens(valor)
            if terminos and all(any(_similares(t, palabra) for palabra in tokens) for t in terminos):
                if valor not in salida:
                    salida.append(valor)
        return salida

    entidad = encontrados(marco.entidades)
    contexto = encontrados(marco.contextos)
    territorio = encontrados(marco.territorios)
    score = 0.0 if not entidad else (1.0 if contexto and territorio else 0.6 if contexto else 0.3)
    dimensiones = [('entidad', entidad), ('contexto', contexto), ('territorio', territorio)]
    presentes = [f'{nombre}: {", ".join(valores)}' for nombre, valores in dimensiones if valores]
    faltantes = [nombre for nombre, valores in dimensiones if not valores]
    justificacion = 'Encontrado: ' + ('; '.join(presentes) or 'ninguna dimensión') + '. '
    justificacion += 'Falta: ' + (', '.join(faltantes) or 'ninguna dimensión') + '.'
    return {'match_entidad': entidad, 'match_contexto': contexto, 'match_territorio': territorio,
            'score_emm': score, 'justificacion': justificacion}
