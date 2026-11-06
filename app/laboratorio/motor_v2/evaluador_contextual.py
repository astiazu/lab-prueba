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
    contexto = matches['contextos']
    territorios_textuales = list(matches['territorios'])
    genericos = list(marco.territorios_genericos)
    especificos = [v for v in marco.territorios if v not in genericos]
    genericos_encontrados = [v for v in territorios_textuales if v in genericos]
    especificos_encontrados = [v for v in territorios_textuales if v in especificos]
    inferidos = [v for v in genericos if v not in territorios_textuales] if especificos_encontrados else []
    territorio = [v for v in marco.territorios if v in territorios_textuales or v in inferidos]
    matches['territorios'] = territorio
    detalle_territorio = detalles['territorios']
    detalle_territorio.update(presente=bool(territorio), encontrados=territorio,
                             encontrados_textuales=territorios_textuales,
                             no_encontrados_textuales=list(detalle_territorio['no_encontrados']),
                             no_encontrados=[v for v in marco.territorios if v not in territorio],
                             inferidos=inferidos, genericos=genericos, especificos=especificos,
                             genericos_encontrados=genericos_encontrados,
                             especificos_encontrados=especificos_encontrados,
                             criterio_especificidad='DECLARACION_DEL_MARCO')
    for evidencia in detalle_territorio['evidencia']:
        if evidencia['alternativa'] in inferidos:
            evidencia.update(metodo='inferencia_por_territorio_especifico',
                             inferido_desde=list(especificos_encontrados))
    componentes = {'entidad': 0.4 if matches['entidades'] else 0.0,
                   'contexto': 0.3 if contexto else 0.0,
                   'territorio': 0.3 if territorio else 0.0}
    score = round(sum(componentes.values()), 1)
    score_base = score
    penalizaciones = []
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
    if not matches['entidades']:
        faltantes.append('entidad')
    if not contexto:
        faltantes.append('contexto')
    if not territorio:
        faltantes.append('territorio')
    presentes = [f'{nombre}: {", ".join(matches[dimension])}'
                 for nombre, dimension in (('entidad', 'entidades'), ('contexto', 'contextos'), ('territorio', 'territorios'))
                 if matches[dimension]]
    justificacion = 'Encontrado: ' + ('; '.join(presentes) or 'ninguna dimensión') + '. '
    justificacion += 'Falta: ' + (', '.join(faltantes) or 'ninguna dimensión') + '.'
    if inferidos:
        justificacion += ' Territorios inferidos por declaración del Marco: ' + ', '.join(inferidos) + '.'
    return {'score_emm': score, 'score_base': score_base, 'penalizaciones': penalizaciones,
            'detalles': detalles, 'match_entidad': matches['entidades'],
            'match_contexto': contexto, 'match_territorio': territorio,
            'entidad_principal_presente': principal_presente,
            'coocurrencia': sum(bool(v) for v in (matches['entidades'], contexto, territorio)) >= 2,
            'componentes_score': componentes,
            'menciones_por_dimension': menciones, 'fuentes_texto_evaluadas': [n for n, _ in fuentes],
            'justificacion': justificacion,
            'ubicacion_entidad': ubicaciones[0] if ubicaciones else None, 'ubicaciones_entidad': ubicaciones}
