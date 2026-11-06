"""Descubrimiento exclusivamente con la API oficial Brave Search."""
from collections import Counter, deque
from datetime import date, datetime, timezone
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from app.laboratorio.motor_v2.contratos import Marco
from app.laboratorio.motor_v2.recuperacion_documental_enriquecida import enriquecer
from app.laboratorio.motor_v2.evaluador_contextual import evaluar_publicacion
from app.laboratorio.interfaz_v2 import descubrimiento_brave as brave

# No heredar datos simulados o de proveedores anteriores.
DESTINO = Path(__file__).resolve().parents[3] / 'datos' / 'ejecuciones' / 'descubrimiento_brave'
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


def ejecutar_busqueda(payload, *, brave_consultar=None, documental_obtener_html=None):
    """Descubrir con Brave, recuperar HTML y evaluar sin descartar candidatos."""
    if not isinstance(payload, dict):
        raise ValueError('El payload debe ser un objeto JSON')
    texto = payload.get('marco')
    if not isinstance(texto, str) or not 0 < len(texto) <= 4000:
        raise ValueError('Marco inválido')
    marco = Marco.desde_input(texto)
    periodo = payload.get('periodo')
    try:
        if not isinstance(periodo, dict):
            raise ValueError
        desde, hasta = date.fromisoformat(periodo['desde']), date.fromisoformat(periodo['hasta'])
        if desde > hasta or hasta > date.today():
            raise ValueError
    except (ValueError, TypeError, KeyError):
        raise ValueError('Período inválido o fecha futura') from None
    max_brave = payload.get('max_brave', 50)
    if type(max_brave) is not int or not 1 <= max_brave <= 50:
        raise ValueError('max_brave fuera de rango (1..50)')
    max_documentos = payload.get('max_documentos_enriquecer')
    if max_documentos is not None and (type(max_documentos) is not int or not 0 <= max_documentos <= 1000):
        raise ValueError('max_documentos_enriquecer fuera de rango (0..1000 o null para todas)')
    clave = brave.clave_brave()
    if brave_consultar is None and not clave:
        raise brave.BraveError('brave_no_configurado', 'Falta BRAVE_API_KEY o BRAVE_SEARCH_API_KEY en el entorno o en .env.', 503)
    periodo = {'desde': desde.isoformat(), 'hasta': hasta.isoformat()}
    propuestas = planificar(marco)
    seleccion = _seleccionar_brave_v5(propuestas, max_brave)
    urls, registros, errores = {}, [], []
    anterior = None
    if DESTINO.is_dir():
        for ruta in sorted(DESTINO.glob('busqueda_integrada_*.json'), reverse=True):
            try:
                candidato = json.loads(ruta.read_text(encoding='utf-8'))
                if candidato.get('modo') == 'BRAVE_SEARCH_REAL' and candidato.get('marco') == texto and candidato.get('periodo') == periodo:
                    anterior = candidato
                    break
            except (ValueError, OSError, AttributeError):
                continue
    for doc in (anterior or {}).get('publicaciones', []):
        if isinstance(doc, dict):
            url = brave._normalizar_url(doc.get('url'))
            if url and not doc.get('simulado') and doc.get('proveedores') == ['BRAVE_WEB']:
                urls[url] = doc
    heredadas = len(urls)
    consultar = brave_consultar or brave._brave
    intentadas = exitosas = 0
    for tipo, consulta in seleccion:
        intentadas += 1
        try:
            respuesta = consultar(consulta, periodo['desde'], periodo['hasta'], clave)
        except brave.BraveError as exc:
            errores.append({'proveedor': 'BRAVE_WEB', 'consulta': consulta,
                            'codigo': exc.codigo, 'error': str(exc)})
            # No agotar cuota ni repetir credenciales inválidas tras un fallo.
            break
        resultados = (respuesta.get('web') or {}).get('results') or []
        nuevas = 0
        for item in resultados:
            url = brave._normalizar_url(item.get('url'))
            if not url:
                continue
            if url not in urls:
                urls[url] = {'url': url, 'titulo': item.get('title') or url,
                             'descripcion': item.get('description') or '',
                             'fecha_indice': item.get('page_age'), 'origen': urlsplit(url).hostname,
                             'consultas_origen': [], 'proveedores': ['BRAVE_WEB'], 'simulado': False}
                nuevas += 1
            if consulta not in urls[url]['consultas_origen']:
                urls[url]['consultas_origen'].append(consulta)
        exitosas += 1
        registros.append({'proveedor': 'BRAVE_WEB', 'estrategia': tipo, 'consulta': consulta,
                          'pagina': 1, 'resultados': len(resultados), 'nuevas_urls': nuevas})
    pendientes = max(0, len(propuestas) - exitosas)
    ahora = datetime.now(timezone.utc)
    avisos = ['Se consulta solo la primera página de cada consulta (hasta 20 resultados). No se presume cobertura exhaustiva.']
    if errores:
        avisos.append('La búsqueda de Brave se detuvo por un error; se conservaron los resultados disponibles.')
    recuperacion = enriquecer(list(urls.values()), obtener_html=documental_obtener_html,
                             max_solicitudes=max_documentos)
    publicaciones = recuperacion.pop('publicaciones')
    for indice, publicacion in enumerate(publicaciones, 1):
        publicacion['evaluacion_contextual'] = evaluar_publicacion(texto, publicacion)
        publicacion['score_emm'] = publicacion['evaluacion_contextual']['score_emm']
        logging.getLogger(__name__).info('[EMM] %s/%s score_emm=%.1f %s', indice, len(publicaciones), publicacion['score_emm'], publicacion.get('titulo', ''))
        if publicacion['recuperacion']['estado'] == 'ERROR':
            error = publicacion['recuperacion']['error']
            errores.append({'proveedor': 'RECUPERACION_DOCUMENTAL', 'url': publicacion['url'],
                            'codigo': error['codigo'], 'error': error['mensaje']})
    if recuperacion['pendientes']:
        avisos.append('Hay documentos pendientes por presupuesto de recuperación; se evaluaron con título y descripción.')
    if any(p['recuperacion']['estado'] in ('ERROR', 'SIN_TEXTO') for p in publicaciones):
        avisos.append('Algunos documentos no aportaron cuerpo; su evaluación usa los textos disponibles.')
    resultado = {
        'modo': 'BRAVE_SEARCH_REAL', 'simulado': False, 'proveedor': 'BRAVE_WEB',
        'version': 'LAB_BRAVE_RECUPERACION_EMM_V1', 'nueva_busqueda': True,
        'fecha_ejecucion_utc': ahora.isoformat(), 'marco': texto, 'periodo': periodo,
        'solicitudes_exitosas': exitosas, 'solicitudes_intentadas': intentadas,
        'solicitudes_externas': intentadas + recuperacion['solicitudes_intentadas'],
        'solicitudes_por_proveedor': {'BRAVE_WEB': intentadas, 'RECUPERACION_DOCUMENTAL': recuperacion['solicitudes_intentadas']},
        'consultas_planificadas': len(propuestas), 'consultas_unicas_planificadas': len(propuestas),
        'consultas_ejecutadas': registros, 'consultas_pendientes': pendientes,
        'pendientes_por_proveedor': {'BRAVE_WEB': pendientes},
        'cobertura_parcial': True,
        'total_urls_unicas': len(urls), 'origenes': dict(Counter(d['origen'] for d in urls.values())),
        'publicaciones': publicaciones, 'errores': errores, 'avisos': avisos,
        'recuperacion_documental': recuperacion,
        'advertencia': 'Evaluación EMM heurística sobre textos disponibles, sin descarte automático. La fecha de índice no acredita la fecha de publicación.',
        'historico': {'corte_previo': (anterior or {}).get('fecha_ejecucion_utc'),
                      'urls_heredadas': heredadas, 'urls_unicas_actuales': len(urls)},
    }
    DESTINO.mkdir(parents=True, exist_ok=True)
    ruta = DESTINO / f"busqueda_integrada_{ahora.strftime('%Y%m%dT%H%M%S%fZ')}.json"
    resultado['auditoria'] = str(ruta.relative_to(DESTINO.parents[2]))
    temporal = ruta.with_suffix('.json.tmp')
    with temporal.open('x', encoding='utf-8') as archivo:
        json.dump(resultado, archivo, ensure_ascii=False, indent=2)
        archivo.flush()
        os.fsync(archivo.fileno())
    temporal.replace(ruta)
    return resultado
