---
code: "01"
title: "PDF import pipeline: convert, translate and dual EPUB"
project: "novel_cli"
status: completed
version: "0.3.0"
date: 2026-10-03
tags: [spec, sdd]
affected_files:
  - pyproject.toml
  - src/novel_cli/core/config.py
  - src/novel_cli/core/models/state.py
  - src/novel_cli/core/services/pdf_import.py
  - src/novel_cli/core/services/pipeline.py
  - src/novel_cli/cli/app.py
  - docs/arquitectura.md
  - docs/uso.md
  - docs/features.md
  - tests/core/test_pdf_import.py
  - tests/test_cli.py
---

# 01 — PDF import pipeline: convert, translate and dual EPUB

## Purpose

Permitir importar un PDF de novela (webnovel o light novel con ilustraciones) y generar:
el EPUB **original** usando pdf-to-epub (conserva imágenes, tablas y formato del PDF) y, si
se pide y el idioma origen difiere del destino, el EPUB **traducido** con el builder actual
(texto plano, tomos). Sirve de base para CLI y web.

## Context

translate_novels solo importa web novels por scrape. El usuario quiere subir PDFs y, cuando
el origen sea distinto del destino (típicamente en → es), obtener el EPUB original y el
traducido. El EPUB original debe ser el de pdf-to-epub (formato rico); el traducido usa el
builder existente. Requiere el export de pdf-to-epub (spec pdf-to-epub 0.2.0/01).

## Proposed change (antes → después)

- **Antes:** solo `run_pipeline` por URL; sin fuente PDF.
- **Después:**
  1. `pyproject.toml`: dependencia `pdf-to-epub = { path = "../pdf-to-epub" }` (repos
     hermanos) y compatibilidad Python 3.14 resuelta (ver spec de pdf-to-epub).
  2. `config.py`: `upload_max_bytes()` desde `NOVEL_UPLOAD_MAX_MB` (default 100) y set
     `SOURCE_LANGUAGES` para validar el idioma origen.
  3. `models/state.py`: nuevo campo `Manifest.source_pdf: str | None = None` (marca novelas
     importadas de PDF).
  4. Nuevo `core/services/pdf_import.py`:
     - `convert_pdf(pdf_path, workdir, *, title, author, language, on_status) -> PdfImport`
       (report de pdf-to-epub + capítulos planos + cover). Ejecuta
       `pdf_to_epub.core.pipeline.run()` en `asyncio.to_thread` con `keep_intermediate=True`
       y luego `extract_docx_chapters(docx_path)` → mapear a `Chapter(num, title, url="", paragraphs)`.
     - `save_chapters(slug_dir, chapters)` → escribe `raw/<NNNN>.md` con `format_chapter`.
     - `run_pdf_pipeline(*, pdf_path, output_dir, source_language, translate, target_language,
       volume_size, translator, on_*)`: manifest (`source_pdf`, `language_code=source_language`),
       EPUB original = el de pdf-to-epub (`{title}.epub`), cover → `manifest.cover_path`;
       si `translate and target != source`: `translate_chapters(source=source_language)` →
       `_generate_epubs(translated=True)`. `_cleanup_orphan_epubs` preserva el original.
  5. `pipeline.py::rebuild_volumes`: si `source_pdf` está presente → regenerar **solo** los
     EPUB traducidos y conservar `epub_original` intacto.
  6. CLI: comando `novel-cli pdf <archivo> [--source en] [-t] [--target es] [--volume-size N]`
     reusando `run_pdf_pipeline`.

## Technical decision

- **D1 = 1B (híbrido):** EPUB original de pdf-to-epub (conserva ilustraciones/formato) +
  EPUB traducido de translate_novels (texto plano). Decisión del usuario: prioriza conservar
  el formato original de light novels.
- El texto a traducir sale del DOCX ya limpio (headers/footers eliminados por pdf-to-epub).
- `source` de traducción = idioma indicado por el usuario (nunca `auto`), para evitar
  errores de detección en PDFs sin metadatos fiables.
- El EPUB traducido NO incluye imágenes en esta iteración (mejora futura).
- El EPUB original es un solo tomo; el traducido puede dividirse en tomos por `volume_size`.

## Affected files

- `pyproject.toml`, `src/novel_cli/core/config.py`, `src/novel_cli/core/models/state.py`
- `src/novel_cli/core/services/pdf_import.py` (nuevo)
- `src/novel_cli/core/services/pipeline.py` (`rebuild_volumes`)
- `src/novel_cli/cli/app.py` (comando `pdf`)
- `docs/arquitectura.md`, `docs/uso.md`, `docs/features.md`
- `tests/core/test_pdf_import.py` (nuevo), `tests/test_cli.py`

## Tests

- Unit `run_pdf_pipeline` con `convert_pdf` mockeado + translator mockeado: EPUB original
  presente; traducido solo cuando `translate and target != source`; manifest correcto
  (`source_pdf`, `language_code`, `epub_original`, `epub_translated`, `cover_path`).
- `rebuild_volumes` con `source_pdf`: regenera solo traducidos y conserva el original.
- CLI `pdf` con mocks (opciones, exit codes).
- Integration (marcado `@pytest.mark.integration`): conversión real de un PDF pequeño.

## Acceptance criteria

- `novel-cli pdf` convierte un PDF: genera EPUB original (pdf-to-epub) + `raw/<NNNN>.md`;
  con `-t` y `target != source` genera `translated/` + EPUB traducido (tomos).
- `manifest.cover_path` apunta al cover cuando el PDF tiene portada.
- El EPUB original nunca se borra ni se regenera desde texto plano.
- `rebuild_volumes`/`volume-size` en una novela PDF solo afecta al EPUB traducido.
- Validación de idioma origen y de tamaño de subida en `config`.