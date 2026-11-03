---
code: "13"
title: "PDF: modo libro/webnovel y paso de metadatos al troceado de capítulos"
project: "novel_cli"
status: completed
version: "0.3.0"
date: 2026-11-02
tags: [spec, sdd]
affected_files:
  - src/novel_cli/core/models/state.py
  - src/novel_cli/core/services/pdf_import.py
  - src/novel_cli/cli/app.py
  - src/novel_cli/web/routes.py
  - src/novel_cli/web/jobs.py
  - src/novel_cli/web/templates/index.html
  - src/novel_cli/web/static/js/jobs.js
  - src/novel_cli/web/static/css/app.css
  - docs/arquitectura.md
  - docs/uso.md
  - docs/features.md
  - tests/core/test_pdf_import.py
  - tests/web/test_upload.py
  - tests/test_cli.py
---

# 13 — PDF: modo libro/webnovel y paso de metadatos al troceado de capítulos

## Purpose

Exponer en translate_novels el modo de troceado `auto|book|webnovel` que implementa
pdf-to-epub (spec 0.2.0/02), persistirlo en el manifest y aplicarlo tanto al EPUB original
como a `raw/` y al EPUB traducido.

## Context

El troceado actual es el mismo para una webnovel de 50-200 capítulos y una light novel de
≤ 10. En las últimas subidas:

- `I Married the Dragon I Killed` (webnovel): 124 capítulos, 45 vacíos.
- `source` (light novel): 1 capítulo de 259 KB.
- `Haburare...` (light novel): 7 capítulos correctos.

La corrección vive en pdf-to-epub (spec 0.2.0/02). translate_novels solo necesita pasar el
modo, guardarlo y no perderlo en `retranslate`/`rebuild`.

## Proposed change (antes → después)

- **Antes:** `run_pdf_pipeline` no conoce el tipo de PDF; `extract_docx_chapters` no recibe
  modo; el manifest no lo guarda.
- **Después:**
  1. `core/models/state.py`: `Manifest.pdf_kind: str | None = None` (valores
     `auto|book|webnovel`).
  2. `core/services/pdf_import.py`:
     - `convert_pdf(..., split_mode="auto")` pasa `split_mode` a `ConversionOptions` y
       devuelve `PdfImport.split_mode` (desde `report.split_mode`).
     - `run_pdf_pipeline(..., split_mode="auto")`:
       - valida el valor;
       - pasa `split_mode` a `convert_pdf`;
       - guarda `manifest.pdf_kind = converted.split_mode`;
       - pasa el modo a `extract_docx_chapters` para que `raw/` use la misma
         normalización que el EPUB original.
     - `retranslate_pdf` no reconvierte: conserva `manifest.pdf_kind` y usa
       `extract_docx_chapters(..., mode=manifest.pdf_kind or "auto")` si hiciera falta.
  3. CLI: `novel-cli pdf ... --kind [auto|book|webnovel]` (default `auto`); validación
     con exit 1 si el valor no es válido.
  4. Web:
     - `POST /api/upload` acepta `kind` (Form, default `auto`) y valida;
     - `create_pdf` lo guarda en `options["split_mode"]`;
     - `_run_pdf_import` lo pasa a `run_pdf_pipeline`;
     - `index.html`: selector “Tipo de PDF: Automático / Libro (light novel) / Webnovel”
       en la tarjeta de subida, con ayuda contextual;
     - `jobs.js`: envía `kind` al endpoint.
  5. `docs/uso.md`: explicar cuándo elegir `book` o `webnovel` y que `auto` es el default.
  6. `docs/features.md` y `docs/arquitectura.md`: documentar el modo y el campo
     `pdf_kind`.

## Technical decision

- **El modo se persiste en el manifest** para que la ficha, una futura re-importación o un
  `rebuild` no pierdan la estrategia elegida.
- **`auto` como default** para no romper los PDFs que ya funcionan; el usuario puede
  forzar el modo cuando la detección automática falle.
- **Una sola fuente de verdad:** la normalización de capítulos ocurre en pdf-to-epub;
  translate_novels no duplica el algoritmo, solo pasa el modo y consume el resultado.
- **El EPUB traducido se genera desde `raw/`**, que ya sale normalizado, así que los tomos
  y el EPUB original coinciden en capítulos.

## Affected files

- `src/novel_cli/core/models/state.py`
- `src/novel_cli/core/services/pdf_import.py`
- `src/novel_cli/cli/app.py`
- `src/novel_cli/web/routes.py`, `web/jobs.py`, `templates/index.html`,
  `static/js/jobs.js`, `static/css/app.css`
- `docs/arquitectura.md`, `docs/uso.md`, `docs/features.md`
- `tests/core/test_pdf_import.py`, `tests/web/test_upload.py`, `tests/test_cli.py`

## Tests

- `run_pdf_pipeline` con `split_mode="webnovel"`: el mock de `convert_pdf` recibe el modo
  y el manifest guarda `pdf_kind="webnovel"`.
- `run_pdf_pipeline` con modo inválido → `PdfImportError`.
- CLI `pdf --kind webnovel` llega al pipeline; `--kind foo` → exit 1.
- Web `/api/upload` con `kind=book` crea el job con `split_mode="book"`; `kind=foo` → 400.
- `retranslate_pdf` conserva `pdf_kind` del manifest.

## Acceptance criteria

- Subir un PDF desde CLI o web con `--kind book` / `--kind webnovel` aplica el modo.
- `auto` deja `I Married...` en 78 capítulos, `source` en 4 capítulos de texto
  (+ front matter ilustrado en el EPUB original) y `Haburare` en 7.
- `manifest.pdf_kind` refleja el modo resuelto.
- Los capítulos de texto del EPUB original, `raw/` y el EPUB traducido coinciden; el
  front matter solo-imágenes se conserva en el EPUB original.
- `uv run pytest -q` y `uv run ruff check .` pasan.
