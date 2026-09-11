# 03 — Caché del TOC

- Estado: implementado
- Versión spec: 0.2.0 · Fecha: 2026-09-11 · Relacionado: 0.1.0/03-scraper.md

## Propósito

Evitar que cada Sync recorra todas las páginas del listado del TOC cuando ya se
conoce, refrescándolo solo si hay capítulos nuevos, y con un ritmo más
conservador para las páginas de listado (menos 429/riesgo de bloqueo).

## Contexto / Problema

`fetch_site_metadata` (`core/services/toc.py`) recorre **todo** el listado
paginado en cada ejecución. En `novelphoenix.com` eso son ~54 peticiones
(`toc resuelto: 5273 capitulos ... paginas=54`) aunque el Sync solo descargue el
siguiente tomo (50). Las 429 del log salen de esas páginas de listado
(`?page=25`, `?page=53`). Repetir el crawl completo en cada Sync es tráfico
innecesario que puede escalar a un bloqueo temporal.

La descarga en sí ya está acotada: `_download_batch()` solo baja
`volume_size` capítulos; el problema es la fase de índice, no la de descarga.

## Cambio propuesto (antes → después)

**Antes**: cada Sync lee las ~54 páginas del listado.

**Después**:
- El índice se guarda en `output/<slug>/.toc.json` y se reutiliza.
- Fresco (< TTL): **0 peticiones** de listado.
- Caducado: **peek** de 2 páginas (primera y última) → si hay novedad, crawl
  completo; si no, se reutiliza la caché.
- `--refresh-toc` / `--force` fuerzan el crawl.
- Las páginas de listado se piden con un pacer propio (`NOVEL_TOC_PACER_MS`,
  default 1000 ms).

## Decisión técnica

- **Modelo** `core/models/toc.py`: `TocCache` (pydantic) con `version`,
  `source_url`, `fetched_at`, `listing_pages` (primera y última) y
  `chapters:[{num,title,url}]`; `load_toc_cache`/`save_toc_cache`.
- **Servicio** (`core/services/toc.py`):
  - `crawl_toc(fetcher, adapter, url, *, toc_pacer=None) -> (SiteMetadata,
    listing_pages)`: lógica actual + pacer + registro de la primera/última
    página que dio capítulos. `fetch_site_metadata` se conserva como wrapper.
  - `toc_changed(fetcher, adapter, cache, *, toc_pacer=None) -> bool`: peek de
    `listing_pages[0]` y `[-1]`; hay cambio si el `num` máximo supera el de la
    caché o si la última página devuelve `next_page`.
  - `site_from_cache(manifest, cache) -> SiteMetadata`: reconstruye capítulos y
    metadatos desde el manifest (sin red).
  - `make_cache(source_url, site, listing_pages) -> TocCache`.
- **Pipeline** (`run_pipeline(..., refresh_toc=False)`):
  1. Busca un manifest por `source_url` (variante no-lanzante de
     `_find_manifest_by_url`).
  2. Si `resume and not force and not refresh_toc` y hay `.toc.json`:
     - fresco (`age <= NOVEL_TOC_TTL_HOURS`) → `site_from_cache` (0 peticiones);
     - caducado → `toc_changed`; si cambió, crawl; si no, caché (y actualiza
       `fetched_at`).
  3. Si no hay caché usable → `crawl_toc` y **guarda** `.toc.json` en el
     `slug_dir`.
  - `--translate-pending` sigue sin tocar el TOC.
- **Config** `core/config.py`: `TOC_REQUEST_MIN_INTERVAL_MS` (env
  `NOVEL_TOC_PACER_MS`, default 1000) y `toc_ttl_seconds()` (env
  `NOVEL_TOC_TTL_HOURS`, default 6; `0` = siempre peek).
- **CLI**: `--refresh-toc` en el run; subcomando manual
  `novel-cli toc [--slug SLUG | --all] [--refresh] [--pacer-ms N]` (no se ejecuta
  automáticamente).
- **Web**: `JobRequest.refresh_toc` (default `False`); `/sync` usa la caché/TTL.
- **Migración**: lazy. Las novelas existentes crean su `.toc.json` en el primer
  Sync posterior (una pasada completa, igual que el comportamiento actual).

## Archivos afectados

- `src/novel_cli/core/models/toc.py` (nuevo).
- `src/novel_cli/core/services/toc.py`.
- `src/novel_cli/core/services/pipeline.py`.
- `src/novel_cli/core/config.py`.
- `src/novel_cli/cli/app.py` (`--refresh-toc`, comando `toc`, dispatch en `main`).
- `src/novel_cli/web/routes.py`, `src/novel_cli/web/jobs.py`.
- `tests/test_toc_cache.py` (nuevo).
- `docs/uso.md`, `docs/arquitectura.md`, `docs/features.md`.

## Tests

- `tests/test_toc_cache.py` (sin red, fetcher/adapter falsos):
  - `TocCache` save/load round-trip.
  - `crawl_toc` fusiona páginas, ordena y registra `listing_pages`.
  - `toc_changed`: sin cambios → `False` y 2 peticiones; `num` nuevo → `True`;
    `next_page` nuevo en la última página → `True`.
  - `site_from_cache` reconstruye capítulos/metadatos.
  - Pipeline: con manifest + caché fresca → **0** llamadas al fetcher; `force`/
    `refresh_toc` → crawl completo; el crawl escribe `.toc.json`.
  - `NOVEL_TOC_PACER_MS` respetado.
- `uv run ruff check .` y `uv run pytest -q` en verde.

## Criterios de aceptación

- Un Sync sin novedades, dentro del TTL, **no pide páginas de listado**.
- Con novedades o TTL caducado se refresca y el Sync sigue bajando el siguiente
  tomo igual que antes.
- `--refresh-toc`/`--force` fuerzan el crawl completo.
- El pacer del listado es configurable (`NOVEL_TOC_PACER_MS`) y se refleja en el
  log.
- Las novelas existentes obtienen su `.toc.json` en el primer Sync (lazy).
- `ruff` y `pytest` pasan sin tocar la red.
