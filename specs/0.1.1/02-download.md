# 02 — Descarga: control de capítulos vacíos

- Estado: implementado · Versión spec: 0.1.1

## Propósito

Evitar que capítulos sin contenido (0 párrafos tras el parse) queden como
"descargados" y nunca se reintenten.

## Contexto / Problema

En algunos capítulos el parser devolvía 0 párrafos (página bloqueada/JS/selectors
sin match) y se escribía un `raw/<NNNN>.md` solo con el título, que contaba como
descargado. No había aviso ni reintento.

## Cambio propuesto

- `is_chapter_empty(paragraphs)`: vacío si no hay ningún párrafo con contenido.
- En `download_chapters`: los vacíos se **reintentan al final del lote** (secuencial, backoff `EMPTY_RETRY_BACKOFF`); si persisten quedan "pendientes de reintento" (no fallan el job).
- `existing_nums` excluye archivos vacíos → un archivo vacío **no cuenta como ya descargado** y se re-descarga al re-ejecutar.
- Manifest: `chapters_empty` / `chapters_empty_nums`; avisos en CLI (`AVISO: N capítulo(s) vacío(s)…`) y en la web (badge en la tarjeta).

## Decisión técnica

La existencia del archivo era la fuente de verdad; ahora la existencia **y** el contenido. `refresh_empty_counts` recalcula los vacíos desde el disco (usado también por las vías de solo-traducción).

## Archivos afectados

`core/services/download.py`, `core/services/pipeline.py`, `core/models/state.py`, `cli/app.py`, `web/static/js/app.js`, `web/static/css/app.css`.

## Tests

Detección, reintento que resuelve, vacío persistente reportado, re-descarga de archivo vacío, refresh de counts.

## Criterios de aceptación

- Un capítulo vacío se reintenta y, si persiste, se reporta sin fallar el job.
- Re-ejecutar el comando vuelve a intentar los vacíos.