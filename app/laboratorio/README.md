# Descubrimiento exclusivo con Brave Search

Instalar desde la raíz del proyecto con `python3 -m pip install -r requirements.txt`.
Iniciar con `python3 run.py` (puerto 8765).

Al iniciar, `python-dotenv` carga el archivo `.env` ubicado junto a `run.py`,
independientemente del directorio de ejecución. Las variables ya definidas en el
proceso tienen prioridad. La configuración necesaria es `BRAVE_API_KEY`;
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

No se ejecutan DDG, YouTube, adaptadores de redes ni recuperación documental.
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
