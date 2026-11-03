---
code: "15"
title: "Upload de PDF: aceptar original_filename explícito"
project: "novel_cli"
status: completed
version: "0.3.0"
date: 2026-11-03
tags: [spec, sdd]
affected_files:
  - src/novel_cli/web/routes.py
  - src/novel_cli/web/jobs.py
  - tests/web/test_upload.py
---

# 15 — Upload de PDF: aceptar original_filename explícito

## Purpose

Permitir que clientes que no controlan el nombre del multipart (la app móvil sube una
copia de caché con nombre UUID) envíen el nombre original del PDF como campo aparte, para
que se use en el fallback de título y en `Manifest.source_filename`.

## Context

La app móvil usa `DocumentPicker` con `copyToCacheDirectory: true`; el archivo que sube se
llama `<uuid>.pdf`. `POST /api/upload` usa `file.filename` como `original_filename` y
`JobManager.create_pdf` lo guarda en las opciones. Si el PDF no trae `Title`, el título
resuelto acaba siendo el UUID.

La spec 12 ya añadió `original_filename` a `run_pdf_pipeline` y `resolve_pdf_metadata`,
pero la ruta web todavía no acepta ese campo desde el formulario.

## Proposed change (antes → después)

- **Antes:** `POST /api/upload` solo usa el nombre del multipart.
- **Después:**
  1. `src/novel_cli/web/routes.py`:
     - `upload_pdf` acepta `original_filename: str | None = Form(None)`;
     - lo añade a `options` (`"original_filename": original_filename or None`).
  2. `src/novel_cli/web/jobs.py`:
     - `create_pdf` usa `options.get("original_filename") or filename` al inyectar
       `"original_filename"` en las opciones del job, para no pisar el valor explícito.
  3. Tests en `tests/web/test_upload.py`:
     - subir con `original_filename="Kunon v01.pdf"` y comprobar que el job recibe ese
       valor;
     - sin `original_filename`, se conserva el comportamiento actual (nombre del multipart).

## Technical decision

- **El campo explícito manda sobre el multipart:** el nombre del multipart es un detalle
  del transporte; el cliente conoce el nombre real del documento.
- **Sin cambios en `run_pdf_pipeline`:** ya acepta `original_filename` y lo usa para el
  fallback de título y para el manifest.
- **Compatibilidad:** el campo es opcional; la web y otros clientes siguen igual.

## Affected files

- `src/novel_cli/web/routes.py`
- `src/novel_cli/web/jobs.py`
- `tests/web/test_upload.py`

## Tests

- `POST /api/upload` con `original_filename` → `run_pdf_pipeline` recibe ese nombre.
- `POST /api/upload` sin `original_filename` → recibe el nombre del multipart.
- La subida normal (sin el campo) no cambia.

## Acceptance criteria

- Subir un PDF sin `Title` con `original_filename="Kunon the Sorcerer Can See v01.pdf"`
  produce título `Kunon the Sorcerer Can See v01` y `Manifest.source_filename` con ese
  nombre, no con el UUID del multipart.
- El campo es opcional y no rompe la web.
- `uv run pytest -q` y `uv run ruff check .` pasan.
