# Laboratorio EMM v2

Instalar desarrollo con `python -m pip install -r requirements-dev.txt` e iniciar
el servidor con `python run.py`. Las credenciales se cargan de `.env`, excluido de
Git. Se admiten BRAVE_API_KEY o BRAVE_SEARCH_API_KEY y YOUTUBE_API_KEY. Nunca se
imprimen claves ni URLs autenticadas.

## Marco universal y contextos

El formato es `Entidad; Contexto; Territorio local, Territorio regional, Territorio amplio`.
La primera entidad es la principal. Los territorios están ordenados de mayor a
menor especificidad, por decisión del usuario. No hay un campo adicional para
clasificarlos ni listas de lugares, personas o profesiones en el motor.

Cada contexto separado por coma se consulta independientemente: `"Entidad" AND
Contexto`. Solo OR mayúsculo explícito dentro de un contexto genera disyunción.
La búsqueda territorial utiliza las alternativas del Marco y la exploración usa
la entidad sola. `max_brave` limita las peticiones totales (default 50) y
`paginas_brave` las páginas por consulta (default 3). Hay hasta 20 resultados por
página, sin garantía de cobertura exhaustiva. El motor no reescribe contextos por
su significado: no puede determinar compatibilidad semántica mediante vocabularios.

Un Marco reúne atributos de una misma identidad.
Mezclar contextos incompatibles puede premiar coincidencias de identidades distintas.
El motor no decide esa compatibilidad mediante nombres o categorías predefinidos.
Por eso consulta cada contexto por separado y exige OR explícito para disyunción.
El usuario debe separar identidades diferentes en marcos diferentes.

## Política configurable

`motor_v2/politica_emm.py` define parámetros generales. El payload permite
sobrescribirlos mediante `politica_emm`, sin valores específicos de un caso:

| Parámetro | Default |
| --- | ---: |
| peso_entidad | 0.40 |
| peso_contexto | 0.30 |
| peso_territorio | 0.30 |
| score_max_sin_entidad | 0.40 |
| umbral_archivado | 0.30 |
| umbral_aceptacion | 0.50 |
| umbral_real | 0.80 |

Los pesos deben sumar 1, los umbrales deben estar ordenados y el cap sin entidad
principal debe ser inferior al de aceptación. La política completa queda en la salida.

## Scorer y fórmula territorial aprobada

Se evalúan título, descripción, cuerpo y título/descripción nativos de YouTube.
Se compara sin distinguir mayúsculas y conservando acentos, por palabras y frases
completas. No se crea una entidad uniendo fragmentos de campos diferentes. No se
exige que la entidad aparezca en el título ni antes de una posición arbitraria.

Si está la entidad principal, aporta PESO_ENTIDAD; si coincide contexto declarado,
aporta PESO_CONTEXTO. Sin la principal el score final se limita a
SCORE_MAX_SIN_ENTIDAD y se registra el motivo `sin_entidad_principal`.

La fórmula es `PESO_TERRITORIO * ((N - posicion) / N)`, con posición base cero.
No existe normalización triangular. Se recorre **el orden del Marco** y se toma
el primer territorio declarado que aparece en el documento. No se toma el primer
lugar mencionado en el texto y no se suman varios territorios.

| N | Pesos por posición con presupuesto 0.30 |
| --- | --- |
| 1 | 0.30 |
| 2 | 0.30, 0.15 |
| 3 | 0.30, 0.20, 0.10 |
| 4 | 0.30, 0.225, 0.15, 0.075 |

Para cualquier N el primero recibe siempre 0.30 y el score máximo es 1.00.
Ejemplo genérico: Marco `Sector local, Área regional, Zona amplia`; documento
`Zona amplia ... Sector local`. El mejor es `Sector local`, aunque se mencione
más tarde. El motor no valida geografía: ordenar correctamente es responsabilidad
del usuario. Agregar/quitar territorios cambia pesos intermedios, nunca el primero.

Entidad + contexto sin territorio da 0.70 y es una aceptada marginal para revisión
humana con los valores por defecto. Es un caso borde conocido y aprobado. Se usan
floats de doble precisión; los tests comparan con tolerancia absoluta menor a 1e-9.
No se redondea un score antes de compararlo con los umbrales.

`motivo_descarte` es null para aceptadas. Para scores inferiores al umbral se asigna,
en orden: `sin_entidad_principal`, `entidad_homonima` (sin contexto declarado),
`territorio_incorrecto` (entidad/contexto pero sin territorio) o `score_bajo`.
Estas etiquetas describen evidencia léxica, no verifican una biografía externa.
Se conservan componentes, matches, motivos, fuentes y ubicación de la entidad.

## Acumulativo compartido y archivo frío

`motor_v2/acumulativo.py` contiene la clasificación común a live y replay. Al
cerrar cada corrida se archivan solo los descartes con score **estrictamente menor**
a UMBRAL_ARCHIVADO. El límite exacto permanece activo; una aceptada no se archiva.
Cada archivo conserva `archivado: true`, fecha y evidencia en disco. Si Brave
redescubre esa URL, no se descarga, enriquece por API ni evalúa otra vez.

Los snapshots son nuevos e inmutables en `datos/ejecuciones/descubrimiento_brave/`.
El histórico live usa Marco y período; un cambio del plan no pierde el archivo frío.
Un registro previo sin marca de archivo se evalúa una vez antes de clasificarlo.
Un cambio de política no reactiva automáticamente los registros archivados.

La salida distingue `publicaciones`, `publicaciones_descartadas` activas y
`publicaciones_archivadas`. Expone URLs nuevas, heredadas aceptadas, heredadas
descartadas activas y heredadas archivadas, así como aceptadas reales (por score)
y marginales. `total_urls_activas` es el denominador al cierre; se comprueba como
nuevas activas + heredadas aún activas. Los archivos nuevos tampoco inflan ese
denominador. `total_urls_descubiertas` conserva el total de auditoría y
`ratio_aceptadas_activas` es null si no quedan activos.

La UI muestra las categorías, el archivo separado y scores sin redondeo adicional.
Usa el umbral enviado por el servidor; el valor por defecto sigue siendo 0.5.

## Replay sin red ni cuota

```bash
python -m app.laboratorio.replay --replay ruta/corrida.json --marco "Entidad; Contexto; Sector local, Región" --salida datos/replays/resultado.json
```

Sin `--salida`, imprime el JSON completo por stdout. `--politica archivo.json`
permite usar la misma configuración general que el endpoint. No se sobrescribe
el input ni una salida existente. Un archivo ausente o inválido produce un error
JSON por stderr y código de salida distinto de cero, sin generar sustitutos.

El replay lee los tres arrays del input, conserva evidencia y métricas nativas
con sus fechas originales y reevalúa solo activos con el Marco nuevo. No importa
clientes de API, no descarga HTML y no lee credenciales. Los contadores de llamadas
externas son cero. La salida tiene las mismas categorías, política y métricas del
pipeline normal, más `modo: REPLAY_SIN_RED`, Marco de origen y ruta de entrada.
No mejora el texto faltante: la validación depende del contenido realmente guardado.

## Recuperación y fuentes

La descarga live usa urllib y BeautifulSoup, hasta 5000 caracteres del body; ante
fallos conserva el snippet de Brave y su procedencia. YouTube consulta videos ya
descubiertos en lotes de hasta 50 IDs. Las estadísticas ausentes son null. Los
logs HTTP no incluyen claves ni URLs autenticadas. Las fuentes y métodos conservan
la distinción entre API oficial, HTML y snippet.

## Pruebas

`python -m pytest -q` y `npm test`. Las fixtures de unidad usan marcos inventados;
no son validación de una corrida real. La aceptación del caso operativo requiere
replay del archivo original y revisión de sus resultados, sin respuestas armadas.

### Conteos heredados

`urls_heredadas_aceptadas_input` cuenta las URLs aceptadas del archivo de
entrada, antes de reevaluar. `urls_heredadas_aceptadas_replay` cuenta las URLs
heredadas que quedan aceptadas tras evaluar con el Marco actual (también
incluye las que antes estaban descartadas). En una corrida en vivo excluye
las URLs nuevas. Se retira el nombre ambiguo anterior.
`aceptadas_reales + aceptadas_marginales == total_publicaciones_aceptadas`.
Las penalizaciones mantienen la clave JSON `codigo`, sin tilde.
