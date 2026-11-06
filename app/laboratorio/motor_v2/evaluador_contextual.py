"""EMM sobre todas las fuentes de texto, con territorios genéricos declarados."""
import re
import unicodedata

from app.laboratorio.motor_v2.contratos import Marco


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


def evaluar_publicacion(marco, publicacion):
    if isinstance(marco, str):
        marco = Marco.desde_input(marco)
    fuentes = _fuentes(publicacion)
    supertexto = ' '.join(texto for _, texto in fuentes)
    secuencia = _tokens(supertexto)
    tokens = set(secuencia)
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
            terminos = _tokens(valor)
            cantidad = _menciones(terminos, textos_unicos)
            presente = bool(_menciones(terminos, [secuencia]))
            (encontrados if presente else faltantes).append(valor)
            evidencia.append({'alternativa': valor, 'metodo': 'frase_completa' if presente else 'sin_coincidencia',
                              'menciones': cantidad})
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
    if not principal_presente:
        score = 0.0
    elif contexto and territorio:
        score = 1.0 if cantidad_principal >= 2 else 0.8
    elif contexto or territorio:
        score = 0.4
    else:
        score = 0.2
    score_base = score
    genericos = list(marco.territorios_genericos)
    especificos = [v for v in marco.territorios if v not in genericos]
    genericos_encontrados = [v for v in territorio if v in genericos]
    especificos_encontrados = [v for v in territorio if v in especificos]
    penalizaciones = []
    if principal_presente and genericos_encontrados and not especificos_encontrados:
        score = min(score, 0.4)
        penalizaciones.append({'codigo': 'solo_territorio_generico', 'limite': 0.4,
                                'motivo': 'Solo coinciden territorios declarados genéricos; falta un territorio específico del Marco.'})
    detalles['territorios'].update(genericos=genericos, especificos=especificos,
                                  genericos_encontrados=genericos_encontrados,
                                  especificos_encontrados=especificos_encontrados,
                                  criterio_especificidad='DECLARACION_DEL_MARCO')
    detalles['entidades'].update(principal=principal, principal_presente=principal_presente,
                                menciones_principal=cantidad_principal)
    ubicaciones = []
    etiquetas = {'TITULO': 'TITULO', 'DESCRIPCION': 'DESCRIPCION', 'CUERPO_EXTRAIDO': 'CUERPO',
                 'YOUTUBE_TITULO': 'METADATOS_YOUTUBE_TITULO', 'YOUTUBE_DESCRIPCION': 'METADATOS_YOUTUBE_DESCRIPCION'}
    for campo in ('TITULO', 'CUERPO_EXTRAIDO', 'DESCRIPCION', 'YOUTUBE_TITULO', 'YOUTUBE_DESCRIPCION'):
        if campo == 'CUERPO_EXTRAIDO' and (publicacion.get('recuperacion') or {}).get('fuente_texto') == 'DESCRIPCION_BRAVE':
            continue
        for nombre, texto in fuentes:
            if nombre == campo and _menciones(_tokens(principal), [_tokens(texto)]):
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
    return {'score_emm': score, 'score_base': score_base, 'penalizaciones': penalizaciones,
            'detalles': detalles, 'match_entidad': matches['entidades'],
            'match_contexto': contexto, 'match_territorio': territorio,
            'entidad_principal_presente': principal_presente,
            'coocurrencia': principal_presente and bool(contexto or territorio),
            'menciones_por_dimension': menciones, 'fuentes_texto_evaluadas': [n for n, _ in fuentes],
            'justificacion': justificacion,
            'ubicacion_entidad': ubicaciones[0] if ubicaciones else None, 'ubicaciones_entidad': ubicaciones}
