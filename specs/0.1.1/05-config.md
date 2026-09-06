# 05 — Config: cargador `.env` y `translate_backend`

- Estado: implementado · Versión spec: 0.1.1

## Propósito

Fijar la configuración (backend de traducción, URL, API key) sin exportar variables en cada arranque, y exponer el motor activo en la web.

## Contexto / Problema

`config.py` lee env al importar; había que exportarlas antes de cada lanzamiento. La UI no mostraba qué backend usaba.

## Cambio propuesto

- `_load_dotenv()` en `core/config.py`: carga `KEY=VALUE` de `.env` (o `NOVEL_CLI_ENV_FILE`) en `os.environ` **sin sobrescribir** variables ya exportadas. Se ejecuta al importar `config`.
- `GET /api/config` incluye `translate_backend`; la UI muestra un badge ("Traducción: LibreTranslate / Google").

## Decisión técnica

Sin dependencias externas (parser propio). El `.env` está en `.gitignore` (puede llevar API keys).

## Archivos afectados

`core/config.py`, `web/app.py`, `web/static/js/app.js`, `tests/test_config.py`.

## Tests

`test_load_dotenv_sets_and_does_not_override` (setea, no sobreescribe, comillas, comentarios, líneas sin `=`).

## Criterios de aceptación

- Crear un `.env` con `NOVEL_TRANSLATE_BACKEND=libre` hace que CLI y web usen LibreTranslate sin exportar nada.
- El badge del header muestra el motor activo.