---
code: "14"
title: "PDF: inferir título y autor desde el contenido"
project: "novel_cli"
status: completed
version: "0.3.0"
date: 2026-11-03
tags: [spec, sdd]
affected_files:
  - src/novel_cli/core/services/pdf_import.py
  - src/novel_cli/web/templates/index.html
  - src/novel_cli/web/static/js/common.js
  - src/novel_cli/web/static/js/app.js
  - src/novel_cli/web/static/js/jobs.js
  - docs/arquitectura.md
  - docs/uso.md
  - docs/features.md
  - tests/core/test_pdf_import.py
---

# 14 — PDF: inferir título y autor desde el contenido

## Purpose

Evitar títulos UUID o placeholders cuando el PDF no trae metadatos y el nombre del archivo
tampoco es legible, infiriendo título y autor del propio contenido del PDF.

## Context

Las últimas subidas desde la app móvil llegaron con nombre de multipart UUID. Dos de esos
PDFs no traían `Title`:

- `21032367-...pdf`: light novel de 262 páginas; su portada dice “Haruya Akasaki Y Las
  bellezas de clase S” y la cabecera repite el título japonés.
- `fc2c6dab-...pdf`: “Kunon the Sorcerer Can See: Volumen 1”, de Umikaze Minamino; el
  título y el autor están en el aviso legal de la página 2, y el metadato `author` dice
  `python-docx` (el generador).

La spec 15 ya permite enviar `original_filename`; esta spec añade una segunda capa para
cuando el nombre original también sea un UUID o los metadatos sean basura.

## Proposed change (antes → después)

- **Antes:** prioridad usuario > metadato > nombre del archivo (aunque sea UUID).
- **Después:**
  1. `_clean_metadata_value` rechaza UUIDs y autores-generador (`python-docx`, `calibre`,
     `Adobe`, `pymupdf`, `pdf2docx`, `Microsoft Word`).
  2. Nuevo `infer_pdf_metadata(pdf_path) -> InferredPdfMetadata`:
     - **título entre comillas** tras “novela ligera”/“light novel”/“obra”/“volumen”
       (alta confianza);
     - **portada**: línea con tipografía claramente mayor que el cuerpo (≥ 1,6× la
       mediana), uniendo líneas consecutivas del mismo tamaño;
     - **cabecera repetida** en la banda superior de las primeras páginas (≥ 25 % de las
       páginas);
     - **autor** tras “escrita por …” / “Autor: …”, normalizando espacios.
  3. `resolve_pdf_metadata` acepta `inferred_title`/`inferred_author` y aplica:
     usuario > metadato válido > inferido > nombre legible > “Novela sin título”.
  4. `convert_pdf` infiere solo si falta título o autor válido.
  5. La web muestra el hint “Se detecta del PDF o del nombre del archivo”.

## Technical decision

- **Heurísticas conservadoras:** el título inferido solo se usa si supera una comprobación
  de confianza (comillas, tamaño de fuente o repetición); si no, se cae al nombre legible.
- **Se reutiliza `pymupdf`**, ya presente como dependencia de pdf-to-epub; no se añade nada
  nuevo.
- **El autor inferido solo se usa si el metadato es inválido**, para no pisar autores
  reales.
- **La inferencia es best-effort:** si falla, el pipeline sigue con el nombre del archivo.

## Affected files

- `src/novel_cli/core/services/pdf_import.py`
- `src/novel_cli/web/templates/index.html`
- `docs/arquitectura.md`, `docs/uso.md`, `docs/features.md`
- `tests/core/test_pdf_import.py`

## Tests

- PDF sintético con título entre comillas → título y autor inferidos.
- PDF sintético con portada en tipografía grande → título inferido.
- PDF sintético con cabecera repetida → título inferido.
- `resolve_pdf_metadata` con nombre UUID y título inferido → usa el inferido.
- Autor `python-docx` → se descarta y se usa el inferido.
- PDF sin señales → no inventa título; cae al nombre legible o “Novela sin título”.

## Acceptance criteria

- Un PDF sin `Title` cuyo aviso legal dice “novela ligera «Kunon…»” obtiene ese título.
- Un PDF con portada grande obtiene el texto de la portada como título.
- Un PDF con cabecera repetida obtiene la cabecera como título.
- El autor `python-docx` no aparece; si hay “escrita por X”, se usa X.
- Un nombre de archivo UUID nunca se usa como título si hay una inferencia válida.
- `uv run pytest -q` y `uv run ruff check .` pasan.
