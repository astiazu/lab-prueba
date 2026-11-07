"""EMM agnóstico: cap de identidad y mejor territorio según el orden del Marco."""
import re
from math import fsum
import unicodedata

from app.laboratorio.motor_v2.contratos import Marco, alternativas_contexto
from app.laboratorio.motor_v2.politica_emm import PoliticaEMM, peso_territorio


def _tokens(texto):
    return re.findall(r'[^\W_]+', unicodedata.normalize('NFC', texto).casefold())


def _menciones(terminos, textos):
    if not terminos:
        return 0
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


def _fuentes(publicacion):
    fuentes = [(campo.upper(), publicacion.get(campo)) for campo in ('titulo', 'descripcion', 'cuerpo_extraido')]
    metadatos = publicacion.get('metadatos_youtube')
    if isinstance(metadatos, dict):
        fuentes.extend((f'YOUTUBE_{campo.upper()}', metadatos.get(campo)) for campo in ('titulo', 'descripcion'))
    return [(nombre, texto) for nombre, texto in fuentes if isinstance(texto, str) and texto.strip()]


def evaluar_publicacion(marco, publicacion, politica=None):
    if isinstance(marco, str):
        marco = Marco.desde_input(marco)
    politica = politica or PoliticaEMM()
    fuentes = _fuentes(publicacion)
    supertexto = ' '.join(texto for _, texto in fuentes)
    tokens = set(_tokens(supertexto))
    # No contar como alta densidad la misma descripción copiada literalmente
    # a cuerpo_extraido o repetida en los metadatos nativos.
    textos_unicos, vistos = [], set()
    for _, texto in fuentes:
        terminos = _tokens(texto)
        firma = tuple(terminos)
        if firma not in vistos:
            vistos.add(firma)
            textos_unicos.append(terminos)
    detalles, matches, menciones = {}, {}, {}
    for dimension, valores in (('entidades', marco.entidades), ('contextos', marco.contextos), ('territorios', marco.territorios)):
        encontrados, faltantes, palabras, evidencia = [], [], [], []
        for valor in valores:
            alternativas = alternativas_contexto(valor) if dimension == 'contextos' else (valor,)
            terminos = [t for v in alternativas for t in _tokens(v)]
            cantidad = sum(_menciones(_tokens(v), textos_unicos) for v in alternativas)
            presentes = [v for v in alternativas if _menciones(_tokens(v), textos_unicos)]
            presente = bool(presentes)
            (encontrados if presente else faltantes).append(valor)
            evidencia.append({'alternativa': valor, 'metodo': 'frase_completa' if presente else 'sin_coincidencia',
                              'menciones': cantidad, 'alternativas_encontradas': presentes})
            for palabra in terminos:
                if palabra not in palabras:
                    palabras.append(palabra)
        detalles[dimension] = {'presente': bool(encontrados), 'encontrados': encontrados, 'no_encontrados': faltantes,
                               'palabras_encontradas': [p for p in palabras if p in tokens],
                               'palabras_no_encontradas': [p for p in palabras if p not in tokens], 'evidencia': evidencia}
        matches[dimension] = encontrados
        menciones[dimension] = max((e['menciones'] for e in evidencia), default=0)
    principal = marco.entidades[0]
    principal_presente = principal in matches['entidades']
    cantidad_principal = _menciones(_tokens(principal), textos_unicos)
    contexto, territorio = matches['contextos'], matches['territorios']
    mejor = None
    # Recorrer el MARCO, nunca el orden de aparición en el documento.
    for declarado in marco.territorios:
        if declarado in territorio:
            mejor = declarado
            break
    aporte = peso_territorio(mejor, marco, politica) if mejor is not None else 0.0
    detalles['territorios'].update(
        criterio_especificidad='ORDEN_DEL_MARCO', mejor_match=mejor,
        pesos={t: peso_territorio(t, marco, politica) for t in marco.territorios}, aporte_score=aporte)
    componentes = {'entidad': politica.peso_entidad if principal_presente else 0.0,
                   'contexto': politica.peso_contexto if contexto else 0.0,
                   'territorio': aporte}
    score_base = fsum(componentes.values())
    score = score_base if principal_presente else min(score_base, politica.score_max_sin_entidad)
    penalizaciones = []
    if not principal_presente:
        penalizaciones.append({'codigo': 'sin_entidad_principal', 'limite': politica.score_max_sin_entidad,
                                'motivo': 'No aparece la entidad principal completa.'})
    if score >= politica.umbral_aceptacion:
        motivo = None
    elif not principal_presente:
        motivo = 'sin_entidad_principal'
    elif not contexto:
        motivo = 'entidad_homonima'
    elif not territorio:
        motivo = 'territorio_incorrecto'
    else:
        motivo = 'score_bajo'
    detalles['entidades'].update(principal=principal, principal_presente=principal_presente,
                                menciones_principal=cantidad_principal)
    ubicaciones = []
    etiquetas = {'TITULO': 'TITULO', 'DESCRIPCION': 'DESCRIPCION', 'CUERPO_EXTRAIDO': 'CUERPO',
                 'YOUTUBE_TITULO': 'METADATOS_YOUTUBE_TITULO', 'YOUTUBE_DESCRIPCION': 'METADATOS_YOUTUBE_DESCRIPCION'}
    for campo in ('TITULO', 'CUERPO_EXTRAIDO', 'DESCRIPCION', 'YOUTUBE_TITULO', 'YOUTUBE_DESCRIPCION'):
        if campo == 'CUERPO_EXTRAIDO' and (publicacion.get('recuperacion') or {}).get('fuente_texto') == 'DESCRIPCION_BRAVE':
            continue
        for nombre, texto in fuentes:
            if nombre == campo and any(_menciones(_tokens(e), [_tokens(texto)]) for e in marco.entidades):
                ubicaciones.append(etiquetas[campo])
    faltantes = []
    if not principal_presente:
        faltantes.append('entidad principal')
    if not contexto:
        faltantes.append('contexto')
    if not territorio:
        faltantes.append('territorio')
    presentes = [f'{nombre}: {", ".join(matches[dimension])}'
                 for nombre, dimension in (('entidad', 'entidades'), ('contexto', 'contextos'), ('territorio', 'territorios'))
                 if matches[dimension]]
    justificacion = 'Encontrado: ' + ('; '.join(presentes) or 'ninguna dimensión') + '. '
    justificacion += 'Falta: ' + (', '.join(faltantes) or 'ninguna dimensión') + '.'
    if penalizaciones:
        justificacion += ' ' + ' '.join(p['motivo'] for p in penalizaciones)
    return {'score_emm': score, 'motivo_descarte': motivo, 'score_base': score_base, 'penalizaciones': penalizaciones,
            'detalles': detalles, 'match_entidad': matches['entidades'],
            'match_contexto': contexto, 'match_territorio': territorio,
            'entidad_principal_presente': principal_presente,
            'coocurrencia': sum(bool(v) for v in (matches['entidades'], contexto, territorio)) >= 2,
            'componentes_score': componentes,
            'menciones_por_dimension': menciones, 'fuentes_texto_evaluadas': [n for n, _ in fuentes],
            'justificacion': justificacion,
            'ubicacion_entidad': ubicaciones[0] if ubicaciones else None, 'ubicaciones_entidad': ubicaciones}
