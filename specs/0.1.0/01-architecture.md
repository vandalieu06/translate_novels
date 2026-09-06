# 01 — Arquitectura

## Principio rector

`core/` es **dominio puro**: sin imports de `click`/`typer`, sin leer argv, sin barras de progreso. Recibe sus dependencias por inyección (fetcher, translator, output dir). `cli/` solo orquesta: parsea args, construye config, llama a `core`, muestra progreso/logs.

Esto permite testear `core/` sin CLI y reutilizar la lógica desde scripts o una futura API.

## Layout de módulos

```
translate_novels/
├── pyproject.toml
├── specs/                       # este plan
├── src/novel_cli/
│   ├── __init__.py
│   ├── cli/
│   │   ├── __init__.py
│   │   ├── app.py               # typer App + comando principal
│   │   └── progress.py          # rich/tqdm bars (solo CLI)
│   └── core/
│       ├── __init__.py
│       ├── config.py            # rutas por defecto, límites, env
│       ├── models/
│       │   ├── __init__.py
│       │   ├── novel.py         # Novel, Chapter, Volume, SiteMetadata (dataclasses)
│       │   └── state.py         # Manifest (JSON load/save)
│       ├── scraper/
│       │   ├── __init__.py
│       │   ├── base.py          # SiteAdapter (Protocol) + Fetcher (Protocol)
│       │   ├── fetcher.py       # httpx-first + Playwright fallback, retry/pacing
│       │   ├── registry.py      # mapping dominio → SiteAdapter
│       │   └── sites/
│       │       ├── __init__.py
│       │       ├── novelfire.py # adaptador NovelFire (del proyecto viejo, modernizado)
│       │       └── generic.py   # heurística genérica de TOC (estilo Readest chapterList)
│       ├── services/
│       │   ├── __init__.py
│       │   ├── toc.py           # obtener TOC completo de un sitio
│       │   ├── download.py      # pool async de descarga de capítulos + pacing
│       │   ├── epub.py          # construcción EPUB con ebooklib (original y traducido)
│       │   ├── translate.py     # cliente Google Translate (endpoint gratuito) + chunking + cache
│       │   └── pipeline.py      # orquesta: scrape → download → epub → translate → pack
│       └── utils/
│           ├── __init__.py
│           ├── text.py          # split_text_by_words (reutilizar del viejo translate.py), saneado
│           └── names.py         # slug de novela, naming de volúmenes (1-50, 51-100)
```

## Dependencias (pyproject nuevo, stack limpio)

```toml
[project]
name = "novel_cli"
version = "0.2.0"
requires-python = ">=3.11"

dependencies = [
    "httpx>=0.27",          # fetch HTTP primero (async)
    "playwright>=1.44",     # fallback JS
    "ebooklib>=0.18",       # construcción EPUB
    "lxml>=5",              # parsing HTML (ebooklib + selectores)
    "typer>=0.12",          # CLI (rich integrado)
    "rich>=13",             # progreso/logs
    "pydantic>=2",          # modelos/validación del manifest
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.23", "respx>=0.21", "ruff"]

[project.scripts]
novel-cli = "novel_cli.cli.app:main"
```

## Eliminado del proyecto viejo

- `ollama`, `peewee`, `pytest-playwright`, `python-dotenv` → fuera.
- `core/database/`, `core/repository/`, `db/`, migraciones ad-hoc → fuera (manifest JSON reemplaza).
- `core/models/llm.py`, `websites.py` → reemplazados por modelos limpios en `core/models/`.
- `cli/app.py` demo hardcodeado → reemplazado por typer real.
- `output/<novela>/raw/*.md` viejos → compatibles como capítulos fuente (mismo layout).

## Flujo de dependencias (core no conoce CLI)

```
cli/app.py ──> core/config.py ──> core/services/pipeline.py
                                        ├─ scraper (SiteAdapter/Fetcher)
                                        ├─ services/download.py
                                        ├─ services/epub.py
                                        ├─ services/translate.py
                                        └─ models/state.py (manifest)
```

## Barra de progreso (solo CLI)

`core` expone callbacks opcionales (`on_progress(done, total)`, `on_status(str)`) o usa generadores. La CLI los conecta a barras `rich.progress`. Core nunca importa `rich`.