# 09 — Roadmap

Hitos de implementación en orden. Cada hito es verificable de forma independiente.

## Hito 1 — Esqueleto del proyecto (stack limpio)

- [ ] `pyproject.toml` nuevo (deps del spec 01), eliminar deps viejas (ollama, peewee, pytest-playwright, python-dotenv).
- [ ] Estructura `src/novel_cli/{cli,core}/...` (spec 01).
- [ ] `novel-cli --help` responde con el comando único `run`.
- [ ] `core/config.py` con `default_output` (env `NOVEL_OUTPUT_DIR` → `./output`).
- [ ] Eliminar `db/`, `core/database/`, `core/repository/`, migraciones viejas (spec 01).

**Done cuando**: `uv run novel-cli --help` funciona y `ruff check` pasa.

## Hito 2 — Modelos + manifest

- [ ] `core/models/novel.py` (NovelMetadata, Chapter, SiteMetadata, Volume).
- [ ] `core/models/state.py` (Manifest pydantic) + load/save.
- [ ] `core/utils/names.py` (slugify, volume_name, chapter_filename).

**Done cuando**: unit tests de modelos/manifest pasan (guardar/cargar, naming).

## Hito 3 — Fetch + retry/pacing

- [ ] `core/scraper/base.py` (Fetcher, SiteAdapter Protocols).
- [ ] `core/scraper/fetcher.py`: `HttpFetcher` (httpx, headers Chrome) + `PlaywrightFetcher` (navegador persistente) + retry/backoff + pacer + cool-down gate (lecciones Readest).
- [ ] Selección de fetcher (HTTP primero, Playwright fallback; `--playwright` fuerza).

**Done cuando**: tests `test_fetcher.py` con respx pasan (429/Retry-After/transient/cool-down).

## Hito 4 — Scraper NovelFire

- [ ] `core/scraper/sites/novelfire.py` modernizado (usa Fetcher, no Playwright por llamada).
- [ ] `core/scraper/sites/generic.py` (heurística TOC estilo Readest).
- [ ] `core/scraper/registry.py` (dominio → adaptador; fallback genérico).
- [ ] `core/services/toc.py`: obtener SiteMetadata completo desde una URL.

**Done cuando**: `test_novelfire.py` + `test_generic.py` pasan; `novel-cli <novelfire-url> --volume-size 50 --no-translate` descarga y genera EPUB original correctamente.

## Hito 5 — Descarga async + estado

- [ ] `core/services/download.py`: pool async (httpx) con pacing + manifest + `raw/NNNN.md`.
- [ ] Reanudación (`--resume`/`--force`) según manifest + existencia de archivos.

**Done cuando**: `test_download.py` pasa; interrumpir a mitad y reanudar completa lo que falta.

## Hito 6 — EPUB (ebooklib)

- [ ] `core/services/epub.py`: `build_epub` + `generate_volumes`.
- [ ] Portada (local o SVG), TOC, spine, language.
- [ ] Naming de volúmenes y EPUB traducido.

**Done cuando**: `test_epub.py` pasa; los EPUBs generados se abren en un lector (calibre/Readest).

## Hito 7 — Traducción (Google gratuito)

- [ ] `core/services/translate.py`: `GoogleFreeTranslator` (endpoint `translate_a/single`, retry/pacing) + `Translator` Protocol + `OllamaTranslator` stub opcional.
- [ ] Chunking (`split_text_by_words` reutilizado) + reensamblado 1:1 de párrafos.
- [ ] Cache `translated/NNNN.md` + conteo en manifest.

**Done cuando**: `test_translate.py` pasa; `novel-cli <url> --translate --volume-size 50` genera EPUB original + traducido.

## Hito 8 — CLI completo + progreso

- [ ] `cli/app.py` completo con todos los flags (spec 06) y validación.
- [ ] `cli/progress.py` con `rich` (descarga, traducción, EPUB).
- [ ] Códigos de salida (0-4).

**Done cuando**: `test_cli.py` + `test_pipeline.py` pasan; `novel-cli --help` documenta todo.

## Hito 9 — Endurecer (opcional)

- [ ] `GenericAdapter` para 1-2 sitios más (ej. Royal Road / biquge) validados con fixtures reales.
- [ ] CI GitHub Actions (uv + ruff + pytest sin integración).
- [ ] `--translate-title` y `OllamaTranslator` real (opcional).

## Criterios de aceptación finales

1. `novel-cli <url>` descarga y genera EPUB original con portada y TOC, en la ruta por defecto.
2. `novel-cli <url> --volume-size 50` genera `Novela 1-50.epub`, `Novela 51-100.epub`, ... con la misma portada.
3. `novel-cli <url> --translate --volume-size 100` genera además `Novela 1-100 (ES).epub`, etc.
4. Interrumpir y `--resume` reanuda sin re-descargar/re-traducir lo completo.
5. `uv run pytest -q` (sin integración) en verde; `ruff check` en verde.
6. Sin SQLite, sin Ollama por defecto, sin `googletrans`.