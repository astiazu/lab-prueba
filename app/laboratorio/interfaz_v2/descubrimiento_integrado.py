"""Descubrimiento exclusivamente con la API oficial Brave Search."""
from collections import Counter
from datetime import date, datetime, timezone
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from app.laboratorio.motor_v2.contratos import Marco
from app.laboratorio.interfaz_v2.planificador_consultas import planificar_consultas
from app.laboratorio.motor_v2.recuperacion_documental_enriquecida import enriquecer
from app.laboratorio.motor_v2.evaluador_contextual import evaluar_publicacion
from app.laboratorio.interfaz_v2 import descubrimiento_brave as brave
from app.laboratorio.interfaz_v2 import descubrimiento_youtube as youtube

# No heredar datos simulados o de proveedores anteriores.
DESTINO = Path(__file__).resolve().parents[3] / 'datos' / 'ejecuciones' / 'descubrimiento_brave'
def planificar(marco):
    """Contexto, territorio y exploración, con alternativas del Marco."""
    return planificar_consultas(marco)


def ejecutar_busqueda(payload, *, brave_consultar=None, documental_obtener_html=None, youtube_detalles=None):
    """Descubrir con Brave, recuperar HTML y evaluar y separar candidatos sin perder trazabilidad."""
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
    paginas_brave = payload.get('paginas_brave', 3)
    if type(paginas_brave) is not int or not 1 <= paginas_brave <= 10:
        raise ValueError('paginas_brave fuera de rango (1..10)')
    max_documentos = payload.get('max_documentos_enriquecer')
    if max_documentos is not None and (type(max_documentos) is not int or not 0 <= max_documentos <= 1000):
        raise ValueError('max_documentos_enriquecer fuera de rango (0..1000 o null para todas)')
    clave = brave.clave_brave()
    if brave_consultar is None and not clave:
        raise brave.BraveError('brave_no_configurado', 'Falta BRAVE_API_KEY o BRAVE_SEARCH_API_KEY en el entorno o en .env.', 503)
    periodo = {'desde': desde.isoformat(), 'hasta': hasta.isoformat()}
    propuestas = planificar(marco)
    plan_consultas = [{'estrategia': tipo, 'consulta': q} for tipo, q in propuestas]
    urls, registros, errores = {}, [], []
    anterior = None
    if DESTINO.is_dir():
        for ruta in sorted(DESTINO.glob('busqueda_integrada_*.json'), reverse=True):
            try:
                candidato = json.loads(ruta.read_text(encoding='utf-8'))
                if candidato.get('modo') == 'BRAVE_SEARCH_REAL' and candidato.get('marco') == texto and candidato.get('periodo') == periodo and candidato.get('plan_consultas') == plan_consultas:
                    anterior = candidato
                    break
            except (ValueError, OSError, AttributeError):
                continue
    inventario_anterior = ((anterior or {}).get('publicaciones', [])
                           + (anterior or {}).get('publicaciones_descartadas', []))
    for doc in inventario_anterior:
        if isinstance(doc, dict):
            url = brave._normalizar_url(doc.get('url'))
            if url and not doc.get('simulado') and doc.get('proveedores') == ['BRAVE_WEB']:
                urls[url] = doc
    heredadas = len(urls)
    consultar = brave_consultar or brave._brave
    intentadas = exitosas = 0
    agotadas, firmas = set(), {}
    detener = False
    for pagina in range(paginas_brave):
        for tipo, consulta in propuestas:
            if consulta in agotadas or intentadas >= max_brave:
                continue
            intentadas += 1
            try:
                if pagina == 0:
                    respuesta = consultar(consulta, periodo['desde'], periodo['hasta'], clave)
                else:
                    respuesta = consultar(consulta, periodo['desde'], periodo['hasta'], clave, offset=pagina)
            except brave.BraveError as exc:
                errores.append({'proveedor': 'BRAVE_WEB', 'consulta': consulta, 'pagina': pagina + 1,
                                'codigo': exc.codigo, 'error': str(exc)})
                detener = True
                break
            resultados = (respuesta.get('web') or {}).get('results') or []
            nuevas = 0
            fecha_hallazgo = datetime.now(timezone.utc).isoformat()
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
                urls[url].setdefault('hallazgos_brave', []).append({
                    'consulta': consulta, 'estrategia': tipo, 'pagina': pagina + 1,
                    'url_descubierta': item.get('url'), 'recuperado_en': fecha_hallazgo})
            exitosas += 1
            registros.append({'proveedor': 'BRAVE_WEB', 'estrategia': tipo, 'consulta': consulta,
                              'pagina': pagina + 1, 'resultados': len(resultados), 'nuevas_urls': nuevas})
            firma = tuple(sorted(item.get('url', '') for item in resultados))
            repetida = firma in firmas.setdefault(consulta, set())
            firmas[consulta].add(firma)
            mas = (respuesta.get('query') or {}).get('more_results_available', len(resultados) >= 20)
            if not resultados or not mas or repetida:
                agotadas.add(consulta)
        if detener or intentadas >= max_brave:
            break
    pendientes = len(propuestas) - len(agotadas)
    ahora = datetime.now(timezone.utc)
    avisos = ['Estrategia escalonada con hasta 20 resultados por página. No se garantiza cobertura exhaustiva.']
    if errores:
        avisos.append('La búsqueda de Brave se detuvo por un error; se conservaron los resultados disponibles.')
    datos_youtube = youtube.enriquecer_publicaciones(list(urls.values()), consultar_detalles=youtube_detalles)
    errores.extend(datos_youtube['errores'])
    recuperacion = enriquecer(datos_youtube['publicaciones'], obtener_html=documental_obtener_html,
                             max_solicitudes=max_documentos)
    publicaciones = recuperacion.pop('publicaciones')
    for indice, publicacion in enumerate(publicaciones, 1):
        publicacion['evaluacion_contextual'] = evaluar_publicacion(texto, publicacion)
        publicacion['score_emm'] = publicacion['evaluacion_contextual']['score_emm']
        publicacion['ubicacion_entidad'] = publicacion['evaluacion_contextual']['ubicacion_entidad']
        logging.getLogger(__name__).info('[EMM] %s/%s score_emm=%.1f %s', indice, len(publicaciones), publicacion['score_emm'], publicacion.get('titulo', ''))
        if publicacion['recuperacion']['estado'] == 'ERROR':
            error = publicacion['recuperacion']['error']
            errores.append({'proveedor': 'RECUPERACION_DOCUMENTAL', 'url': publicacion['url'],
                            'codigo': error['codigo'], 'error': error['mensaje']})
    if recuperacion['pendientes']:
        avisos.append('Hay documentos pendientes por presupuesto de recuperación; se evaluaron con título y descripción.')
    if any(p['recuperacion']['estado'] in ('ERROR', 'SIN_TEXTO') for p in publicaciones):
        avisos.append('Algunos documentos no aportaron cuerpo; su evaluación usa los textos disponibles.')
    publicaciones.sort(key=lambda p: p['score_emm'], reverse=True)
    descartadas = [p for p in publicaciones if p['score_emm'] < 0.5]
    aceptadas = [p for p in publicaciones if p['score_emm'] >= 0.5]
    resultado = {
        'modo': 'BRAVE_SEARCH_REAL', 'simulado': False, 'proveedor': 'BRAVE_WEB',
        'version': 'LAB_EMM_FILTRADO_V4', 'nueva_busqueda': True,
        'fecha_ejecucion_utc': ahora.isoformat(), 'marco': texto, 'periodo': periodo,
        'plan_consultas': plan_consultas, 'paginas_brave_maximas': paginas_brave,
        'solicitudes_exitosas': exitosas, 'solicitudes_intentadas': intentadas,
        'solicitudes_externas': intentadas + recuperacion['solicitudes_intentadas'] + datos_youtube['solicitudes_intentadas'],
        'solicitudes_por_proveedor': {'BRAVE_WEB': intentadas, 'RECUPERACION_DOCUMENTAL': recuperacion['solicitudes_intentadas'], 'YOUTUBE_DATA_API_V3': datos_youtube['solicitudes_intentadas']},
        'consultas_planificadas': len(propuestas), 'consultas_unicas_planificadas': len(propuestas),
        'consultas_ejecutadas': registros, 'consultas_pendientes': pendientes,
        'pendientes_por_proveedor': {'BRAVE_WEB': pendientes},
        'cobertura_parcial': True,
        'total_urls_unicas': len(urls), 'origenes': dict(Counter(d['origen'] for d in urls.values())),
        'publicaciones': aceptadas, 'publicaciones_descartadas': descartadas,
        'total_publicaciones_aceptadas': len(aceptadas),
        'total_publicaciones_descartadas': len(descartadas),
        'errores': errores, 'avisos': avisos,
        'recuperacion_documental': recuperacion,
        'youtube_api': {k: v for k, v in datos_youtube.items() if k != 'publicaciones'},
        'advertencia': 'Evaluación EMM heurística sobre textos disponibles, resultados principales con score >= 0.5; descartes conservados para auditoría. La fecha de índice no acredita la fecha de publicación.',
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
