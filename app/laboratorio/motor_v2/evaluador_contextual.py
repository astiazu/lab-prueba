"""Termómetro EMM universal con alternativas y partes principales auditables."""
from math import ceil
import re
import unicodedata

from app.laboratorio.motor_v2.contratos import Marco

VENTANA_ENTIDAD = 12


def _tokens(texto):
    return re.findall(r'[^\W_]+', unicodedata.normalize('NFC', texto).casefold())


def _menciones(terminos, textos):
    """Contar frases completas no solapadas, sin unir título y cuerpo."""
    cantidad = 0
    for tokens in textos:
        i = 0
        while i <= len(tokens) - len(terminos):
            if tokens[i:i + len(terminos)] == terminos:
                cantidad += 1
                i += len(terminos)
            else:
                i += 1
    return cantidad


def _partes_principales(terminos, textos):
    # Heurística exclusivamente estructural: longitud, proporción y cercanía.
    partes = set(t for t in terminos if len(t) >= 4)
    if not partes:
        return 0
    minimo = max(2, ceil(len(partes) * 2 / 3)) if len(partes) > 1 else 1
    cantidad = 0
    for tokens in textos:
        i = 0
        while i < len(tokens):
            if tokens[i] not in partes:
                i += 1
                continue
            posiciones = [j for j in range(i, min(i + VENTANA_ENTIDAD, len(tokens))) if tokens[j] in partes]
            if len({tokens[j] for j in posiciones}) >= minimo:
                # Consumir solo la primera combinación suficiente, sin solapar.
                vistos = set()
                for j in posiciones:
                    vistos.add(tokens[j])
                    if len(vistos) >= minimo:
                        cantidad += 1
                        i = j + 1
                        break
            else:
                i += 1
    return cantidad


def evaluar_publicacion(marco, publicacion):
    if isinstance(marco, str):
        marco = Marco.desde_input(marco)
    textos = [_tokens(publicacion.get(campo) or '') for campo in ('titulo', 'cuerpo_extraido')
              if isinstance(publicacion.get(campo) or '', str)]
    tokens = {token for texto in textos for token in texto}
    detalles, matches, menciones = {}, {}, {}
    for dimension, valores in (('entidades', marco.entidades), ('contextos', marco.contextos), ('territorios', marco.territorios)):
        encontrados, faltantes, palabras, evidencia = [], [], [], []
        for valor in valores:
            terminos = _tokens(valor)
            for palabra in terminos:
                if palabra not in palabras:
                    palabras.append(palabra)
            completas = _menciones(terminos, textos) if terminos else 0
            cantidad = completas
            metodo = 'frase_completa'
            if dimension == 'entidades' and terminos:
                parciales = _partes_principales(terminos, textos)
                cantidad = max(completas, parciales)
                if not completas and parciales:
                    metodo = 'partes_principales'
            (encontrados if cantidad else faltantes).append(valor)
            evidencia.append({'alternativa': valor, 'metodo': metodo if cantidad else 'sin_coincidencia', 'menciones': cantidad})
        detalles[dimension] = {'presente': bool(encontrados), 'encontrados': encontrados, 'no_encontrados': faltantes,
                               'palabras_encontradas': [p for p in palabras if p in tokens],
                               'palabras_no_encontradas': [p for p in palabras if p not in tokens],
                               'evidencia': evidencia}
        matches[dimension] = encontrados
        # Exigir repetición de una misma alternativa; no inflar por alternativas solapadas.
        menciones[dimension] = max((e['menciones'] for e in evidencia), default=0)
    entidad, contexto, territorio = (matches[d] for d in ('entidades', 'contextos', 'territorios'))
    repetida = menciones['entidades'] >= 2
    if not entidad:
        score = 0.0
    elif contexto and territorio:
        score = 1.0 if repetida else 0.8
    elif contexto or territorio:
        score = 0.6
    else:
        score = 0.4
    dimensiones = [('entidad', entidad), ('contexto', contexto), ('territorio', territorio)]
    presentes = [f'{nombre}: {", ".join(valores)}' for nombre, valores in dimensiones if valores]
    faltantes = [nombre for nombre, valores in dimensiones if not valores]
    justificacion = 'Encontrado: ' + ('; '.join(presentes) or 'ninguna dimensión') + '. '
    justificacion += 'Falta: ' + (', '.join(faltantes) or 'ninguna dimensión') + '.'
    if entidad and contexto and territorio:
        justificacion += ' Entidad con múltiples menciones.' if repetida else ' Sin repetición de la entidad.'
    return {'score_emm': score, 'detalles': detalles, 'match_entidad': entidad,
            'match_contexto': contexto, 'match_territorio': territorio,
            'menciones_por_dimension': menciones, 'justificacion': justificacion}
