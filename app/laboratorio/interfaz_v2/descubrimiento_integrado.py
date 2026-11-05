"""Descubrimiento multiproveedor V5; sin decisión EMM ni filtrado irreversible.
V5 corrige V4: DDG LIMITADO no se cuenta como pendiente reintentable,
Brave sin corte prematuro 12, fase redes con cobertura independiente.
"""
from __future__ import annotations
import json
import os
from hashlib import sha256
from collections import Counter, deque
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from app.laboratorio.motor_v2.contratos import Marco
from app.laboratorio.interfaz_v2 import descubrimiento_brave as brave
from app.laboratorio.interfaz_v2 import descubrimiento_ddg as ddg
from app.laboratorio.interfaz_v2 import descubrimiento_youtube as youtube
from app.laboratorio.interfaz_v2 import descubrimiento_redes as redes
from app.laboratorio.motor_v2.recuperacion_documental_enriquecida import enriquecer, fuente_url
from app.laboratorio.motor_v2.recuperador_documental import descargar_html

# Aislar este modo mixto de los snapshots anteriores totalmente simulados.
DESTINO = Path(__file__).resolve().parents[3] / 'datos' / 'ejecuciones' / 'descubrimiento_v2_ddg'
REDES = ('facebook.com', 'instagram.com', 'youtube.com', 'x.com', 'twitter.com')

def planificar(marco):
    """Rondas equilibradas por entidad, contexto, territorio y red.
    Las dimensiones son alternativas: ninguna se exige conjuntamente para admitir.
    """
    grupos = {}
    def agregar(familia, linea, consulta):
        grupos.setdefault((familia, linea), []).append((familia, consulta))
    for entidad in marco.entidades:
        e = '"' + entidad.replace('"', '') + '"'
        for i, contexto in enumerate(marco.contextos):
            linea = (entidad, i)
            for territorio in marco.territorios:
                agregar('contexto_territorio', linea, f'{e} {contexto} {territorio}')
            agregar('contexto', linea, f'{e} {contexto}')
            for sitio in REDES:
                agregar('red_contexto', (entidad, i, sitio), f'{e} {contexto} site:{sitio}')
        for i, territorio in enumerate(marco.territorios):
            agregar('territorio', (entidad, i), f'{e} {territorio}')
            for sitio in REDES:
                agregar('red_territorio', (entidad, i, sitio), f'{e} {territorio} site:{sitio}')
        agregar('exploracion', (entidad, 0), e)
    orden = ('contexto_territorio', 'red_contexto', 'territorio', 'red_territorio', 'contexto', 'exploracion')
    colas = {f: deque((k, deque(v)) for k, v in grupos.items() if k[0] == f) for f in orden}
    salida, vistos = [], set()
    while any(colas.values()):
        for familia in orden:
            cola = colas[familia]
            if not cola:
                continue
            clave, opciones = cola.popleft()
            tipo, q = opciones.popleft()
            if q.casefold() not in vistos:
                salida.append((tipo, q))
                vistos.add(q.casefold())
            if opciones:
                cola.append((clave, opciones))
    return salida

def _seleccionar_brave_v5(propuestas, limite):
    """Fases secuenciales: web contextual y luego redes indexadas.

    Rondas equilibradas entre contextos/territorios en el orden del planificador.
    La selección no supone acreditación EMM ni acceso nativo a redes.
    """
    web = [x for x in propuestas if not x[0].startswith('red_')]
    redes = [x for x in propuestas if x[0].startswith('red_')]
    por_red = {red: deque(x for x in redes if f'site:{red}' in x[1]) for red in REDES}
    redes_equilibradas = []
    while any(por_red.values()):
        for red in REDES:
            if por_red[red]:
                redes_equilibradas.append(por_red[red].popleft())
    return (web + redes_equilibradas)[:limite]


def ejecutar_busqueda(payload, *, brave_consultar=None, ddg_consultar=None, youtube_buscar=None, youtube_detalles=None, documental_obtener_html=None):
    texto = payload.get('marco')
    if not isinstance(texto, str) or not 0 < len(texto) <= 4000:
        raise ValueError('Marco inválido')
    marco = Marco.desde_input(texto)
    if not all((marco.entidades, marco.contextos, marco.territorios)):
        raise ValueError('Marco obligatorio: entidad(es); contexto(s); territorio(s)')
    periodo = payload.get('periodo') or {}
    desde, hasta = date.fromisoformat(periodo['desde']), date.fromisoformat(periodo['hasta'])
    if desde > hasta or hasta > date.today():
        raise ValueError('Período inválido o fecha futura')
    max_ddg, max_brave = payload.get('max_ddg', 90), payload.get('max_brave', 50)
    if type(max_ddg) is not int or not 0 <= max_ddg <= 90:
        raise ValueError('max_ddg fuera de rango (0..90)')
    if type(max_brave) is not int or not 0 <= max_brave <= 50:
        raise ValueError('max_brave fuera de rango (0..50)')
    max_youtube = payload.get('max_youtube', 6)
    paginas_youtube = payload.get('paginas_youtube', 1)
    if type(max_youtube) is not int or not 0 <= max_youtube <= 20:
        raise ValueError('max_youtube fuera de rango (0..20)')
    if type(paginas_youtube) is not int or not 1 <= paginas_youtube <= 3:
        raise ValueError('paginas_youtube fuera de rango (1..3)')
    max_facebook, max_instagram, max_x = payload.get('max_facebook', 8), payload.get('max_instagram', 8), payload.get('max_x', 8)
    if any(type(n) is not int or not 0 <= n <= 30 for n in (max_facebook, max_instagram, max_x)):
        raise ValueError('Presupuestos Facebook/Instagram/X fuera de rango (0..30)')
    if max_ddg + max_brave + max_youtube + max_facebook + max_instagram + max_x == 0:
        raise ValueError('Debe habilitar al menos un proveedor')
    clave = brave.clave_brave()
    if (max_brave or max_facebook or max_instagram or max_x) and brave_consultar is None and not clave:
        max_brave = max_facebook = max_instagram = max_x = 0
    propuestas = planificar(marco)
    consultas_unicas_planificadas = len(propuestas)

    # Snapshot anterior inmutable: solo mismo Marco y período. Nunca se reescribe.
    anterior = None
    if DESTINO.is_dir():
        for ruta_anterior in sorted(DESTINO.glob('busqueda_integrada_*.json'), reverse=True):
            try:
                candidato = json.loads(ruta_anterior.read_text(encoding='utf-8'))
                if candidato.get('marco') == texto and candidato.get('periodo') == {'desde':desde.isoformat(), 'hasta':hasta.isoformat()}:
                    anterior = candidato
                    break
            except (ValueError, OSError):
                continue
    urls, registros, errores, avisos = {}, [], [], []
    # Identidad por video_id, no URL: watch, shorts y youtu.be son una evidencia.
    por_video = {}
    for item in (anterior or {}).get('publicaciones', []):
        if not isinstance(item, dict) or not item.get('url'):
            continue
        doc = json.loads(json.dumps(item))
        vid = youtube.identificar_video(doc['url'])
        social = next((redes.identidad(doc['url'], red) for red in ('FACEBOOK', 'INSTAGRAM', 'X') if redes.identidad(doc['url'], red)), None)
        key = f'YOUTUBE:{vid}' if vid else (social[0] if social else brave._normalizar_url(doc['url']))
        if not key:
            continue
        if key in urls:
            existente = urls[key]
            if doc['url'] != existente['url'] and doc['url'] not in existente.setdefault('urls_equivalentes', []): existente['urls_equivalentes'].append(doc['url'])
            for campo in ('consultas_origen','proveedores'):
                for valor in doc.get(campo) or []:
                    if valor not in existente.setdefault(campo, []): existente[campo].append(valor)
            continue
        urls[key] = doc
        if vid: por_video[vid] = key
    heredadas = len(urls)
    lecturas_previas = (anterior or {}).get('lecturas_youtube') or []
    lecturas_youtube = list(lecturas_previas)
    ids_actualizados = set()
    youtube_estado = 'NO_CONFIGURADO'
    youtube_registros = []
    youtube_pendientes = 0
    youtube_planificadas = 0
    youtube_intentos = 0
    youtube_detalles_intentos = 0
    youtube_key = youtube.clave_youtube() if youtube_buscar is None and youtube_detalles is None else 'SIMULACION'
    if max_youtube and not youtube_key:
        avisos.append('YouTube API no configurada; inventario anterior conservado')
    intentos = Counter()
    exito = Counter()

    def agregar(resultados, proveedor, tipo, q, pagina):
        nuevas = 0
        for r in resultados:
            url = brave._normalizar_url(r.get('url', ''))
            if not url:
                continue
            vid = youtube.identificar_video(url)
            social = next((redes.identidad(url, red) for red in ('FACEBOOK', 'INSTAGRAM', 'X') if redes.identidad(url, red)), None)
            key_url = f'YOUTUBE:{vid}' if vid else (social[0] if social else url)
            if key_url not in urls:
                urls[key_url] = {'url': url, 'titulo': r.get('title'), 'descripcion': r.get('description'),
                             'fecha_indice': r.get('page_age') if proveedor == 'BRAVE_WEB' else None,
                             'origen': urlsplit(url).hostname, 'consultas_origen': [], 'proveedores': []}
                nuevas += 1
            doc = urls[key_url]
            if vid: por_video[vid] = key_url
            if url != doc['url'] and url not in doc.setdefault('urls_equivalentes',[]): doc['urls_equivalentes'].append(url)
            if social and not vid: doc.setdefault('identidad_evidencia', social[0]); doc.setdefault('formato_red', social[2])
            if q not in doc['consultas_origen']:
                doc['consultas_origen'].append(q)
            if proveedor not in doc['proveedores']:
                doc['proveedores'].append(proveedor)
            if not doc['titulo'] and r.get('title'):
                doc['titulo'] = r['title']
            if not doc['fecha_indice'] and proveedor == 'BRAVE_WEB':
                doc['fecha_indice'] = r.get('page_age')
        registros.append({'proveedor': proveedor, 'estrategia': tipo, 'consulta': q,
                          'pagina': pagina, 'resultados': len(resultados), 'nuevas_urls': nuevas})
        exito[proveedor] += 1
        return nuevas

    # --- FASE DDG ---
    ddg_fn = ddg_consultar or ddg.consultar
    pendientes_ddg = deque(propuestas)
    cursores_vistos = set()
    diagnosticos_ddg = []
    estado_ddg = 'EN_CURSO'
    detener_ddg = False
    siguiente = None
    cursor = None
    ddg_completadas = 0
    ddg_consulta_incompleta = None

    while pendientes_ddg and intentos['DUCKDUCKGO_HTML'] < max_ddg and not detener_ddg:
        tipo, q = pendientes_ddg.popleft()
        pagina, cursor = 1, None
        siguiente = None
        while intentos['DUCKDUCKGO_HTML'] < max_ddg:
            intentos['DUCKDUCKGO_HTML'] += 1
            try:
                if ddg_consultar is None:
                    resultados, siguiente, diagnostico = ddg.consultar(q, cursor, con_diagnostico=True)
                    diagnosticos_ddg.append({'consulta': q, 'pagina': pagina, **diagnostico})
                    if diagnostico.get('estado') not in ('OK', 'SIN_RESULTADOS'):
                        raise ddg.DDGRespuestaInvalida(diagnostico.get('estado', 'ERROR_EXTRACCION'), diagnostico)
                else:
                    respuesta = ddg_fn(q, cursor)
                    resultados, siguiente = respuesta[:2]
                    if len(respuesta) > 2:
                        diagnosticos_ddg.append({'consulta': q, 'pagina': pagina, **respuesta[2]})
                agregar(resultados, 'DUCKDUCKGO_HTML', tipo, q, pagina)
                if not siguiente:
                    ddg_completadas += 1
                    break
                llave = (q, json.dumps(siguiente, sort_keys=True, default=str))
                if llave in cursores_vistos:
                    avisos.append(f'DDG: cursor repetido en consulta {q[:100]}')
                    estado_ddg = 'ERROR_EXTRACCION'
                    ddg_consulta_incompleta = q
                    detener_ddg = True
                    break
                cursores_vistos.add(llave)
                cursor = siguiente
                pagina += 1
            except ddg.DDGRespuestaInvalida as exc:
                estado_ddg = exc.estado
                if not diagnosticos_ddg or diagnosticos_ddg[-1].get('consulta') != q or diagnosticos_ddg[-1].get('pagina') != pagina:
                    diagnosticos_ddg.append({'consulta': q, 'pagina': pagina, **exc.diagnostico, 'estado': exc.estado})
                ddg_consulta_incompleta = q
                if exc.estado == 'LIMITADO':
                    avisos.append(f'DDG LIMITADO: se detuvo el proveedor en {q[:80]}; no se presume agotamiento ni se reintenta')
                    # V5: no malgastar resto del presupuesto DDG
                    pendientes_ddg.clear()
                else:
                    avisos.append(f'DDG {exc.estado}: {exc.diagnostico.get("aviso", "no se pudo completar la consulta")}')
                detener_ddg = True
                break
            except Exception as exc:
                errores.append({'proveedor': 'DUCKDUCKGO_HTML', 'consulta': q, 'pagina': pagina,
                                'error': f'{type(exc).__name__}: {str(exc)[:180]}'})
                ddg_consulta_incompleta = q
                estado_ddg = 'ERROR_HTTP'
                detener_ddg = True
                break
        if cursor is not None and siguiente and intentos['DUCKDUCKGO_HTML'] >= max_ddg:
            ddg_consulta_incompleta = q

    if estado_ddg == 'EN_CURSO':
        estado_ddg = 'AGOTADO' if not pendientes_ddg and ddg_consulta_incompleta is None and ddg_completadas == consultas_unicas_planificadas else 'PRESUPUESTO_AGOTADO'

    # --- FASE BRAVE WEB Y DESPUÉS REDES INDEXADAS (NO API NATIVA) ---
    brave_fn = brave_consultar or brave._brave
    seleccion = _seleccionar_brave_v5(propuestas, max_brave)
    cobertura_redes = {d: {'intentos':0, 'resultados':0, 'urls':0} for d in REDES}

    for tipo, q in seleccion:
        intentos['BRAVE_WEB'] += 1
        # tracking por red si la consulta es de red
        red_detectada = next((r for r in REDES if f'site:{r}' in q), None)
        if red_detectada:
            cobertura_redes[red_detectada]['intentos'] += 1
        try:
            respuesta = brave_fn(q, desde.isoformat(), hasta.isoformat(), clave)
            results = (respuesta.get('web') or {}).get('results') or []
            nuevas = agregar(results, 'BRAVE_WEB', tipo, q, 1)
            if red_detectada:
                cobertura_redes[red_detectada]['resultados'] += len(results)
                cobertura_redes[red_detectada]['urls'] += nuevas
        except Exception as exc:
            errores.append({'proveedor': 'BRAVE_WEB', 'consulta': q,
                            'error': f'{type(exc).__name__}: {str(exc)[:180]}'})

    # --- ADAPTADORES DE DESCUBRIMIENTO INDEXADO FACEBOOK E INSTAGRAM ---
    # La búsqueda es real; NO es API nativa ni acreditación EMM.
    redes_auditoria = {}
    respuestas_brutas_redes = []
    # No repetir consultas Meta exitosas en cortes anteriores del mismo Marco/período.
    # Los errores se reintentan; la auditoría anterior permanece inmutable.
    consultas_brave_hechas = [q for _, q in seleccion]
    consultas_meta_previas = {
        red: [r['consulta'] for r in (anterior or {}).get('consultas_ejecutadas', []) + (anterior or {}).get('consultas_historicas_redes', [])
              if isinstance(r, dict) and r.get('proveedor') == f'{red}_INDEXADO_BRAVE'
              and isinstance(r.get('consulta'), str)]
        for red in ('FACEBOOK', 'INSTAGRAM', 'X')
    }
    for red, presupuesto in (('FACEBOOK', max_facebook), ('INSTAGRAM', max_instagram), ('X', max_x)):
        if not presupuesto:
            redes_auditoria[red] = {'estado':'DESHABILITADO', 'intentadas':0, 'nuevas':0}
            continue
        auditoria = redes.descubrir(marco, red, presupuesto, brave_fn, desde.isoformat(),
                                    hasta.isoformat(), clave, consultas_brave_hechas + consultas_meta_previas[red])
        respuestas_brutas_redes.extend(auditoria['respuestas_brutas'])
        nuevas = 0
        for item in auditoria['hallazgos']:
            key = item['identidad_evidencia']
            if key not in urls:
                urls[key] = {'url':item['url'], 'titulo':item.get('title'), 'descripcion':item.get('description'),
                             'fecha_indice':item.get('page_age'), 'origen':urlsplit(item['url']).hostname,
                             'consultas_origen':[], 'proveedores':[], 'identidad_evidencia':key,
                             'formato_red':item['formato']}
                nuevas += 1
            doc = urls[key]
            doc.setdefault('identidad_evidencia',key)
            if item['url_descubierta'] != doc['url'] and item['url_descubierta'] not in doc.setdefault('urls_equivalentes',[]): doc['urls_equivalentes'].append(item['url_descubierta'])
            doc.setdefault('formato_red',item['formato'])
            if item['consulta'] not in doc.setdefault('consultas_origen',[]): doc['consultas_origen'].append(item['consulta'])
            prov = f'{red}_INDEXADO_BRAVE'
            if prov not in doc.setdefault('proveedores',[]): doc['proveedores'].append(prov)
            if not doc.get('titulo'): doc['titulo'] = item.get('title')
        intentos[f'{red}_INDEXADO_BRAVE'] += auditoria['intentadas']
        exito[f'{red}_INDEXADO_BRAVE'] += len(auditoria['consultas'])
        registros.extend(auditoria['consultas'])
        errores.extend(auditoria['errores'])
        redes_auditoria[red] = {'estado':'PARCIAL' if auditoria['errores'] or auditoria['pendientes'] else 'COMPLETO',
                               'planificadas':auditoria['planificadas'], 'intentadas':auditoria['intentadas'],
                               'omitidas_ya_ejecutadas':auditoria['omitidas_ya_ejecutadas'],
                               'ejecutadas':auditoria['ejecutadas'], 'fallidas':auditoria['fallidas'],
                               'pendientes':auditoria['pendientes'], 'nuevas':nuevas,
                               'resultados_indexados':len(auditoria['hallazgos']),
                               'consultas_abiertas':sum(r['estrategia'].startswith('abierta_') for r in auditoria['consultas']),
                               'consultas_restringidas':sum(not r['estrategia'].startswith('abierta_') for r in auditoria['consultas']),
                               'resultados_fuera_de_dominio':sum(r.get('fuera_de_dominio',0) for r in auditoria['consultas']),
                               'respuestas_brutas_guardadas':len(auditoria['respuestas_brutas']),
                               'auditoria_truncada':auditoria['auditoria_truncada'],
                               'publicaciones_o_enlaces':auditoria['publicaciones_o_enlaces'],
                               'perfiles':auditoria['perfiles']}

    # --- FASE YOUTUBE NATIVA: descubrir, consolidar, actualizar metadatos ---
    youtube_propuestas = youtube.planificar(marco)
    youtube_planificadas = len(youtube_propuestas)
    if max_youtube and youtube_key:
        youtube_estado = 'EN_CURSO'
        nuevas_youtube = set()
        seleccion_youtube = youtube_propuestas[:max_youtube]
        for tipo, q in seleccion_youtube:
            token, vistos_tokens = None, set()
            for pagina in range(1, paginas_youtube + 1):
                youtube_intentos += 1
                intentos['YOUTUBE_API_SEARCH'] += 1
                try:
                    if youtube_buscar is not None:
                        data = youtube_buscar(q, desde, hasta, youtube_key, page_token=token)
                    else:
                        data = youtube.buscar(q, desde, hasta, youtube_key, page_token=token)
                    exito['YOUTUBE_API_SEARCH'] += 1
                    encontrados, nuevos = 0, 0
                    for item in data.get('items') or []:
                        vid = (item.get('id') or {}).get('videoId') if isinstance(item.get('id'), dict) else None
                        if not vid or not youtube.VIDEO_ID.fullmatch(vid): continue
                        encontrados += 1
                        key_url = f'YOUTUBE:{vid}'
                        if key_url not in urls:
                            sn = item.get('snippet') or {}
                            urls[key_url] = {'url':f'https://www.youtube.com/watch?v={vid}',
                                'titulo':sn.get('title'), 'descripcion':sn.get('description'),
                                'fecha_indice':None, 'origen':'www.youtube.com',
                                'consultas_origen':[], 'proveedores':[]}
                            nuevos += 1
                        doc = urls[key_url]
                        por_video[vid] = key_url
                        if q not in doc.setdefault('consultas_origen', []): doc['consultas_origen'].append(q)
                        if 'YOUTUBE_API_SEARCH' not in doc.setdefault('proveedores', []): doc['proveedores'].append('YOUTUBE_API_SEARCH')
                        nuevas_youtube.add(vid)
                    youtube_registros.append({'proveedor':'YOUTUBE_API_SEARCH','estrategia':tipo,'consulta':q,
                                             'pagina':pagina,'resultados':encontrados,'nuevas_urls':nuevos})
                    siguiente_token = data.get('nextPageToken')
                    if not siguiente_token: break
                    if siguiente_token == token or siguiente_token in vistos_tokens:
                        avisos.append('YouTube: cursor repetido; cobertura parcial')
                        youtube_pendientes += 1
                        break
                    vistos_tokens.add(siguiente_token)
                    token = siguiente_token
                    if pagina == paginas_youtube:
                        youtube_pendientes += 1
                except Exception as exc:
                    errores.append({'proveedor':'YOUTUBE_API_SEARCH','consulta':q,'pagina':pagina,
                                    'error':f'{type(exc).__name__}: {str(exc)[:150]}'})
                    youtube_pendientes += 1
                    break
        youtube_pendientes += max(0, len(youtube_propuestas) - len(seleccion_youtube))
        # Incluye videos ya encontrados por Brave y los heredados del histórico.
        todos_ids = list(por_video)
        if todos_ids:
            try:
                youtube_detalles_intentos = (len(todos_ids) + 49) // 50
                intentos['YOUTUBE_API_VIDEOS'] += youtube_detalles_intentos
                detalles = (youtube_detalles(todos_ids, youtube_key) if youtube_detalles is not None
                            else youtube.detalles(todos_ids, youtube_key))
                exito['YOUTUBE_API_VIDEOS'] += youtube_detalles_intentos
                for vid, detalle in detalles.items():
                    doc = urls[por_video[vid]]
                    # URL original V5 se conserva. La identidad canónica es estable.
                    doc['identidad_evidencia'] = f'YOUTUBE:{vid}'
                    doc['youtube'] = {k:v for k,v in detalle.items() if k not in ('visualizaciones','me_gusta','comentarios_informados','recuperado_en')}
                    if 'YOUTUBE_API_VIDEOS' not in doc.setdefault('proveedores', []): doc['proveedores'].append('YOUTUBE_API_VIDEOS')
                    # Lectura nueva solo cuando existen métricas; nunca convertir N/D en 0.
                    metricas = {k:detalle.get(k) for k in ('visualizaciones','me_gusta','comentarios_informados')}
                    if any(v is not None for v in metricas.values()):
                        lecturas_youtube.append({'identidad_evidencia':f'YOUTUBE:{vid}',
                            'recuperado_en':detalle['recuperado_en'], 'metricas':metricas,
                            'fuente':'YOUTUBE_DATA_API_V3'})
                    ids_actualizados.add(vid)
            except Exception as exc:
                errores.append({'proveedor':'YOUTUBE_API_VIDEOS',
                                'error':f'{type(exc).__name__}: {str(exc)[:150]}'})
        youtube_estado = 'PARCIAL' if youtube_pendientes or any(e['proveedor'].startswith('YOUTUBE') for e in errores) else 'COMPLETO'
    elif max_youtube == 0:
        youtube_estado = 'DESHABILITADO'

    # --- CONTABILIDAD V5 CORREGIDA ---
    ahora = datetime.now(timezone.utc)
    # Para claridad: pendientes reales solo Brave (DDG limitado va a no_intentables)
    pendientes_brave_reales = max(0, consultas_unicas_planificadas - len(seleccion)) if max_brave else 0
    # si DDG LIMITADO, no hay pendientes DDG reintentables
    pendientes_ddg_reintentables = (len(pendientes_ddg) + int(ddg_consulta_incompleta is not None)) if estado_ddg not in ('LIMITADO',) and max_ddg else 0
    ddg_no_ejecutadas = (consultas_unicas_planificadas - ddg_completadas) if estado_ddg == 'LIMITADO' else 0

    origenes_counter = Counter(x['origen'] for x in urls.values())
    origenes_sociales = {k:v for k,v in origenes_counter.items() if any(k == r or (k or '').endswith('.' + r) for r in REDES)}

    resultado = {
        'modo': 'DDG_REAL_CON_OTROS_PROVEEDORES_SIMULADOS',
        'simulado': True,
        'solicitudes_externas': sum(d.get('solicitudes_http', 0) for d in diagnosticos_ddg),
        'version': 'LAB_DISCOVERY_V11_META_ULTIMA_INTERVENCION',
        'nueva_busqueda': True,
        'fecha_ejecucion_utc': ahora.isoformat(),
        'marco': texto,
        'periodo': {'desde': desde.isoformat(), 'hasta': hasta.isoformat()},
        'proveedor': 'BRAVE_WEB + DUCKDUCKGO_HTML + YOUTUBE_DATA_API_V3 + FACEBOOK/INSTAGRAM/X_INDEXADOS',
        # compatibilidad V4
        'solicitudes_exitosas': sum(exito.values()),
        'solicitudes_intentadas': sum(intentos.values()),
        'solicitudes_por_proveedor': dict(intentos),
        'consultas_planificadas': consultas_unicas_planificadas + youtube_planificadas + sum(a.get('planificadas',0) for a in redes_auditoria.values()),
        'consultas_ejecutadas': registros + youtube_registros,
        # V5 contabilidad clara
        'consultas_unicas_planificadas': consultas_unicas_planificadas,
        'consultas_unicas_ejecutadas_brave': len(seleccion),
        'consultas_unicas_ejecutadas_ddg': ddg_completadas,
        'consultas_unicas_pendientes_brave': pendientes_brave_reales,
        'consultas_no_intentables_por_limitacion': {'DUCKDUCKGO_HTML': ddg_no_ejecutadas},
        'consultas_completadas_ddg': ddg_completadas,
        'consulta_ddg_incompleta': ddg_consulta_incompleta,
        'paginas_pendientes_ddg': bool(ddg_consulta_incompleta and estado_ddg == 'PRESUPUESTO_AGOTADO'),
        'consultas_pendientes': pendientes_brave_reales + pendientes_ddg_reintentables + youtube_pendientes + sum(a.get('pendientes',0) for a in redes_auditoria.values()), # solo reintentables
        'pendientes_por_proveedor': {'DUCKDUCKGO_HTML': pendientes_ddg_reintentables, 'BRAVE_WEB': pendientes_brave_reales, 'YOUTUBE_API_SEARCH':youtube_pendientes, 'FACEBOOK_INDEXADO_BRAVE':redes_auditoria['FACEBOOK'].get('pendientes',0), 'INSTAGRAM_INDEXADO_BRAVE':redes_auditoria['INSTAGRAM'].get('pendientes',0), 'X_INDEXADO_BRAVE':redes_auditoria['X'].get('pendientes',0)},
        'cobertura_parcial': bool(pendientes_brave_reales or pendientes_ddg_reintentables or ddg_no_ejecutadas or (max_ddg and estado_ddg != 'AGOTADO') or errores or youtube_pendientes or any(a.get('estado') == 'PARCIAL' for a in redes_auditoria.values()) or (max_youtube and youtube_estado != 'COMPLETO')),
        'cobertura_incompleta': {'DDG_LIMITADO': estado_ddg == 'LIMITADO', 'DDG_PARCIAL': estado_ddg != 'AGOTADO' and bool(max_ddg), 'BRAVE_PARCIAL': bool(pendientes_brave_reales or any(e.get('proveedor') == 'BRAVE_WEB' for e in errores)), 'YOUTUBE_PARCIAL': bool(max_youtube and youtube_estado != 'COMPLETO')},
        'cobertura_redes': cobertura_redes,
        'fase_redes': 'BRAVE_INDEXACION_YOUTUBE_API_NATIVA_FACEBOOK_INSTAGRAM_X_INDEXADOS',
        'adaptadores_redes': redes_auditoria,
        'respuestas_brutas_redes': respuestas_brutas_redes,
        'consultas_historicas_redes': list({(r.get('proveedor'), r.get('consulta')): r for r in
            ((anterior or {}).get('consultas_historicas_redes', []) +
             [r for r in (anterior or {}).get('consultas_ejecutadas', []) if r.get('proveedor') in ('FACEBOOK_INDEXADO_BRAVE', 'INSTAGRAM_INDEXADO_BRAVE', 'X_INDEXADO_BRAVE')] +
             [r for r in registros if r.get('proveedor') in ('FACEBOOK_INDEXADO_BRAVE', 'INSTAGRAM_INDEXADO_BRAVE', 'X_INDEXADO_BRAVE')])
             if isinstance(r, dict) and r.get('consulta')}.values()),
        'total_urls_unicas': len(urls),
        'origenes': dict(origenes_counter),
        'origenes_sociales': origenes_sociales,
        'total_social_links': sum(origenes_sociales.values()),
        'errores': errores,
        'avisos': avisos + ['DuckDuckGo usa HTTP real; Brave, YouTube, redes y recuperación documental siguen siendo simulados.'],
        'estado_ddg': estado_ddg,
        'diagnosticos_ddg': diagnosticos_ddg,
        'publicaciones': list(urls.values()),
        'historico': {'corte_previo': (anterior or {}).get('fecha_ejecucion_utc'),
                     'urls_heredadas':heredadas, 'urls_unicas_actuales':len(urls),
                     'nuevos_videos_youtube':len(nuevas_youtube - set((youtube.identificar_video(x.get('url','')) for x in (anterior or {}).get('publicaciones', [])))) if max_youtube and youtube_key else 0},
        'youtube_api': {'estado':youtube_estado, 'consultas_planificadas':youtube_planificadas,
                        'consultas_intentadas':youtube_intentos, 'consultas_pendientes_o_paginas':youtube_pendientes,
                        'videos_actualizados':len(ids_actualizados), 'solicitudes_videos_estimadas':youtube_detalles_intentos,
                        'cuota_search_estimada':youtube_intentos*100},
        'lecturas_youtube':lecturas_youtube,
        'advertencia': 'MODO MIXTO: DuckDuckGo real; otros proveedores y recuperación documental simulados. Los candidatos no constituyen evidencia EMM acreditada.'
    }

    for doc in resultado['publicaciones']:
        doc['simulado'] = 'DUCKDUCKGO_HTML' not in doc.get('proveedores', [])

    # L4.9.2.9: segunda pasada de documentos, sin decidir EMM ni alterar candidatos.
    # Solo HTML público para WEB; YouTube usa detalles nativos ya obtenidos.
    presupuesto_documental = payload.get('max_documentos_enriquecer', 8)
    if type(presupuesto_documental) is not int or not 0 <= presupuesto_documental <= 100:
        raise ValueError('max_documentos_enriquecer fuera de rango (0..100)')
    def _youtube_documental(doc):
        info = doc.get('youtube') or {}
        return {
            'titulo': info.get('titulo'), 'descripcion': info.get('descripcion'),
            'cuerpo': None, 'detalles': {'duracion_iso8601': info.get('duracion_iso8601'),
                                      'canal_id': info.get('canal_id')},
            'comentarios': None, 'autor': info.get('canal'),
            'fecha_publicacion': info.get('publicado_en'), 'metricas': None,
            'evidencia': {'proveedor': 'YOUTUBE_DATA_API_V3',
                         'identidad_evidencia': doc.get('identidad_evidencia')},
            'limitaciones': ['No se recuperaron comentarios ni transcripción; conteos históricos permanecen separados']}
    # Reutilizar la identidad de consolidación ya calculada.
    # No modificar las publicaciones del inventario ni los snapshots históricos.
    candidatos_doc = [
        {
            **doc,
            'id': clave,
        }
        for clave, doc in urls.items()
    ]
    # Priorizar WEB para el presupuesto HTTP; los metadatos YouTube nativos
    # ya recuperados se procesan TODOS sin consumir solicitudes nuevas.
    # Mantener todas las URLs en el inventario y sin decisión EMM.
    candidatos_doc = sorted(candidatos_doc, key=lambda d: (
        fuente_url(d.get('url') or '') != 'WEB', d.get('url') or ''))
    # Diario incremental independiente del snapshot final. Cada linea es una ficha
    # completa; la ultima entrada por URL prevalece y los errores son reintentables.
    # Un id explicito permite reanudar una ejecucion interrumpida; sin id se crea
    # una ejecucion nueva. No se eliminan historicos automaticamente.
    identificador_ejecucion = payload.get('id_ejecucion_documental')
    if identificador_ejecucion is not None and (
        not isinstance(identificador_ejecucion, str) or
        not identificador_ejecucion.isascii() or
        not 1 <= len(identificador_ejecucion) <= 80 or
        any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in identificador_ejecucion)
    ):
        raise ValueError('id_ejecucion_documental invalido')
    identificador_ejecucion = identificador_ejecucion or ahora.strftime('%Y%m%dT%H%M%S%fZ')
    firma = sha256(json.dumps({'marco': texto, 'periodo': resultado['periodo']},
                            sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()
    DESTINO.mkdir(parents=True, exist_ok=True)
    diario = DESTINO / f'documental_{firma[:16]}_{identificador_ejecucion}.jsonl'
    previas = {}
    if diario.exists():
        with diario.open('r', encoding='utf-8') as archivo:
            for linea in archivo:
                try:
                    registro = json.loads(linea)
                except json.JSONDecodeError:
                    continue  # linea truncada tras interrupcion
                if registro.get('firma') != firma:
                    raise ValueError('Diario documental pertenece a otro Marco o periodo')
                ficha = registro.get('ficha')
                if isinstance(ficha, dict) and ficha.get('url_solicitada'):
                    previas[ficha['url_solicitada']] = ficha

    def _persistir_ficha(ficha):
        registro = {'firma': firma, 'ficha': ficha}
        with diario.open('a', encoding='utf-8') as archivo:
            archivo.write(json.dumps(registro, ensure_ascii=False) + '\n')
            archivo.flush()
            os.fsync(archivo.fileno())

    resultado['recuperacion_documental'] = enriquecer(
        candidatos_doc, obtener_html=documental_obtener_html or descargar_html,
        adaptadores_nativos={'YOUTUBE': _youtube_documental},
        max_solicitudes=presupuesto_documental, al_guardar=_persistir_ficha,
        fichas_previas=previas)
    resultado['recuperacion_documental']['diario_incremental'] = str(diario)
    resultado['recuperacion_documental']['resumen'] = {
        'total_candidatos': len(candidatos_doc),
        'estados': dict(Counter(f['estado_recuperacion'] for f in resultado['recuperacion_documental']['documentos'])),
        'solicitudes_http': resultado['recuperacion_documental']['solicitudes_intentadas'],
        'documentos_con_texto': sum(bool(any(f['contenido'].get(k) for k in
            ('titulo', 'descripcion', 'cuerpo', 'comentarios')))
            for f in resultado['recuperacion_documental']['documentos']),
        'advertencia': 'La recuperación no acredita el Marco EMM'}

    DESTINO.mkdir(parents=True, exist_ok=True)
    ruta = DESTINO / f"busqueda_integrada_{ahora.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    temporal = ruta.with_suffix('.json.tmp')
    with temporal.open('x', encoding='utf-8') as archivo:
        json.dump(resultado, archivo, ensure_ascii=False, indent=2)
        archivo.flush()
        os.fsync(archivo.fileno())
    temporal.replace(ruta)
    resultado['auditoria'] = str(ruta.relative_to(DESTINO.parents[2]))
    return resultado
