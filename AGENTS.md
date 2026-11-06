# Reglas del proyecto

- Construir un motor universal de descubrimiento EMM: separar el transporte HTTP, la lógica del laboratorio y la persistencia.
- No hardcodear entidades, nombres, categorías ni reglas específicas de un dominio. Recibirlos mediante datos o configuración.
- Usar la librería estándar de Python para el backend y SQLite mediante `sqlite3` para persistencia. Las dependencias externas autorizadas son `python-dotenv` para cargar `.env` y `beautifulsoup4` para limpiar HTML.
- Devolver todos los errores de la API en JSON con la forma `{"error": {"codigo": "...", "mensaje": "..."}}` y un estado HTTP apropiado.
- Guardar las bases SQLite en `datos/`; no versionar bases generadas ni secretos.
- Mantener los stubs explícitos: no presentar resultados simulados como búsquedas reales.
- Iniciar el servidor de desarrollo con `python3 run.py` en el puerto 8765.
