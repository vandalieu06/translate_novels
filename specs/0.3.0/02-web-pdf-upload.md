---
code: "02"
title: "Web: PDF upload and jobs"
project: "novel_cli"
status: completed
version: "0.3.0"
date: 2026-10-03
tags: [spec, sdd]
affected_files:
  - src/novel_cli/web/routes.py
  - src/novel_cli/web/jobs.py
  - src/novel_cli/web/app.py
  - src/novel_cli/web/templates/index.html
  - src/novel_cli/web/static/js/jobs.js
  - src/novel_cli/web/templates/novel.html
  - src/novel_cli/web/static/js/novel.js
  - src/novel_cli/web/static/js/library.js
  - src/novel_cli/web/static/css/app.css
  - tests/web/test_upload.py
  - docs/uso.md
  - docs/features.md
---

# 02 — Web: PDF upload and jobs

## Purpose

Exponer en la web la subida de PDFs (reusando `run_pdf_pipeline` de la spec 0.3.0/01) con
progreso en vivo, y adaptar biblioteca/ficha a las novelas de tipo PDF.

## Context

La web lanza jobs por URL y muestra progreso por WebSocket. Falta un endpoint multipart para
subir un PDF, un job que ejecute el pipeline PDF y los controles de UI (formulario, fases,
badge PDF, retraducir sin URL). La novela PDF no tiene `source_url`, así que `sync` y
`retranslate` (basados en URL) no aplican tal cual.

## Proposed change (antes → después)

- **Antes:** `POST /api/jobs` solo por URL; biblioteca/ficha asumen novela web.
- **Después:**
  1. `routes.py`: `POST /api/upload` (multipart: `file`, `source_language`, `translate`,
     `target_language`, `volume_size`). Valida extensión `.pdf` y tamaño
     ≤ `upload_max_bytes()`. Guarda en staging `output/.uploads/<jobid>/source.pdf` y crea
     job `operation="pdf"`.
  2. `jobs.py`: rama `operation == "pdf"` → sin fetcher; translator solo si `translate`;
     llama `run_pdf_pipeline` con el PDF staged; los callbacks emiten los mismos eventos
     (status/progress). Al terminar, mueve `source.pdf` a `output/<slug>/source.pdf`.
  3. `retranslate` para PDF: `POST /api/novels/{slug}/retranslate` detecta `source_pdf` y
     re-traduce por slug (reusa la lógica de translate_pending sin URL). `sync` queda
     deshabilitado para PDF (400 con mensaje claro).
  4. `app.py` `/api/config`: añade `upload_enabled`, `upload_max_mb`, `source_languages`.
  5. UI: tarjeta "Subir PDF" en `index.html` (archivo, idioma origen default `es`, traducir,
     idioma destino, tomos); `submitPdfJob()` con `FormData` en `jobs.js`; panel de progreso
     reutilizado (fase "PDF" mapeada a la barra de descarga o fase nueva); badge "PDF" en
     biblioteca y ficha; ocultar botón Sync en la ficha de novelas PDF.

## Technical decision

- Staging en `output/.uploads/<jobid>/`: no se conoce el slug hasta convertir (el título
  sale del PDF), así que la subida va a un área temporal y el pipeline lo mueve al slug final.
- Reuso de `JobManager`/WebSocket tal cual: el pipeline PDF emite los mismos eventos que el
  pipeline web (status + 3 barras de progreso).
- La subida (guardar archivo) es síncrona al crear el job; la conversión es async en el job.
- El idioma origen es obligatorio en el formulario (default `es`); nunca `auto`.

## Affected files

- `src/novel_cli/web/routes.py`, `src/novel_cli/web/jobs.py`, `src/novel_cli/web/app.py`
- `src/novel_cli/web/templates/index.html`, `src/novel_cli/web/templates/novel.html`
- `src/novel_cli/web/static/js/jobs.js`, `novel.js`, `library.js`, `app.css`
- `tests/web/test_upload.py` (nuevo)
- `docs/uso.md`, `docs/features.md`

## Tests

- Ruta: `POST /api/upload` valida extensión `.pdf` y tamaño máximo; devuelve 400 con mensaje
  claro en fallos; crea job `operation="pdf"` (mock del manager).
- Jobs: rama `operation == "pdf"` llama `run_pdf_pipeline` con el PDF staged (mock) y emite
  eventos de progreso.
- `retranslate` de una novela `source_pdf` funciona por slug; `sync` devuelve 400.
- Verificación visual de la UI con la skill `agent-browser` (subida, progreso, badge PDF).

## Acceptance criteria

- Desde la web se sube un PDF, se lanza el job y se ve el progreso en vivo.
- La novela aparece en la biblioteca con portada y badge "PDF"; Sync oculto; Retraducir funciona.
- PDF > `NOVEL_UPLOAD_MAX_MB` → 400 con mensaje claro.
- El `source.pdf` queda guardado en `output/<slug>/source.pdf`.