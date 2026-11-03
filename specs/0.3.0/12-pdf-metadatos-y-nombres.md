---
code: "12"
title: "PDF sin metadatos: fallback a nombre de archivo y overrides de título/autor"
project: "novel_cli"
status: completed
version: "0.3.0"
date: 2026-11-02
tags: [spec, sdd]
affected_files:
  - src/novel_cli/core/config.py
  - src/novel_cli/core/models/state.py
  - src/novel_cli/core/services/pdf_import.py
  - src/novel_cli/core/utils/names.py
  - src/novel_cli/cli/app.py
  - src/novel_cli/web/routes.py
  - src/novel_cli/web/jobs.py
  - src/novel_cli/web/templates/index.html
  - src/novel_cli/web/static/js/jobs.js
  - docs/arquitectura.md
  - docs/uso.md
  - docs/features.md
  - tests/core/test_pdf_import.py
  - tests/web/test_upload.py
  - tests/test_cli.py
---

# 12 — PDF sin metadatos: fallback a nombre de archivo y overrides de título/autor

## Purpose

Evitar que un PDF sin metadatos acabe con título/slug `source`, y permitir que el usuario
fuerce el título y el autor cuando los metadatos del PDF faltan o son incorrectos.

## Context

La subida web guarda siempre el archivo en staging como `source.pdf`
(`web/jobs.py`). `run_pdf_pipeline` no pasa `title` ni `author` a `ConversionOptions`, así
que pdf-to-epub aplica su fallback `metadata.title or input_pdf.stem` y obtiene
`"source"`. Resultado real en la biblioteca:

```json
{
  "slug": "source",
  "title": "source",
  "author": "Jared Marino",
  "chapters_total": 1,
  "epub_original": ["source.epub"]
}
```

Además, `metadata.title` puede ser basura (`Microsoft Word - documento1`) y
`metadata.author` puede ser `<unknown>` (caso de `i-married-the-dragon-i-killed`), que hoy
se guarda tal cual.

## Proposed change (antes → después)

- **Antes:** el nombre original se pierde en staging; no hay `--title`/`--author`; no hay
  sanitización de placeholders; dos PDFs sin metadatos comparten el slug `source`.
- **Después:**
  1. `core/services/pdf_import.py`:
     - `resolve_pdf_metadata(pdf_path, *, title=None, author=None, metadata=None) ->
       ResolvedPdfMetadata(title, author)`:
       - prioridad: valor del usuario > metadato válido > stem del nombre de archivo;
       - título inválido → `filename.stem`; si tampoco hay, `"Novela sin título"`;
       - autor inválido → `None`;
       - placeholders considerados inválidos: vacío, `<unknown>`, `unknown`,
         `desconocido`, `anonymous`, `anónimo`, `untitled`, `sin título`,
         `Microsoft Word - …`, `Microsoft® Word …`, y valores que terminan en `.pdf`.
     - `convert_pdf(..., title, author)` pasa los valores resueltos a `ConversionOptions`.
     - `PdfImport` expone `source_filename` y `source_pdf_sha256`.
     - `run_pdf_pipeline(..., title=None, author=None, original_filename=None)` usa el
       título resuelto para `slug`, `manifest.title` y el nombre del EPUB.
  2. `core/models/state.py`: `Manifest.source_filename: str | None = None` y
     `Manifest.source_pdf_sha256: str | None = None`.
  3. `core/utils/names.py`: `unique_slug(base, output_dir, *, sha256)`:
     - si no existe el directorio → `base`;
     - si existe y el `source_pdf_sha256` coincide → reutiliza `base`;
     - si existe con otro hash → `base-2`, `base-3`, …
  4. CLI: `novel-cli pdf ... --title "..." --author "..."`.
  5. Web:
     - `POST /api/upload` acepta `title` y `author` opcionales (Form);
     - `create_pdf` conserva el nombre original en `options["original_filename"]`;
     - `_run_pdf_import` pasa `title`, `author` y `original_filename` a
       `run_pdf_pipeline`;
     - `index.html`: campos “Título” y “Autor” opcionales en la tarjeta PDF;
     - `jobs.js`: al seleccionar el archivo, prerrellena el título con el nombre sin
       `.pdf` (editable); envía `title`/`author` solo si tienen valor.
  6. `docs/uso.md` y `docs/features.md`: documentar el fallback y los overrides.

## Technical decision

- **No depender del nombre del archivo en staging:** el staging sigue siendo
  `source.pdf` para no complicar el job, pero el nombre original viaja en `options` y en
  el manifest (`source_filename`).
- **Sanitizar antes de pdf-to-epub:** el override se pasa como `ConversionOptions.title`
  / `author`, que pdf-to-epub ya prioriza sobre los metadatos. Así el EPUB original y el
  manifest usan el mismo valor.
- **Hash del PDF para idempotencia:** re-subir el mismo PDF reutiliza la carpeta; subir
  otro PDF con el mismo título crea `-2` en vez de sobrescribir.
- **El autor `<unknown>` se convierte en `None`:** no se inventa un autor y no se escribe
  `dc:creator` basura.

## Affected files

- `src/novel_cli/core/config.py` (si hace falta una constante de placeholders)
- `src/novel_cli/core/models/state.py`
- `src/novel_cli/core/services/pdf_import.py`
- `src/novel_cli/core/utils/names.py`
- `src/novel_cli/cli/app.py`
- `src/novel_cli/web/routes.py`, `web/jobs.py`, `templates/index.html`,
  `static/js/jobs.js`
- `docs/arquitectura.md`, `docs/uso.md`, `docs/features.md`
- `tests/core/test_pdf_import.py`, `tests/web/test_upload.py`, `tests/test_cli.py`

## Tests

- `resolve_pdf_metadata`: sin título → stem; título `""`/`Microsoft Word - x`/`untitled`
  → stem; `--title` gana; autor `<unknown>` → `None`; autor válido se conserva.
- `run_pdf_pipeline`: manifest con `source_filename` y `source_pdf_sha256`; título del
  EPUB y slug basados en el nombre resuelto.
- `unique_slug`: mismo hash reutiliza; hash distinto sufija `-2`; colisión triple `-3`.
- CLI: `--title`/`--author` llegan a `run_pdf_pipeline` (mock) y validan vacío.
- Web: `/api/upload` acepta `title`/`author`; el job recibe `original_filename`; el
  formulario envía los campos.

## Acceptance criteria

- Subir `mi-novela.pdf` sin metadatos produce título `mi-novela`, slug `mi-novela`,
  `mi-novela.epub` y `<dc:title>mi-novela</dc:title>`.
- `--title "Mi Novela"` o el campo web “Título” mandan sobre metadatos y filename.
- Un autor `<unknown>` no aparece en el manifest ni en `dc:creator`.
- Dos PDFs distintos sin metadatos no comparten carpeta; el mismo PDF re-subido sí.
- `uv run pytest -q` y `uv run ruff check .` pasan.
