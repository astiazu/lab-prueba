"""Estado y clasificación compartidos por la búsqueda en vivo y el replay sin red."""
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from app.laboratorio.motor_v2.evaluador_contextual import evaluar_publicacion


def normalizar_url(url):
    if not isinstance(url, str):
        raise ValueError('Cada publicación requiere una URL HTTP')
    try:
        p = urlsplit(url)
        if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
            raise ValueError
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path or '/', p.query, ''))
    except ValueError:
        raise ValueError('Cada publicación requiere una URL HTTP válida') from None


@dataclass
class Inventario:
    activas: dict = field(default_factory=dict)
    archivadas: dict = field(default_factory=dict)
    heredadas_aceptadas: set = field(default_factory=set)
    heredadas_descartadas: set = field(default_factory=set)
    nuevas: set = field(default_factory=set)
    archivadas_reencontradas: set = field(default_factory=set)

    @classmethod
    def desde_salida(cls, salida):
        if not isinstance(salida, dict):
            raise ValueError('La corrida debe ser un objeto JSON')
        grupos = ('publicaciones', 'publicaciones_descartadas', 'publicaciones_archivadas')
        if not any(g in salida for g in grupos):
            raise ValueError('La corrida no contiene publicaciones')
        inventario = cls()
        for grupo in grupos:
            registros = salida.get(grupo, [])
            if not isinstance(registros, list):
                raise ValueError(f'{grupo} debe ser una lista')
            for original in registros:
                if not isinstance(original, dict):
                    raise ValueError('Una publicación no es un objeto JSON')
                doc = deepcopy(original)
                url = normalizar_url(doc.get('url'))
                doc['url'] = url
                if doc.get('archivado') is True or grupo == 'publicaciones_archivadas':
                    doc['archivado'] = True
                    inventario.archivadas[url] = doc
                else:
                    doc.setdefault('titulo', url)
                    doc.setdefault('descripcion', '')
                    doc.setdefault('origen', urlsplit(url).hostname)
                    doc.setdefault('consultas_origen', [])
                    inventario.activas[url] = doc
                    conjunto = inventario.heredadas_aceptadas if grupo == 'publicaciones' else inventario.heredadas_descartadas
                    conjunto.add(url)
        for url in inventario.archivadas:
            inventario.activas.pop(url, None)
            inventario.heredadas_aceptadas.discard(url)
            inventario.heredadas_descartadas.discard(url)
        inventario.heredadas_descartadas -= inventario.heredadas_aceptadas
        return inventario


def cerrar_corrida(inventario, publicaciones, marco, politica, metadatos):
    """Evaluar una vez los activos, podar y medir sin modificar registros de entrada."""
    ahora = datetime.now(timezone.utc).isoformat()
    aceptadas, descartadas, archivos_nuevos = [], [], []
    for indice, original in enumerate(publicaciones, 1):
        doc = deepcopy(original)
        evaluacion = evaluar_publicacion(marco, doc, politica)
        doc.update(evaluacion_contextual=evaluacion, score_emm=evaluacion['score_emm'],
                   motivo_descarte=evaluacion['motivo_descarte'],
                   ubicacion_entidad=evaluacion['ubicacion_entidad'], archivado=False)
        logging.getLogger(__name__).info('[EMM] %s/%s score_emm=%s %s', indice, len(publicaciones), doc['score_emm'], doc.get('titulo', ''))
        if doc['score_emm'] >= politica.umbral_aceptacion:
            aceptadas.append(doc)
        elif doc['score_emm'] < politica.umbral_archivado:
            doc.update(archivado=True, archivado_en=ahora)
            archivos_nuevos.append(doc)
        else:
            descartadas.append(doc)
    aceptadas.sort(key=lambda p: p['score_emm'], reverse=True)
    descartadas.sort(key=lambda p: p['score_emm'], reverse=True)
    archivadas = deepcopy(inventario.archivadas)
    for doc in archivos_nuevos:
        archivadas[doc['url']] = doc
    activas = aceptadas + descartadas
    heredadas = inventario.heredadas_aceptadas | inventario.heredadas_descartadas
    reales = sum(p['score_emm'] >= politica.umbral_real for p in aceptadas)
    cantidades = {
        'urls_nuevas_esta_corrida': len(inventario.nuevas),
        'urls_heredadas_aceptadas_input': len(inventario.heredadas_aceptadas),
        'urls_heredadas_aceptadas_replay': sum(p['url'] in heredadas for p in aceptadas),
        'urls_heredadas_descartadas_activas': len(inventario.heredadas_descartadas),
        'urls_heredadas_archivadas': len(inventario.archivadas),
        'urls_reencontradas_archivadas': len(inventario.archivadas_reencontradas),
        'urls_archivadas_esta_corrida': len(archivos_nuevos),
        'urls_nuevas_activas': sum(p['url'] in inventario.nuevas for p in activas),
        'urls_heredadas_activas_al_cierre': sum(p['url'] in heredadas for p in activas),
        'aceptadas_reales': reales, 'aceptadas_marginales': len(aceptadas) - reales,
        'total_urls_activas': len(activas), 'total_urls_archivadas': len(archivadas),
        'ratio_aceptadas_activas': len(aceptadas) / len(activas) if activas else None,
    }
    return {
        **metadatos, **cantidades,
        'version': 'LAB_EMM_IDENTIDAD_JERARQUICA_V7', 'fecha_ejecucion_utc': ahora,
        'marco': '; '.join((', '.join(marco.entidades), ', '.join(marco.contextos), ', '.join(marco.territorios))),
        'politica_emm': politica.como_dict(),
        'publicaciones': aceptadas, 'publicaciones_descartadas': descartadas,
        'publicaciones_archivadas': list(archivadas.values()),
        'total_publicaciones_aceptadas': len(aceptadas), 'total_publicaciones_descartadas': len(descartadas),
        'total_urls_unicas': len(activas), 'total_urls_descubiertas': len(publicaciones) + len(inventario.archivadas),
        'origenes': dict(Counter(p['origen'] for p in activas)),
        'historico': {'corte_previo': metadatos.get('corte_previo'), 'urls_heredadas': len(heredadas), 'urls_unicas_actuales': len(activas)},
        'advertencia': 'Evaluación EMM heurística. El denominador contiene solo URLs activas; los archivos fríos se conservan sin reprocesar.',
    }


def guardar_salida(resultado, destino):
    """Snapshot nuevo con nombre único, sin reescribir una corrida anterior."""
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    momento = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    ruta = destino / f'busqueda_integrada_{momento}_{uuid4().hex[:8]}.json'
    resultado['auditoria'] = str(ruta)
    temporal = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=destino, suffix='.tmp', delete=False) as archivo:
            temporal = Path(archivo.name)
            json.dump(resultado, archivo, ensure_ascii=False, indent=2, allow_nan=False)
            archivo.flush()
            os.fsync(archivo.fileno())
        temporal.replace(ruta)
    finally:
        if temporal is not None:
            temporal.unlink(missing_ok=True)
    return ruta
