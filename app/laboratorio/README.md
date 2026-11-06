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

`ejecutar_busqueda(payload)` utiliza una consulta booleana estricta y consolida
las URLs y sus consultas de origen. `max_brave` limita las consultas (1 a 50,
por defecto 50). Solo se obtiene la primera página de cada consulta: los
resultados no representan cobertura exhaustiva. La fecha del índice tampoco
acredita una fecha de publicación ni admisión EMM.

No se ejecutan DDG, YouTube ni adaptadores de redes. Después de Brave se ejecutan
la recuperación documental y la evaluación contextual que se describen abajo.
El planificador no agrega búsquedas abiertas ni restricciones de dominio ajenas
al Marco. Los módulos locales de otros proveedores permanecen
inactivos para futuras integraciones; el adaptador y las pruebas DDG se retiraron.
No se generan publicaciones simuladas ni se heredan snapshots de otros modos.

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

## Consultas booleanas universales

`interfaz_v2/planificador_consultas.py` construye una sola consulta:
`(entidades OR ...) AND (contextos OR ...) AND (territorios OR ...)`.
Las comas definen alternativas en las tres dimensiones, siguiendo la consulta
de ejemplo del contrato del producto. Las frases de varias palabras se citan;
los territorios se citan siempre. Los operadores introducidos como alternativas
se tratan como texto literal. No se agregan vocabularios temáticos ni dominios.

El orquestador guarda la consulta en `consulta_booleana` y solo hereda snapshots
con la misma consulta, Marco y período. Los snapshots de búsqueda natural se
conservan en disco, pero no se mezclan con la búsqueda estricta.

## Paso 4: termómetro EMM flexible

`evaluar_publicacion(marco, publicacion)` acepta el string del Marco o el contrato
`Marco` y evalúa título y cuerpo disponible. Normaliza Unicode y mayúsculas,
conservando acentos. Contextos y territorios son alternativas: una frase completa
de cada lista basta para considerar presente esa dimensión.

Una entidad puede coincidir como frase completa o por partes principales. La
heurística genérica considera palabras de cuatro o más caracteres y exige al
menos dos tercios de esas palabras distintas, redondeando hacia arriba, con un
mínimo de dos cuando hay varias. Si solo hay una palabra larga, esa es su parte
principal. Las partes deben aparecer dentro de una ventana de 12 tokens; no se
usan diccionarios de nombres, cargos, categorías ni lugares. Entidades formadas
solo por palabras cortas requieren frase completa. Estas son aproximaciones
léxicas auditables, no decisiones semánticas de admisión.

Scores:

- 0.0: ninguna entidad.
- 0.4: entidad sin contexto ni territorio.
- 0.6: entidad más contexto o territorio.
- 0.8: las tres dimensiones presentes.
- 1.0: las tres presentes y al menos dos menciones no solapadas de una misma
  alternativa de entidad en título/cuerpo. No se suman alternativas solapadas
  para inflar el contador.

`evaluacion_contextual.detalles` conserva encontrados, faltantes y la evidencia
por alternativa (`metodo`, `menciones`). También se guardan los matches,
`menciones_por_dimension`, la justificación y el `score_emm` en cada publicación.
El backend conserva todo el inventario y los snapshots para auditoría.

## Visualización

El panel oculta publicaciones con score inferior a 0.5 y muestra al final
`[X] publicaciones descartadas por no cumplir el Marco EMM.` Los scores ausentes
o inválidos se tratan como no evaluados y se ocultan también. Los contadores de
URLs y orígenes describen el inventario completo, no solo las filas visibles.
No se borra información del JSON; el filtro se aplica solo en la presentación.

Al iniciar con `python3 run.py`, la terminal muestra una línea `[EMM] i/total
score_emm=...` por publicación después de recuperar el lote.
