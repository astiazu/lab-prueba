# Motor integrado en modo local

`interfaz_v2/descubrimiento_integrado.py` contiene el orquestador adjunto por el usuario.
Se conserva su planificación, consolidación, contabilidad, recuperación incremental
y escritura de snapshots. Se ajustaron el destino de datos y las etiquetas para
identificar inequívocamente esta ejecución como simulada.

Solo se recibió ese archivo. Los demás módulos son implementaciones compatibles
locales, no las dependencias originales del motor:

- `motor_v2/contratos.py`: Marco con tres dimensiones separadas por `;`, y
  alternativas dentro de cada dimensión separadas por comas.
- `interfaz_v2/descubrimiento_{brave,ddg,youtube}.py`: proveedores de prueba,
  sin lectura de credenciales ni clientes de red.
- `interfaz_v2/descubrimiento_redes.py`: auditoría local, sin extracción real de
  identidades sociales; devuelve cero hallazgos sociales.
- `motor_v2/recuperador_documental.py` y
  `motor_v2/recuperacion_documental_enriquecida.py`: recuperación y enriquecimiento
  mínimos sobre HTML generado localmente, con fichas y diario incremental.

El endpoint llama a `ejecutar_busqueda(payload)` con el Marco, período y opciones
de presupuesto del orquestador. No hay una opción HTTP para activar Internet.
Los resultados se guardan en `datos/ejecuciones/descubrimiento_v2_stub/`, aislados
de futuros resultados reales. No se versionan los archivos generados.

Iniciar desde la raíz con `python3 run.py`. Ejecutar las pruebas con
`python3 -m unittest discover -s tests -v` y `node tests/test_busqueda.cjs`.
Para integrar los proveedores y recuperación definitivos harán falta los módulos
originales; no se ha validado su comportamiento mediante estos sustitutos.
