# 07 — Testing

- Estado: implementado · Versión spec: 0.1.1 · Relacionado: 0.1.0/08-testing.md

## Propósito

Cobertura unitaria sin red para el CLI, el core y la web.

## Contexto / Problema

0.1.0 cubría CLI/core. 0.1.1 añade la capa web y varias features que requieren nuevos tests.

## Cambio propuesto

- **168 tests unitarios** (sin red; `respx` + fixtures HTML), `asyncio_mode = auto`, `addopts = -m 'not integration'`.
- Nuevos test files/cobertura:
  - `test_download.py`: capítulos vacíos (reintento resuelve, persistente reportado, re-descarga).
  - `test_translate.py`: stale `translated/` re-traducido/limpiado, placeholders en ES.
  - `test_pipeline.py`: placeholders EN/ES, alineación de tomos, rebuild en translate-pending, limpieza de huérfanos, `rebuild_volumes` (cambios de tamaño y ALL).
  - `test_web.py`: rutas, auth por token, jobs (crear/listar/estados via `app.state.manager`), retranslate, volume-size, `translate_backend` en `/api/config`.
  - `test_cli.py`: validación `--volume-size` 50/100/150/200.
  - `test_config.py` (nuevo): `_load_dotenv`.

## Decisión técnica

Los tests de web mockean `web.jobs.run_pipeline`; los de red usan `respx` contra los endpoints (GTX/LibreTranslate) con URL explícita (independientes del `.env` ambiente).

## Archivos afectados

`tests/*.py`, `tests/fixtures/`.

## Criterios de aceptación

- `uv run pytest -q` en verde.
- `uv run ruff check .` limpio (line-length 100, `specs/` excluido).