# 02 — Logging e historial de ejecuciones

- Estado: implementado
- Versión spec: 0.2.0 · Fecha: 2026-09-11 · Relacionado: 0.1.0/06-cli.md

## Propósito

Tener un **log técnico** persistente (debug/errores) y un **historial** de las
ejecuciones (qué se hizo y cómo terminó), para diagnosticar fallos al probar el
sistema sin depender de la consola ni de la web en memoria.

## Contexto / Problema

Hoy no existe un sistema de logs:

- `-V/--verbose` solo activa `rich.traceback` (`cli/app.py`), no niveles ni fichero.
- Hay 2 `logger.exception` sueltos (notifier/Telegram) sin `basicConfig`, sin
  formato ni persistencia.
- La web guarda los errores del job **en memoria** (`job.error`) y los pierde al
  reiniciar; Uvicorn escribe a stderr sin persistir.
- `core` (fetcher, download, translate, toc) **no registra nada**: reintentos,
  backoff, `429`, fallback HTTP→Playwright, capítulos vacíos… pasan inadvertidos.
- El único estado persistente es el `.manifest.json` por novela (estado final,
  no historial).

El spec `0.1.0/06-cli.md` prometía `-V` = "logs detallados (rich traceback,
debug)" pero solo se implementó el traceback. No hay spec de logging en el
roadmap.

## Cambio propuesto (antes → después)

**Antes**: ante un fallo, no hay `output/logs/...` que consultar.

**Después**:
- Fichero rotativo `output/logs/novel-cli.log` con timestamps, nivel, módulo y
  `job_id`; `-V` sube a DEBUG.
- `output/logs/runs.jsonl`: una línea por ejecución (CLI o web) con operación,
  estado, duración, contadores, slug/título y error.
- Consola en WARNING para no romper las barras de `rich`; DEBUG con `-V`.

## Decisión técnica

- **`core/` puro**: los módulos de dominio solo usan
  `logging.getLogger(__name__)`. La **configuración de handlers** vive en
  `novel_cli/logging_setup.py` (infraestructura) y se invoca desde los
  entrypoints (`cli/app.py` `run`/`serve`, `web/app.py:main`). **Nunca** en
  `create_app()` para que los tests no escriban ficheros.
- **`configure_logging(*, output_dir, verbose=False, force=False)`**:
  - Fichero: `output_dir/logs/novel-cli.log` (o `NOVEL_LOG_FILE`),
    `RotatingFileHandler(maxBytes=5 MiB, backupCount=3)`, nivel INFO/DEBUG.
  - Consola: `StreamHandler(stderr)` a WARNING (DEBUG con `-V`).
  - Formato `%(asctime)s %(levelname)s %(name)s [%(job_id)s]: %(message)s`.
  - Env: `NOVEL_LOG_FILE`, `NOVEL_LOG_LEVEL`, `NOVEL_LOG_MAX_BYTES`,
    `NOVEL_LOG_BACKUPS`.
  - Idempotente (marca los handlers) y silencia `httpx`/`telegram`/`uvicorn.access`.
- **Correlación `job_id`**: `contextvars.ContextVar` fijado por `JobManager._run`
  (web) y por el run de CLI; un `logging.Filter` lo inyecta en cada registro.
- **Historial**: `novel_cli/run_history.py` con `RunRecord` (`@dataclass`) y
  `append_run(output_dir, record)` (JSONL, append). CLI y web lo llaman tras el
  pipeline (o en el error), midiendo con `time.monotonic()`.
- **Privacidad**: nunca se loguean `NOVEL_TELEGRAM_BOT_TOKEN` ni
  `NOVEL_TRANSLATE_API_KEY`.

## Archivos afectados

- `src/novel_cli/logging_setup.py` (nuevo): `configure_logging`, `JOB_ID`, filtro.
- `src/novel_cli/run_history.py` (nuevo): `RunRecord`, `append_run`,
  `record_from_manifest`.
- `src/novel_cli/core/scraper/fetcher.py`, `core/services/download.py`,
  `core/services/translate.py`, `core/services/toc.py`,
  `core/services/pipeline.py`: `logger` + mensajes.
- `src/novel_cli/cli/app.py`: configura logging, registra run e historial.
- `src/novel_cli/web/app.py`: configura logging en `main()`.
- `src/novel_cli/web/jobs.py`: `job_id`, logs de job y historial.
- `tests/test_logging.py` (nuevo).
- `docs/uso.md`, `docs/arquitectura.md`, `docs/features.md`.

## Tests

- `tests/test_logging.py` (sin red):
  - `configure_logging` crea el fichero en `tmp_path`, respeta niveles, es
    idempotente y aplica la rotación.
  - `caplog` verifica mensajes de `core` (p. ej. capítulo vacío, cache de
    traducción, fallback).
  - `append_run` escribe JSONL válido, acumula líneas y crea el directorio.
  - `create_app()` no escribe ficheros de log.
- `uv run ruff check .` y `uv run pytest -q` en verde.

## Criterios de aceptación

- Tras un run de CLI o un job web, existen `output/logs/novel-cli.log` y
  `output/logs/runs.jsonl`.
- `-V` deja trazas DEBUG en el fichero; sin `-V`, INFO.
- Un fallo registra la excepción con traza en el log y una línea `status="error"`
  en `runs.jsonl` (con la fase/mensaje).
- La web etiqueta los logs con el `job_id` del job.
- No se filtran tokens/API keys.
- La suite de tests y `ruff` pasan sin tocar la red.
