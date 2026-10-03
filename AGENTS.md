# AGENTS.md

Python CLI (`novel_cli`) that scrapes web novels, builds EPUBs, and optionally translates to Spanish (Google free endpoint or local LibreTranslate). Spanish docs in `docs/` are authoritative (`arquitectura.md` = technical reference, `uso.md` = user guide); `specs/` holds the **versioned plan** (`specs/0.1.0/` base, `specs/0.1.1/` current changes).

## Flujo Spec-Driven Development (SDD) — Obligatorio

1. **Regla de oro:** prohibido crear o modificar código fuente sin una spec APROBADA por el
   usuario. Si llega un cambio sin documentar, el primer paso es escribir/actualizar su spec
   y confirmarla antes de implementar.

2. **Creación de spec:** crea `specs/<version>/NN-tema.md` con este frontmatter YAML (es la
   **fuente de verdad** del estado):

   ```yaml
   ---
   code: "NN"
   title: "Título conciso"
   project: "novel_cli"
   status: proposed          # proposed | approved | in-progress | completed
   version: "<version>"
   date: YYYY-MM-DD
   tags: [spec, sdd]
   affected_files:
     - src/novel_cli/...
   ---
   ```

   El cuerpo usa estas secciones: Purpose / Context / Proposed change / Technical decision /
   Affected files / Tests / Acceptance criteria. La spec describe **un** cambio; si supera
   ~300 líneas, divídela en varias specs. El estado completo del sistema vive en `docs/`
   (`arquitectura.md` = referencia técnica, `uso.md` = guía de usuario, `features.md`).

3. **Pausa dura (human-in-the-loop):** al dejar la spec en `status: proposed`, DETÉN la
   ejecución, muestra un resumen y espera confirmación explícita. No pases a `in-progress`
   ni toques código hasta que el usuario apruebe.

4. **Implementación:** con la aprobación, cambia la spec a `status: in-progress` e implementa
   el código y los tests descritos en ella.

5. **Cierre:** cuando los Acceptance criteria estén cumplidos, cambia la spec a
   `status: completed`, actualiza la documentación viva en `docs/` y anota el cambio y el
   hash del commit en `specs/<version>/00-changelog.md`.

Los specs se organizan por versión en `specs/<version>/`; los cambios nuevos se registran en
la versión actual (`00-changelog.md`) y al liberar un conjunto se sube la versión de specs.
`docs/` es la referencia autoritativa del estado actual; `specs/` es el contrato/plan por
versión. El bloque canónico para replicar este flujo está en `Dev/Prompts/sdd-base.md`.

Plantilla de `specs/<version>/00-changelog.md`:

```markdown
# Changelog — <version>

| Fecha | Spec | Cambio | Commit |
| ----- | ---- | ------ | ------ |
| YYYY-MM-DD | NN | Resumen del cambio | <hash> |
```

## Commands

- Install: `uv sync --extra dev` (requires-python >= 3.11; local venv is 3.14)
- Tests: `uv run pytest -q` — unit tests only, no network (respx + HTML fixtures in `tests/fixtures/`)
- Lint: `uv run ruff check .` (rules `E,F,I,UP,B`, line-length 100, target py311; `specs/` excluded)
- Run CLI: `uv run novel-cli <url>` (entrypoint `novel_cli.cli.app:main`)
- Run web: `uv run novel-cli web` (FastAPI + UI; `--host/--port/--no-browser`, auth via `NOVEL_WEB_TOKEN`)

## Architecture

- `src/novel_cli/core/` is **pure domain**: must not import `typer`/`rich`/read `argv`. Dependencies (fetcher, translator, output dir) are injected; progress flows out via `on_status(str)` / `on_progress(done, total)` callbacks wired to `rich` by `cli/progress.py`.
- `src/novel_cli/cli/app.py` parses args and builds the fetcher/translator; it maps domain exceptions to exit codes (1=validation, 2=network/download, 3=translation, 4=epub/manifest). `main()` dispatches `web` vs the default `run`.
- `src/novel_cli/web/` is the presentation layer (FastAPI + vanilla UI): `jobs.py` runs `run_pipeline` as background tasks (one at a time) with progress events, `routes.py` is the REST API, `ws.py` streams progress over WebSocket, `app.py` builds the app + auth (`NOVEL_WEB_TOKEN`). Reuses `core` unchanged; tests mock `web.jobs.run_pipeline`.
- `src/novel_cli/notifications/` is the notification adapter layer (python-telegram-bot). `core/notifications.py` defines the pure `Notifier` Protocol + `NotificationEvent` + `NullNotifier`; `TelegramNotifier` sends a per-job summary and error alerts. Injected into `run_pipeline` from CLI and web; configured via `NOVEL_TELEGRAM_BOT_TOKEN` / `NOVEL_TELEGRAM_CHAT_ID`.
- Pipeline: `cli/app.py -> core/services/pipeline.py -> scraper/registry (site adapter) -> toc -> download -> epub -> translate -> manifest`.
- Site adapters in `core/scraper/sites/` (`novelfire.py`, `generic.py` fallback) implement the `SiteAdapter` protocol; `registry.get_adapter(url)` picks by domain. Fetchers (`HttpFetcher` primary, `PlaywrightFetcher` JS fallback) implement the `Fetcher` protocol.

## State & resume

- Per-novel dir `output/<slug>/` holds `.manifest.json` (pydantic index), `.toc.json` (TOC cache; TTL + peek, `--refresh-toc`/`novel-cli toc`), `raw/<NNNN>.md`, `translated/<NNNN>.md` (only with `-t`), and EPUBs.
- **File existence on disk is the source of truth** for "already downloaded/translated"; the manifest is a cache. `--force` redownloads; `--no-resume` still respects existing files.
- Download is volume-by-volume (default 50 chapters per run); re-running the same command advances to the next volume. `--all` downloads everything at once. `--translate-pending` translates only pending chapters without downloading.

## Testing

- Tests must never hit the network: mock HTTP with `respx` and use fixture HTML. Never run the real CLI against live sites.
- `asyncio_mode = "auto"` (pytest-asyncio); `testpaths = ["tests"]`.
- `addopts = "-m 'not integration'"` — anything requiring real Playwright/network must be marked `@pytest.mark.integration` and stays deselected by default.

## Conventions & gotchas

- Domain models: `@dataclass`; state: `pydantic`. Interfaces: `typing.Protocol`. Use `from __future__ import annotations`.
- The CLI hits Google's free translate endpoint with conservative pacing — never raise translation concurrency. Download pool default `-c 4`, pacer ~300 ms; translation pacer default 1500 ms (env `NOVEL_TRANSLATE_PACER_MS`).
- Translation backend env: `NOVEL_TRANSLATE_BACKEND` (`google` default | `libre` for local LibreTranslate via `podman compose up -d` | `ollama` for a local LLM such as TranslateGemma via `NOVEL_OLLAMA_MODEL`), `NOVEL_TRANSLATE_URL`, `NOVEL_TRANSLATE_API_KEY`. `NOVEL_OUTPUT_DIR` sets the default output dir.
