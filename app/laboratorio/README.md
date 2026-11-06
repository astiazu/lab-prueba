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

`ejecutar_busqueda(payload)` conserva la planificación equilibrada y consolida
las URLs y sus consultas de origen. `max_brave` limita las consultas (1 a 50,
por defecto 50). Solo se obtiene la primera página de cada consulta: los
resultados no representan cobertura exhaustiva. La fecha del índice tampoco
acredita una fecha de publicación ni admisión EMM.

No se ejecutan DDG, YouTube ni adaptadores de redes. Después de Brave se ejecutan
la recuperación documental y la evaluación contextual que se describen abajo.
Las consultas `site:` del planificador son búsquedas indexadas hechas por Brave,
no llamadas a APIs de redes. Los módulos locales de otros proveedores permanecen
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

## Paso 4: evaluación EMM exacta

`evaluar_publicacion(marco, publicacion)` acepta el Marco como string separado
por punto y coma, o el contrato `Marco` para compatibilidad. Compara únicamente
`titulo` y `cuerpo_extraido`. Las descripciones participan a través del fallback
de recuperación, sin introducir una tercera fuente implícita.

Se comparan palabras completas sin distinguir mayúsculas; se conservan acentos.
No se usan raíces, similitudes, listas temáticas ni categorías. Para que coincida
una alternativa de varias palabras, todas deben aparecer en el texto (sin
exigir adyacencia u orden). Una alternativa completa por dimensión es suficiente.

El score es 0.0 sin entidad, 0.3 con entidad, 0.6 con entidad y contexto y 1.0
con entidad, contexto y territorio. Entidad más territorio sin contexto da 0.3.
Se guarda en `publicacion.score_emm` y en `evaluacion_contextual.score_emm`.
`evaluacion_contextual.detalles` incluye por dimensión las alternativas y palabras
encontradas y no encontradas; se conservan los matches y la justificación para
compatibilidad con el panel. No se descarta ni reordena ninguna publicación.

Al iniciar con `python3 run.py`, la terminal muestra una línea `[EMM] i/total
score_emm=...` por publicación después de recuperar el lote. Las pruebas de lotes
103 usan respuestas controladas y no consumen la API de Brave ni los sitios web.
