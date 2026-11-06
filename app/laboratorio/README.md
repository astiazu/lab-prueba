# Descubrimiento exclusivo con Brave Search

Instalar desde la raíz del proyecto con `python3 -m pip install -r requirements.txt`.
Iniciar con `python3 run.py` (puerto 8765).

Al iniciar, `python-dotenv` carga el archivo `.env` ubicado junto a `run.py`,
independientemente del directorio de ejecución. Las variables ya definidas en el
proceso tienen prioridad si no están vacías. Una variable `BRAVE_API_KEY` vacía
o con espacios se completa desde el archivo. Se aceptan archivos UTF-8 con o sin
BOM. Si falta la clave, el cliente vuelve a cargar `.env` antes de buscar, incluso
si el servidor se inició sin `run.py` o el archivo se creó después del arranque. Se acepta `BRAVE_API_KEY` o `BRAVE_SEARCH_API_KEY` (el primero tiene prioridad);
`.env.example` documenta su nombre sin contener credenciales. `.env` y sus variantes
locales están excluidos de Git. Nunca incluir claves en commits o logs.

El adaptador `interfaz_v2/descubrimiento_brave.py` consulta exclusivamente
`https://api.search.brave.com/res/v1/web/search` mediante `urllib`, con la clave de
`os.environ.get('BRAVE_API_KEY')` en la cabecera `X-Subscription-Token`.
Usa el período como filtro `freshness=DESDEtoHASTA`, hasta 20 resultados por
consulta, un timeout de 15 segundos y un máximo de 4 MiB por respuesta. Conserva
TLS y el proxy del entorno y no sigue redirecciones con la clave.

`ejecutar_busqueda(payload)` utiliza consultas escalonadas y consolida
las URLs y sus consultas de origen. `max_brave` limita las consultas (1 a 50,
por defecto 50) incluyendo páginas. `paginas_brave` admite de 1 a 10 páginas
por consulta, por defecto 3, de hasta 20 resultados cada una. No se garantiza
cobertura exhaustiva ni un número mínimo de resultados. La fecha del índice tampoco
acredita una fecha de publicación ni admisión EMM.

No se ejecutan DDG ni adaptadores nativos de Facebook/Instagram/X. YouTube API
se utiliza solo para enriquecer videos descubiertos por Brave. Después de Brave se ejecutan
la recuperación documental y la evaluación contextual que se describen abajo.
El planificador incluye exploración por entidad, sin términos temáticos o
restricciones de dominio ajenas al Marco. Los módulos locales de otros proveedores permanecen
inactivos para futuras integraciones; el adaptador y las pruebas DDG se retiraron.
No se generan publicaciones ni métricas simuladas; el histórico exige el mismo
plan de consultas, Marco y período.

Si falta la clave, la API devuelve HTTP 503 con un error JSON. Si Brave falla,
el motor detiene nuevas solicitudes para no repetir errores de autenticación,
cuota o red y devuelve resultados parciales con `errores` y `avisos`, sin exponer
claves o cuerpos de error remotos. Los snapshots se guardan en
`datos/ejecuciones/descubrimiento_brave/` y quedan fuera de Git.

El entorno requiere salida HTTPS hacia `api.search.brave.com`. El borrador de
configuración incluye ese dominio; su publicación es independiente del push de código.

Pruebas: `python3 -m unittest discover -s tests -v` y
`node tests/test_busqueda.cjs`. Los tests usan respuestas controladas sin consumir
la API ni necesitar claves reales.

## Si aparece «Falta BRAVE_API_KEY»

El archivo debe llamarse exactamente `.env` (no `.env.txt`) y estar en la misma
carpeta que `run.py`. La entrada puede llamarse `BRAVE_API_KEY` o `BRAVE_SEARCH_API_KEY`.
El archivo local de otra máquina no se transfiere automáticamente al servidor
ni a este entorno en la nube; se debe configurar en la máquina que ejecuta Python.
No compartir el contenido del archivo ni la clave por chat. Si se reemplaza una
clave ya cargada y no vacía, reiniciar el servidor para aplicar la nueva.

## Paso 3: recuperación documental

`motor_v2/recuperacion_documental_enriquecida.py` descarga HTML con `urllib` y
limpia el `body` con BeautifulSoup (`beautifulsoup4` en `requirements.txt`).
Extrae el texto del body completo, excluyendo scripts, estilos, plantillas y
elementos ocultos por atributos o estilos inline. No clasifica vocabulario o
temas, no ejecuta JavaScript y no calcula estilos de hojas CSS externas.
`cuerpo_extraido` siempre existe y contiene hasta 5000 caracteres.

Ante HTTP 403, fallos de red, tipos no HTML o un body sin texto, se usa la
`descripcion` original de Brave (también limitada a 5000 caracteres). La
publicación conserva el estado y error de recuperación; no se marca como HTML
recuperado un texto proveniente de la descripción. `recuperacion.fuente_texto`
indica `HTML_BODY`, `DESCRIPCION_BRAVE` o `SIN_TEXTO`.

Por defecto se intenta descargar **todas** las publicaciones, incluidas 103 o más.
`max_documentos_enriquecer` permite un límite explícito de 0 a 1000 intentos;
omitirlo o pasar `null` procesa todas. Las pendientes conservan su descripción y
se evalúan igualmente. Las solicitudes son secuenciales, con timeout de 10
segundos por documento y límite de 2 MiB por HTML: lotes grandes pueden tardar.
La red del entorno debe permitir los dominios de las publicaciones. Nunca se
envía la cabecera de autenticación de Brave a esos sitios.

## Consultas escalonadas universales

`planificar_consultas` devuelve, para cada entidad:

1. `"Entidad" AND (Contexto1 OR Contexto2)`.
2. `"Entidad" AND (Territorio1 OR Territorio2)`.
3. `"Entidad"`.

Se ejecuta primero la etapa de contexto para todas las entidades, luego territorio
y exploración. La paginación realiza rondas: primera página de todas las consultas,
luego las siguientes. `max_brave` es el máximo total de peticiones. Se detiene una
consulta si no hay más resultados, la página está vacía o se repite; ante un error
de Brave se detiene el proveedor sin descartar los hallazgos existentes. El cliente
espacia las peticiones al menos 1.1 segundos para planes limitados a una por segundo.

`plan_consultas` y `consultas_ejecutadas` guardan estrategia, consulta y página.
Cada publicación conserva `consultas_origen` y `hallazgos_brave` con la URL descubierta,
la etapa, la página y la fecha de recuperación UTC. Las URLs se consolidan y los
hallazgos se conservan por separado. Los snapshots anteriores quedan inmutables;
solo se heredan si coincide todo el plan, Marco y período.

## YouTube y trazabilidad para informes

`YOUTUBE_API_KEY` se carga de `.env` o del entorno, sin sobrescribir un valor no
vacío del proceso. Se consulta `https://www.googleapis.com/youtube/v3/videos`
con `part=snippet,statistics`. No se busca directamente en YouTube. Los IDs de
videos (watch, youtu.be, shorts, embed y live) se agrupan en lotes de hasta 50;
variantes de URL del mismo ID comparten una lectura API. Canales o perfiles sin
ID de video registran la imposibilidad de recuperar métricas de video.

`publicacion.metricas` contiene `vistas`, `likes`, `comentarios`,
`fecha_publicacion`, `recuperado_en`, `proveedor` y `video_id`. Un dato omitido
por la API queda `null`, nunca cero inventado. Se preserva la descripción original
de Brave; los metadatos nativos van en `metadatos_youtube`. Si la API falla,
`error_metricas` identifica el problema y se intenta HTML/snippet. No se siguen
redirecciones con la clave y no se registran URLs que incluyan credenciales.

`fuente_especifica` se calcula sobre el hostname exacto o un subdominio válido:
`YOUTUBE`, `FACEBOOK`, `INSTAGRAM`, `X`, `OFICIAL` (gov.ar/gob.ar) o `WEB`.
Se clasifica la URL descubierta, sin inferir titularidad o contenido del sitio.

`metodo_recuperacion` indica `API_OFICIAL` tras obtener datos de YouTube,
`HTML_SCRAPING` si se extrae texto del HTML, o `SNIPPET_BRAVE` para el respaldo.
`recuperacion.fuente_texto` permite distinguir específicamente el texto HTML,
la descripción nativa de YouTube y el resumen de Brave; si tampoco hay resumen,
queda `SIN_TEXTO`. El éxito API no se confunde con una descarga HTML y las
métricas incluyen su fecha de lectura. Las cuentas de solicitudes API y HTML
se exponen por separado en el resumen.

El borrador de red añade `www.googleapis.com`; requiere revisar, guardar y
publicar la configuración del entorno. También se necesita habilitar YouTube
Data API v3 para la clave y disponer de cuota. El código no configura esos permisos.

## Paso 4: Súper-Texto y score acumulativo

El evaluador concatena todo el texto disponible: `titulo`, `descripcion`,
`cuerpo_extraido`, `metadatos_youtube.titulo` y `metadatos_youtube.descripcion`.
`fuentes_texto_evaluadas` identifica las fuentes utilizadas. Las dimensiones se
buscan en este Súper-Texto sin distinguir mayúsculas, conservando los acentos.
No se exige la primera entidad ni presencia en el título o al comienzo del cuerpo.

El score suma una sola contribución por dimensión, independientemente del número
de alternativas o menciones:

- Alguna entidad: +0.4.
- Algún contexto: +0.3.
- Algún territorio: +0.3.

Máximo 1.0, redondeado a un decimal. Entidad sola obtiene 0.4; contexto y territorio
sin entidad obtienen 0.6; entidad y una dimensión obtienen 0.7; las tres dimensiones
obtienen 1.0. No hay bonificación por repetición ni penalización por territorio
genérico. Se acepta score >= 0.5; los valores inferiores se conservan en descartadas.

`componentes_score` permite auditar la suma por dimensión. Se conservan matches,
evidencias, menciones, fuentes, `score_base`, `penalizaciones` (vacío para esta
versión) y justificación. `entidad_principal_presente` es solo información de
trazabilidad: no impone ningún filtro. Se evita duplicar menciones cuando el mismo
campo se copia literalmente, sin alterar la suma fija por dimensiones.

## Territorios específicos e inferencia de los generales

El formulario permite declarar territorios genéricos separados por comas. La API
acepta `territorios_genericos` como lista de alternativas que ya existan en el
Marco. Los demás territorios se consideran específicos. Esta declaración define
la relación solicitada: si aparece uno específico, se asumen presentes todos los
generales declarados en ese mismo Marco, aunque no figuren textualmente.

Ejemplo: `Elemento; Proceso; Localidad, Región Amplia, País`, con
`"territorios_genericos": ["Región Amplia", "País"]`. Si aparece `Localidad`, se
registran también `Región Amplia` y `País` como inferidos. Esto aporta **solo 0.3**
para territorio, no puntos por cada lugar. No se infieren otros territorios
específicos ni lugares externos al Marco, y la inferencia no funciona a la inversa.

`detalles.territorios` diferencia `encontrados_textuales`, `inferidos`,
`no_encontrados_textuales` y los encontrados efectivos. La evidencia inferida
indica `inferencia_por_territorio_especifico`, sus territorios de origen y cero
menciones textuales. Las palabras no vistas no se marcan como vistas.
Sin una declaración explícita de generales, no se inventa una jerarquía geográfica
ni se aplica una lista fija de lugares o una clasificación por cantidad de palabras.

El histórico del mismo Marco/plan/período se reevalúa con la declaración actual,
sin perder publicaciones ni modificar los snapshots previos.

## Visualización

El panel muestra siempre `Score EMM: 0.7` (con el valor correspondiente),
ordena de mayor a menor score y oculta publicaciones con score inferior a 0.5 y muestra al final
`[X] publicaciones descartadas por no cumplir el Marco EMM.` Los scores ausentes
o inválidos se tratan como no evaluados y se ocultan también. Los contadores de
URLs y orígenes describen el inventario completo, no solo las filas visibles.
El backend ordena de mayor a menor score y devuelve en `publicaciones` solo
scores >= 0.5. Los demás se guardan, también ordenados, en
`publicaciones_descartadas`. Un score exactamente 0.5 permanece en el principal.
`total_publicaciones_aceptadas` y `total_publicaciones_descartadas` acompañan ambos
arrays. `total_urls_unicas` y `origenes` siguen describiendo todo el inventario.
El contador visual suma los descartes del servidor y cualquier descarte local de
respuestas antiguas. Un desplegable permite auditar título, score y justificación de las descartadas.
Al reutilizar el histórico se recuperan **ambos** arrays para
reevaluarlos: no se pierde una publicación por un descarte de una ejecución previa.

Al iniciar con `python3 run.py`, la terminal muestra una línea `[EMM] i/total
score_emm=...` por publicación después de recuperar el lote.

## Ubicación de la entidad

`ubicacion_entidad` se guarda tanto en la publicación como en su evaluación:
`TITULO`, `CUERPO`, `DESCRIPCION`, o `null` si no hay coincidencia. La prioridad es
el título, luego el cuerpo y por último la descripción. `ubicaciones_entidad`
conserva todas las ubicaciones encontradas. La descripción de Brave copiada a
`cuerpo_extraido` como respaldo se atribuye a `DESCRIPCION`, no a un HTML descargado.
Esta trazabilidad identifica cualquiera de las entidades completas del Marco. Incluye también
`METADATOS_YOUTUBE_TITULO` y `METADATOS_YOUTUBE_DESCRIPCION` si corresponde.

## Diagnóstico de YouTube

La base del cliente es exactamente `https://www.googleapis.com/youtube/v3/videos`.
Los parámetros `part`, `id` y `key` se construyen con `urlencode`; los caracteres
reservados de la clave no se concatenan sin codificar. La terminal registra
`[YOUTUBE_API] HTTP ...` cuando recibe respuesta y `[YOUTUBE_API] Error HTTP ...`
para fallos (por ejemplo 403). También distingue conexión fallida, JSON inválido
y lotes no completados, manteniendo los errores estructurados del JSON.
Nunca se registra la URL autenticada, la clave ni el cuerpo remoto de error.
