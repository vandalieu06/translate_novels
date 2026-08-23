# 08 — Testing

## Estrategia general

- **Unit tests sin red**: fixtures de HTML (TOC, portada, capítulo) para cada adaptador y para la heurística genérica.
- **Fake HTTP con `respx`** para `HttpFetcher`: mock de respuestas por URL, sin tocar la red.
- **Playwright**: NO en CI unitario (lento). Tests de integración marcados `@pytest.mark.integration` (optativos, con `--run-integration`).
- `pytest-asyncio` para las funciones async del pool de descarga y el cliente de traducción.

## Fixtures (`tests/fixtures/`)

- `novelfire_toc.html` — página de portada/TOC NovelFire.
- `novelfire_chapter.html` — página de capítulo NovelFire.
- `generic_toc.html` — página genérica para la heurística.
- `chapter_paragraphs.txt` — contenido esperado.
- `retry_after_429.txt` — respuestas simuladas 429 con `Retry-After`.

## Tests clave

### Scraper / adaptadores
- `test_novelfire.py`:
  - `parse_toc` extrae título, portada URL, lista de capítulos con `num`/`title`/`url`.
  - `parse_chapter` extrae los párrafos correctos y en orden.
- `test_generic.py`: heurística detecta enlaces numerados, dedupe, orden por número, rechazo de no-TOC.

### Fetch / retry / pacing
- `test_fetcher.py` (respx):
  - HTTP ok → HTML.
  - 429 → retry con backoff → ok; se honor `Retry-After`.
  - 429 persistente → error tras presupuesto.
  - 502/504/timeout → retry transient.
  - Cool-down de pool: un 429 de un worker retrasa a los demás (estilo Readest).
  - `--playwright` fuerza el fallback (mock de `PlaywrightFetcher`).

### Descarga (pool)
- `test_download.py` (respx + async):
  - Descarga todos los capítulos en orden y guarda `raw/NNNN.md`.
  - Pacing: inicios separados ≥ min-interval.
  - Reanudación: si `raw/0002.md` existe, no re-descarga 0002.

### Traducción
- `test_translate.py` (respx para `translate.googleapis.com`):
  - `translate_text` concatena segmentos del JSON simulado.
  - Chunking respeta `max_words_per_chunk`.
  - Reensamblado 1:1 de párrafos.
  - Cache: capítulo traducido existente → no re-traduce.
  - Retry ante 429 del endpoint.

### EPUB
- `test_epub.py`:
  - `build_epub` genera un zip válido con `content.opf`, `toc.ncx`, capítulos XHTML, portada.
  - Volúmenes: `generate_volumes(chapters, 50)` divide correctamente (incluido último volumen corto).
  - Naming: `Novela 1-50.epub`, `Novela (ES).epub`.

### CLI / pipeline
- `test_pipeline.py` (mock de fetcher + translator):
  - Flujo completo con 3 capítulos → manifest correcto, EPUBs generados, conteos.
  - `--force` re-ejecuta; `--resume` salta fases.
- `test_cli.py` (typer `CliRunner`):
  - Validación de flags (`--volume-size 75` → error).
  - Códigos de salida.

## Comandos

```bash
pnpm/uv: uv run pytest -q                 # unit sin red
uv run pytest -q -m integration           # integración (Playwright)
uv run ruff check .                       # lint
```

Nota: es un proyecto uv, no pnpm. El comando es `uv run pytest`.

## CI objetivo

GitHub Actions: `uv sync --dev`, `ruff`, `pytest -q` (sin integración). La integración queda como job manual/optativo.