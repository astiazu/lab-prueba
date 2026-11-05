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
extrae texto con `HTMLParser`, sin dependencias adicionales. Usa texto dentro de
`main` o `article` si está disponible y, en otro caso, el `body`. Omite elementos
estructurales de navegación, scripts, estilos y elementos ocultos; no utiliza
palabras o categorías temáticas para seleccionar contenido. El campo
`cuerpo_extraido` siempre existe y contiene hasta 5000 caracteres.

Cada publicación incluye `recuperacion.estado` (`RECUPERADO`, `SIN_TEXTO`,
`ERROR` o `PENDIENTE`) y, cuando corresponde, un error JSON. Una descarga fallida
no elimina la publicación ni impide evaluar su título y descripción.

`max_documentos_enriquecer` admite de 0 a 100 intentos, por defecto 8 por búsqueda.
El presupuesto deja documentos pendientes de descarga, pero todos se conservan
y se evalúan. Cada petición usa un timeout de 10 segundos y limita el HTML a
2 MiB. No se ejecuta JavaScript ni se procesan PDF u otros tipos no HTML. Se
requiere acceso de red a los sitios de las publicaciones; la configuración de
red restringida puede bloquear algunos y el fallo se registra por documento.
No se envía la cabecera de autenticación de Brave a las publicaciones.

## Paso 4: evaluación contextual de base

`evaluar_publicacion(marco, publicacion)` compara exclusivamente las dimensiones
del Marco contra título, descripción y cuerpo disponible. Normaliza mayúsculas
y acentos, exige los términos de cada expresión y permite prefijos comunes y
similitudes básicas de tokens largos. No contiene diccionarios temáticos,
clasificaciones de contenido ni reglas específicas de entidades. La comparación
es léxica y aproximada: no resuelve negaciones ni acredita relaciones semánticas.

La publicación incluye `evaluacion_contextual` con `match_entidad`,
`match_contexto`, `match_territorio`, `score_emm` y `justificacion`:

- Sin entidad: 0.0, aunque aparezcan otras dimensiones.
- Con entidad: 0.3 (también si solo añade territorio).
- Con entidad y contexto: 0.6.
- Con entidad, contexto y territorio: 1.0.

Una coincidencia alternativa por dimensión es suficiente para este cálculo.
Los scores no descartan ni reordenan publicaciones. El panel muestra el score,
la justificación, el estado de recuperación y el cuerpo desplegable para auditar.
