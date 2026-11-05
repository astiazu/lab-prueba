# Motor integrado con DuckDuckGo real

`interfaz_v2/descubrimiento_integrado.py` contiene el orquestador adjunto por el usuario.
Se conserva su planificación, consolidación, contabilidad, recuperación incremental
y escritura de snapshots. Se ajustaron el destino de datos y las etiquetas para
identificar el modo mixto: DDG real y otros proveedores simulados.

Solo se recibió ese archivo. Las dependencias locales compatibles no son las
originales del motor; el adaptador DDG ya fue reemplazado por una implementación real:

- `motor_v2/contratos.py`: Marco con tres dimensiones separadas por `;`, y
  alternativas dentro de cada dimensión separadas por comas.
- `interfaz_v2/descubrimiento_ddg.py`: consultas reales a DuckDuckGo HTML con
  `urllib` y extracción con `HTMLParser`. GET para la primera página y POST con
  los campos del formulario Next para las siguientes. Conserva el contrato
  `(resultados, cursor)` o `(resultados, cursor, diagnostico)`.
- `interfaz_v2/descubrimiento_{brave,youtube}.py`: proveedores de prueba,
  sin lectura de credenciales ni clientes de red.
- `interfaz_v2/descubrimiento_redes.py`: auditoría local, sin extracción real de
  identidades sociales; devuelve cero hallazgos sociales.
- `motor_v2/recuperador_documental.py` y
  `motor_v2/recuperacion_documental_enriquecida.py`: recuperación y enriquecimiento
  mínimos sobre HTML generado localmente, con fichas y diario incremental.

El endpoint llama a `ejecutar_busqueda(payload)` con el Marco, período y opciones
de presupuesto del orquestador. DDG requiere acceso HTTPS a
`html.duckduckgo.com`, sin clave de API. Usa un timeout de 10 segundos y un máximo
de 2 MiB por página, manteniendo la verificación TLS y el proxy del entorno.
Los fallos de red, bloqueos y HTML no reconocido devuelven una lista vacía con
aviso y diagnóstico. El orquestador detiene DDG sin contar el fallo como éxito;
los otros proveedores pueden continuar. No reintenta CAPTCHA ni límites HTTP.

Los resultados se guardan en `datos/ejecuciones/descubrimiento_v2_ddg/`, separados
de los snapshots antiguos totalmente simulados. Cada publicación indica si es
simulada; el panel habilita enlaces solo para resultados reales de DDG. La
recuperación documental sigue siendo un stub: no descarga los enlaces reales.
Las búsquedas DDG no garantizan filtrar las fechas del período solicitado.
No se versionan los archivos generados.

Iniciar desde la raíz con `python3 run.py`. Ejecutar las pruebas con
`python3 -m unittest discover -s tests -v` y `node tests/test_busqueda.cjs`.
Para integrar los proveedores y recuperación definitivos harán falta los módulos
originales; no se ha validado su comportamiento mediante estos sustitutos.
Las pruebas HTTP de DDG usan respuestas controladas, sin conexiones externas.
