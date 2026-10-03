---
code: "03"
title: "Move novels library to ../library-novels and separate logs"
project: "novel_cli"
status: in-progress
version: "0.3.0"
date: 2026-10-03
tags: [spec, sdd]
affected_files:
  - .env.example
  - src/novel_cli/core/config.py
  - src/novel_cli/logging_setup.py
  - src/novel_cli/run_history.py
  - docs/uso.md
  - docs/arquitectura.md
  - README.md
  - specs/README.md
---

# 03 — Move novels library to ../library-novels and separate logs

## Purpose

Separar la biblioteca de novelas del directorio de trabajo: las novelas viven en
`library-novels/` y `output/` queda solo con logs y ejemplos de test/scripts. Migrar las
novelas existentes a su nueva ubicación.

## Context

Hoy todo vive en `output/` (novelas + `logs/` + `scripts/` de benchmark). El usuario quiere
`output/` solo con logs y ejemplos de test, y las novelas en
`/home/jhonnyc/Dev/projects/personal-tools-novels/library-novels`. El código usa
`default_output()` para novelas, logs y run history a la vez; hay que separar el directorio
de novelas del de logs.

## Proposed change (antes → después)

- **Antes:** `default_output()` → novelas + logs + runs en el mismo dir.
- **Después:**
  1. `config.py`: `default_output()` sigue leyendo `NOVEL_OUTPUT_DIR` (default `./output`);
     nuevo `log_dir()` = env `NOVEL_LOG_DIR` o `Path("output") / "logs"`.
  2. `logging_setup.py` y `run_history.py`: usan `config.log_dir()` en lugar de
     `output_dir/logs`. `append_run` deja de derivar de `output_dir`.
  3. `.env` y `.env.example`: `NOVEL_OUTPUT_DIR=/home/jhonnyc/Dev/projects/personal-tools-novels/library-novels`
     y `NOVEL_LOG_DIR=output/logs`.
  4. Migrar datos: mover los slug dirs de novelas de `output/` a `library-novels/`; mantener
     `output/logs` y `output/scripts`.
  5. Docs: actualizar `docs/uso.md`, `docs/arquitectura.md`, `README.md`, `.env.example` y
     `specs/README.md`.

## Technical decision

- Separar explícitamente `NOVEL_OUTPUT_DIR` (novelas/biblioteca) de `NOVEL_LOG_DIR` (logs)
  para que `output/logs` se conserve aunque las novelas salgan del proyecto.
- Ruta absoluta en `.env` para no depender del cwd de lanzamiento.

## Affected files

- `.env.example`, `src/novel_cli/core/config.py`, `src/novel_cli/logging_setup.py`,
  `src/novel_cli/run_history.py`
- `docs/uso.md`, `docs/arquitectura.md`, `README.md`, `specs/README.md`
- Datos: `output/<slug>/*` → `library-novels/<slug>/*` (fuera de git)

## Tests

- Config: `default_output()` y `log_dir()` con/sin env.
- `run_history` y logging escriben en `config.log_dir()`.
- Verificación manual: tras migrar, la web lista las novelas desde `library-novels` y los
  logs siguen en `output/logs`.

## Acceptance criteria

- `output/` solo contiene `logs/` y `scripts/` (ejemplos de test) tras migrar.
- `library-novels/` contiene las 5 novelas con su `manifest/raw/translated/EPUB`.
- Web y CLI usan `library-novels` como biblioteca; logs y runs siguen en `output/logs`.
- `NOVEL_OUTPUT_DIR` documentado en `.env.example`.