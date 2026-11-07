"""Reevaluar una corrida guardada sin importar clientes ni realizar llamadas de red."""
import argparse
import json
import sys
from pathlib import Path

from app.laboratorio.motor_v2.acumulativo import Inventario, cerrar_corrida
from app.laboratorio.motor_v2.contratos import Marco
from app.laboratorio.motor_v2.politica_emm import PoliticaEMM
from app.laboratorio.interfaz_v2.planificador_consultas import planificar_consultas


def reprocesar_corrida(entrada, marco_nuevo, politica=None):
    marco = Marco.desde_input(marco_nuevo)
    politica = politica or PoliticaEMM()
    inventario = Inventario.desde_salida(entrada)
    if not isinstance(entrada.get('periodo'), dict):
        raise ValueError('La corrida requiere su período original')
    return cerrar_corrida(inventario, list(inventario.activas.values()), marco, politica, {
        'modo': 'REPLAY_SIN_RED', 'simulado': bool(entrada.get('simulado', False)), 'nueva_busqueda': False,
        'proveedor': entrada.get('proveedor'), 'periodo': entrada['periodo'],
        'marco_origen': entrada.get('marco'), 'corte_previo': entrada.get('fecha_ejecucion_utc'),
        'plan_consultas': [{'estrategia': t, 'consulta': q} for t, q in planificar_consultas(marco)],
        'consultas_ejecutadas': [], 'consultas_planificadas': 0, 'consultas_unicas_planificadas': 0,
        'consultas_pendientes': 0, 'pendientes_por_proveedor': {}, 'paginas_brave_maximas': 0,
        'solicitudes_exitosas': 0, 'solicitudes_intentadas': 0, 'solicitudes_externas': 0,
        'solicitudes_por_proveedor': {'BRAVE_WEB': 0, 'RECUPERACION_DOCUMENTAL': 0, 'YOUTUBE_DATA_API_V3': 0},
        'recuperacion_documental': {'solicitudes_intentadas': 0, 'documentos_con_texto': sum(bool(p.get('cuerpo_extraido')) for p in inventario.activas.values()), 'pendientes': 0},
        'youtube_api': {'solicitudes_intentadas': 0, 'solicitudes_exitosas': 0, 'errores': []},
        'cobertura_parcial': True, 'errores': [],
        'avisos': ['Replay: solo se usa el texto almacenado; no se consulta Brave, YouTube ni HTML. Las métricas nativas conservan su fecha original.'],
    })


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--replay', type=Path, required=True, help='JSON real de una corrida previa')
    parser.add_argument('--marco', required=True, help='Entidad; contexto; territorios de más a menos específico')
    parser.add_argument('--salida', type=Path, help='Archivo nuevo de salida; por defecto, JSON completo en stdout')
    parser.add_argument('--politica', type=Path, help='JSON con parámetros generales de PoliticaEMM')
    args = parser.parse_args(argv)
    try:
        if args.salida and args.salida.exists():
            raise ValueError('El archivo de salida ya existe; no se sobrescribe')
        entrada = json.loads(args.replay.read_text(encoding='utf-8-sig'))
        politica = PoliticaEMM.desde_config(json.loads(args.politica.read_text(encoding='utf-8-sig')) if args.politica else None)
        resultado = reprocesar_corrida(entrada, args.marco, politica)
        resultado['replay_entrada'] = str(args.replay.resolve())
        texto = json.dumps(resultado, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
        if args.salida:
            args.salida.parent.mkdir(parents=True, exist_ok=True)
            with args.salida.open('x', encoding='utf-8') as archivo:
                archivo.write(texto)
            print(str(args.salida))
        else:
            print(texto, end='')
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({'error': {'codigo': 'replay_invalido', 'mensaje': str(exc)}}, ensure_ascii=False), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
