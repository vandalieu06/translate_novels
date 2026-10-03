# Arquitectura de novel-cli

Documento técnico de referencia: diseño, módulos, flujo de datos, estado, red, EPUB, traducción, errores y testing.

## 1. Principios de diseño

- **`core/` es dominio puro**: no importa `typer`, `rich` ni lee `argv`. Recibe sus dependencias por inyección (fetcher, translator, directorio de salida). Así se testea sin CLI y se reutiliza desde scripts o una futura API.
- **`cli/` solo orquesta**: parsea args, construye la configuración, conecta las barras de progreso y traduce errores a códigos de salida.
- **HTTP primero, Playwright solo como fallback JS**: los sitios de novelas son server-rendered; un `httpx.AsyncClient` con headers de navegador basta y es mucho más barato.
- **Sin SQLite**: el estado vive en un `.manifest.json` por novela + archivos de capítulo en disco. Portable y editable a mano.
- **Lecciones de Readest**: pacing (~300 ms), retry con backoff, `Retry-After`, cool-down de pool, endpoint gratuito de Google Translate (`translate_a/single` con `client=gtx`), identificador estable de EPUB.

## 2. Layout del proyecto

```
translate_novels/
├── pyproject.toml              # deps, scripts, ruff/pytest
├── docs/                       # documentación (este archivo, uso, features)
├── specs/                      # plan original (00-09)
├── src/novel_cli/
│   ├── cli/                    # ORQUESTACIÓN (typer + rich)
│   │   ├── app.py              # comando por defecto `run` + subcomando `web`, exit codes 0-4
│   │   └── progress.py         # ProgressUI: barras rich conectadas a core
│   ├── web/                    # PRESENTACIÓN WEB (FastAPI + UI vanilla)
│   │   ├── app.py              # create_app() FastAPI, auth por token, main()
│   │   ├── jobs.py             # JobManager: run_pipeline en background + eventos
│   │   ├── routes.py           # API REST (jobs, novelas, EPUBs)
│   │   ├── ws.py               # WebSocket de progreso por job
│   │   ├── templates/index.html# SPA (HTML)
│   │   └── static/             # CSS (design MOSH) + JS vanilla, sin build
│   ├── notifications/          # ADAPTADORES DE NOTIFICACIÓN (presentación)
│   │   ├── __init__.py         # build_default_notifier() (Telegram o Null)
│   │   └── telegram.py         # TelegramNotifier (python-telegram-bot, solo envío)
│   ├── logging_setup.py        # configure_logging() + JOB_ID (contextvar) + filtro
│   ├── run_history.py          # RunRecord + append_run() (output/logs/runs.jsonl)
│   └── core/                   # DOMINIO PURO (sin typer/rich/argv)
│       ├── config.py           # constantes y default_output()
│       ├── notifications.py    # NotificationEvent + Protocol Notifier + NullNotifier
│       ├── models/
│       │   ├── novel.py        # NovelMetadata, Chapter, SiteMetadata, Volume
│       │   └── state.py        # Manifest (pydantic) load/save
│       ├── scraper/
│       │   ├── base.py         # Protocolos Fetcher y SiteAdapter
│       │   ├── fetcher.py      # HttpFetcher, PlaywrightFetcher, Pacer,
│       │   │                   # CooldownGate, retry/backoff, FallbackFetcher
│       │   ├── registry.py     # dominio → SiteAdapter (fallback genérico)
│       │   └── sites/
│       │       ├── novelfire.py # adaptador NovelFire
│       │       └── generic.py   # heurística TOC estilo Readest chapterList
│       ├── services/
│       │   ├── toc.py          # fetch_site_metadata(): TOC completo
│       │   ├── download.py     # pool async + raw/<NNNN>.md + portada
│       │   ├── epub.py         # build_epub() + generate_volumes()
│       │   ├── translate.py    # Google/LibreTranslate/Ollama + chunking + caché
│       │   └── pipeline.py     # orquesta scrape→download→epub→translate→pack
│       └── utils/
│           ├── names.py        # slugify, naming de volúmenes/capítulos
│           └── text.py         # clean_text, guess_chapter_num, split_text_by_words
└── tests/                      # unit tests SIN RED (respx + fixtures)
```

## 3. Flujo de dependencias

```mermaid
flowchart TD
    CLI["cli/app.py<br/>run"] -->|construye deps + callbacks| PIPE
    WEB["web/app.py<br/>create_app()"] --> JOBS["web/jobs.py<br/>JobManager"]
    JOBS -->|run_pipeline| PIPE
    PIPE["core/services/pipeline.py<br/>run_pipeline()"]
    PIPE --> REG["core/scraper/registry.py<br/>adaptador por dominio"]
    PIPE --> TOC["core/services/toc.py<br/>SiteMetadata (metadatos + capítulos)"]
    PIPE --> DL["core/services/download.py<br/>pool async + raw/&lt;NNNN&gt;.md + cover"]
    PIPE --> EPUB["core/services/epub.py<br/>EPUB original (volúmenes)"]
    PIPE --> TR["core/services/translate.py<br/>translated/&lt;NNNN&gt;.md + EPUB traducido"]
    PIPE --> STATE["core/models/state.py<br/>.manifest.json (estado/reanudación)"]
    PIPE -->|notifier| NOTIF["core/notifications.py<br/>NotificationEvent + Notifier"]
    CLI --> NOTIF
    JOBS --> NOTIF
    NOTIF -.->|implementa| TG["notifications/telegram.py<br/>TelegramNotifier (Bot.send_message)"]
```

`core` nunca importa `rich`: expone callbacks `on_status(str)` y `on_progress(done, total)` que la CLI conecta a `rich.progress` (`cli/progress.py`) y la web a eventos WebSocket (`web/jobs.py` → `web/ws.py`). El **notifier** es otro punto de inyección: `core` define el `Protocol` y el evento, y el adaptador de Telegram vive fuera de `core` (en `notifications/`), por lo que el dominio sigue puro y testeable con un `FakeNotifier`.

## 4. Flujo de datos (pipeline)

```mermaid
flowchart TD
    URL(["URL"]) --> A["1. get_adapter(url)<br/>SiteAdapter (Novelfire / Generic)"]
    A --> B["2. fetch_site_metadata(fetcher, adapter, url)<br/>tocs() → páginas de listado (next_page)<br/>parse_toc() → título, portada, autor, capítulos"]
    B --> SLUG["slug = slugify(título)<br/>output/&lt;slug&gt;/"]
    SLUG --> D["3. _download_batch()<br/>primer tomo pendiente (o todo con --all)"]
    D --> E["4. download_chapters()<br/>raw/&lt;NNNN&gt;.md (pool + pacer, resume/force)"]
    E --> F["5. _load_all_chapters()<br/>solo capítulos con archivo en disco"]
    F --> G["6. _generate_epubs()<br/>Novela 1-50.epub (solo lo que falta)"]
    G --> H{"--translate?"}
    H -->|sí| I["7. translate_chapters()<br/>translated/&lt;NNNN&gt;.md"]
    I --> J["_generate_epubs(es)<br/>Novela 1-50 (ES).epub"]
    H -->|no| K
    J --> K["Manifest.save()<br/>.manifest.json"]
```

## 5. Componentes clave

### 5.1 Modelos (`core/models/novel.py`, `core/models/state.py`)

Dataclasses del dominio:

```python
NovelMetadata(title, author, cover_url, description, language_code="auto", source_url)
Chapter(num, title, url, paragraphs: list[str])
SiteMetadata(metadata, chapters)
Volume(start, end, chapters)
```

`Manifest` (pydantic `BaseModel`, `extra="ignore"`) es el índice/estado en `output/<slug>/.manifest.json`:

```python
Manifest(schema_version, slug, title, author, source_url, language_code,
         cover_path, chapters_total, chapters_downloaded, chapters_translated,
         chapters_empty, chapters_empty_nums: list[int],
         volume_size, translated, epub_original: list[str], epub_translated: list[str],
         created_at, updated_at)
```

`chapters_downloaded` solo cuenta capítulos **con contenido**; los capítulos cuyo
parser devuelve 0 párrafos se consideran **vacíos**: se reintentan al final del
lote de descarga (`download_chapters`, con backoff configurable `EMPTY_RETRIES`)
y, si persisten, quedan en `chapters_empty` / `chapters_empty_nums` como
"pendientes de reintento" (no fallan el job). Se reportan por `on_status`, en el
CLI y en la UI web, y re-ejecutar el mismo comando los vuelve a descargar porque
un archivo vacío no cuenta como "ya descargado".

API: `Manifest.load(slug_dir) -> Manifest | None` y `manifest.save(slug_dir)`.

### 5.2 Config (`core/config.py`)

Constantes de red/retry heredadas de Readest y `default_output()`:

```python
CHAPTER_REQUEST_MIN_INTERVAL_MS = 300   # pacer de descarga
TRANSLATE_REQUEST_MIN_INTERVAL_MS = ...  # pacer traducción: 1500 (google) / 250 (libre) / 0 (ollama), env NOVEL_TRANSLATE_PACER_MS
DEFAULT_TRANSLATE_CONCURRENCY = 1         # traducción en paralelo: default google/ollama
LIBRE_TRANSLATE_CONCURRENCY = 4           # default LibreTranslate local
TRANSLATE_MAX_CONCURRENCY = 16            # tope de protección (env NOVEL_TRANSLATE_MAX_CONCURRENCY)
RETRY_TRANSIENT = 2                      # 502/504/timeout → backoff (1s, 2s)
RETRY_RATE_LIMIT = 3                     # 429/503 → backoff base 2s
RETRY_AFTER_MAX_SECONDS = 30.0
MAX_COOLDOWN_SECONDS = 30.0
DEFAULT_VOLUME_SIZE = 50                 # tomos por defecto
DEFAULT_CONCURRENCY = 4
DEFAULT_MAX_WORDS_PER_CHUNK = 400
EMPTY_RETRIES = 3                        # reintentos de capítulos vacíos (backoff EMPTY_RETRY_BACKOFF)
```

Al importar el módulo, `_load_dotenv()` carga un `.env` del directorio de trabajo (o `NOVEL_CLI_ENV_FILE`) en `os.environ` **sin sobrescribir** variables ya exportadas; después se leen todas las constantes. Así la config (p. ej. `NOVEL_TRANSLATE_BACKEND=libre`) puede vivir en un `.env` sin exportar nada al arrancar el CLI o `novel-cli web`.

Notificaciones (leídas en cada llamada para facilitar el test): `telegram_enabled()` (falso si falta `NOVEL_TELEGRAM_BOT_TOKEN` o `NOVEL_TELEGRAM_CHAT_ID`, y desactivable con `NOVEL_TELEGRAM_ENABLED=off`), `telegram_bot_token()` y `telegram_chat_id()`.

### 5.3 Scraper (`core/scraper/`)

Protocolos (`base.py`):

```python
class Fetcher(Protocol):
    async def fetch_html(self, url, *, headers=None) -> str: ...
    async def fetch_bytes(self, url, *, headers=None) -> bytes: ...
    async def aclose(self) -> None: ...

class SiteAdapter(Protocol):
    name: str
    def tocs(self, novel_url) -> list[str]: ...
    def parse_toc(self, html, base_url) -> SiteMetadata: ...
    def parse_chapter(self, html, chapter_url) -> list[str]: ...
    def next_page(self, html, base_url) -> str | None: ...
```

`fetcher.py`:

- `HttpFetcher` — `httpx.AsyncClient` con headers tipo Chrome, `follow_redirects=True`, timeout 15 s. Internamente aplica cool-down del pool → pacer → request → retry. Clasifica errores en *transient* (502/504/52x), *rate-limit* (429/503) y resto; honra `Retry-After` (segundos o fecha HTTP) con tope 30 s.
- `Pacer` — mínimo `N` ms entre inicios de requests (compartido por el pool → ~3.3 req/s).
- `CooldownGate` — si un worker recibe 429, frena al resto del pool (evita el "thundering herd").
- `PlaywrightFetcher` — **un único navegador persistente** (lazy, se lanza en el primer fetch), `wait_until="networkidle"`. Nada de `launch()` por llamada.
- `FallbackFetcher` / `get_fetcher()` — HTTP primero; ante `FetchError` reenvía por Playwright; con `--playwright` fuerza PW directamente. Los fallos de PW se envuelven como `FetchError` (→ exit 2).

Secuencia de una petición con clasificación de errores y fallback:

```mermaid
sequenceDiagram
    participant P as pipeline / download
    participant F as FallbackFetcher
    participant H as HttpFetcher
    participant G as CooldownGate + Pacer
    participant W as PlaywrightFetcher
    P->>F: fetch_html(url)
    F->>H: intenta HTTP primero
    H->>G: cool-down → pacer → request
    alt 2xx
        G-->>H: HTML
        H-->>F: HTML
    else transient (502/504/52x)
        G-->>H: backoff (RETRY_TRANSIENT)
        H->>H: reintento
    else rate-limit (429/503)
        G-->>H: Retry-After (tope 30 s)
        H->>H: backoff y reintento
    else FetchError
        F->>W: reenvío por navegador persistente
        W-->>F: HTML (networkidle)
    end
    F-->>P: HTML
```

`registry.py` → `get_adapter(url)`: mapa `{dominio: clase}` con `GenericAdapter` como fallback.

Adaptadores (`sites/`):

- `NovelfireAdapter` — selectores `{ .novel-title, .fixed-img .cover img, #chpagedlist .chapter-list li a, #chapter-container #content p }`; `tocs()` → página de portada + `/chapters`; `next_page()` lee `.page-link[rel="next"]`.
- `GenericAdapter` — heurística TOC estilo Readest `chapterList.ts`: enlaces con texto numerado (`Chapter N`, `第N章`, `Capítulo N`) o href con digit runs; elige el contenedor más profundo con la mayoría de candidatos; metadatos de `og:title`/`og:image`/`meta[name=author]`; dedupe y orden por número.

`services/toc.py` → `crawl_toc()` recorre las páginas de listado del adaptador y fusiona metadatos + capítulos, registrando la primera/última página (para el peek de la caché). `fetch_site_metadata()` se conserva como wrapper. El índice se **cachea** en `output/<slug>/.toc.json` (ver §5.12).

### 5.4 Descarga (`core/services/download.py`)

- `download_chapters(...)` — pool async (`asyncio.Semaphore(concurrency)`) + `Pacer` compartido. Cada worker: `fetcher.fetch_html(url)` → `adapter.parse_chapter()` → escribe `raw/<NNNN>.md`. Respeta reanudación por **existencia de archivo**; con `force` re-descarga todo el lote.
- `is_chapter_empty(paragraphs)` — un capítulo es vacío si el parser devuelve 0 párrafos con contenido. Los vacíos **no** cuentan como descargados y se **reintentan al final del lote** (secuencial, con backoff `EMPTY_RETRY_BACKOFF`). Si persisten quedan en `manifest.chapters_empty(_nums)` y se reportan; re-ejecutar el comando los re-descarga porque un archivo vacío no cuenta como hecho.
- `download_cover(...)` → `cover.<ext>` (jpg/png/webp...).
- `load_chapter(path, num, url)` — reconstruye un `Chapter` desde `raw/` o `translated/` (formato: `# título` + párrafos separados por `\n\n`).

### 5.5 EPUB (`core/services/epub.py`)

- `build_epub(*, title, author, language, identifier, chapters, cover_path, translated=False, include_end_page=True) -> bytes` — genera `content.opf`, `toc.ncx`, `nav.xhtml`, un XHTML por capítulo (`<h1>` + un `<p>` por párrafo, 1:1), portada local (imagen) o SVG generado, `spine` ordenado por número, `language` correcto y `identifier` estable. Con `include_end_page` añade `end.xhtml` al final del spine: `FIN`/`THE END` según el idioma + ficha del tomo (título, rango `start–end`, autor, idioma de traducción si `translated`); la página queda **fuera del TOC**.
- `stable_identifier(source_url)` — hash SHA-1 de la URL → `urn:novel-cli:<hash>` (re-imports deterministas).
- `generate_volumes(chapters, volume_size)` — divide en `Volume(start, end, chapters)`; el último tomo puede ser corto; `None` → un solo volumen.

En el pipeline (`pipeline.py`), `_generate_epubs` acepta `rebuild` (default `False`): con `rebuild=True` **reescribe los EPUB existentes aunque haya `resume`** (lo usan las vías de traducción, para que los EPUB `(ES)` reflejen siempre las traducciones actuales). Tras generar, `_cleanup_orphan_epubs` **borra del disco los `*.epub` que ya no están en `epub_original`+`epub_translated`** (restos de generaciones anteriores). Las vías de solo-traducción refrescan además `chapters_empty` desde el disco (`refresh_empty_counts`).

`_build_epub_chapters(reference, chapter_dir, placeholder)` construye la lista de capítulos de un EPUB **del mismo tamaño/orden que la lista raw de referencia**: los archivos existentes se cargan (y si quedaron vacíos se sustituyen por el placeholder), y los que faltan (capítulos sin traducir) se crean con el placeholder. Así los tomos del EPUB traducido **se alinean** con los del original y no hay páginas en blanco (`EMPTY_PLACEHOLDER_EN`/`EMPTY_PLACEHOLDER_ES`).

`rebuild_volumes(slug_dir, volume_size)` reconstruye los EPUBs con un nuevo tamaño de tomo **sin red** (desde el disco): valida el tamaño (`None` = un único EPUB/ALL, o `>= 1`), actualiza `manifest.volume_size`, regenera original y traducido con `rebuild=True`, limpia huérfanos y refresca `chapters_empty`. Es la base del endpoint `POST /api/novels/{slug}/volume-size`.

### 5.6 Traducción (`core/services/translate.py`)

- `GoogleFreeTranslator` — `GET translate.googleapis.com/translate_a/single?client=gtx&dt=t&sl=auto&tl=<target>&q=<texto>`; concatena los `segment[0]` de `data[0]`. Retry/pacing propios (pacer 1500 ms por defecto, backoff ante 429/5xx honrando `Retry-After`). El `Translator` acepta `target` por llamada (default `es`), igual que LibreTranslate (`payload["target"]`).
- `translate_paragraphs()` — traduce párrafo a párrafo con chunking (`split_text_by_words`, ~400 palabras) y **reensamblado 1:1** (los párrafos vacíos no llaman al endpoint).
- `translate_chapters(...)` — caché en `translated/<NNNN>.md`; solo traduce lo que falta; actualiza `manifest.chapters_translated`. **Paraleliza capítulos** con `concurrency` (patrón `asyncio.Semaphore` + `gather`, igual que la descarga); el `Pacer`/`CooldownGate` compartidos limitan el ritmo global de peticiones incluso en paralelo. Los capítulos **vacíos** (sin contenido en `raw/`) no se traducen ni se marcan como traducidos; un `translated/<NNNN>.md` **vacío** (heredado de cuando el raw estaba vacío) **no cuenta como ya traducido** — si el raw tiene contenido se re-traduce, y si el raw sigue vacío se limpia (para que el EPUB traducido no incluya capítulos en blanco).
- `OllamaTranslator` — backend opcional de **LLM local** (`NOVEL_TRANSLATE_BACKEND=ollama`): `POST /api/chat` con el prompt oficial de TranslateGemma (una user message, modelo default `translategemma:4b`), timeout propio (`NOVEL_OLLAMA_TIMEOUT`, 300 s) y `keep_alive`. El modelo devuelve una línea por párrafo; si no cuadra el recuento, reintenta con una instrucción *"Preserve the paragraph breaks"* y, si persiste, traduce **línea a línea** (un párrafo por llamada) con un `WARNING` (nunca falla el job ni deja párrafos vacíos). `Pacer` 0 y concurrencia 1 (una GPU).

Decisión de caché por capítulo (no re-traduce lo ya hecho; un `translated/` vacío no cuenta):

```mermaid
sequenceDiagram
    participant T as translate_chapters
    participant C as translated/NNNN.md
    participant X as Translator (Google / libre)
    T->>C: ¿existe y no está vacío?
    alt caché válida
        C-->>T: se reutiliza (sin llamada)
    else falta o vacío
        T->>X: translate_paragraphs(target)
        X-->>T: párrafos reensamblados 1:1
        T->>C: escribe la traducción
    end
```

**Idioma destino**: `config.TRANSLATE_TARGET_LANGUAGES` (código→etiqueta) es la lista curada (`es, en, fr, de, it, pt, ru, ja, ko, zh`); default `config.translate_target_default()` (env `NOVEL_TRANSLATE_TARGET`). El target viaja por `run_pipeline(..., target)` → `translate_chapters(target=...)` y se persiste en `manifest.translated_language` (compatible con manifests viejos: `translated=True` sin idioma ⇒ `es`). El sufijo de los EPUB traducidos y el `language=` del metadato usan el target (no `(ES)` fijo); `rebuild_volumes` los reconstruye con el idioma guardado.

Concurrencia y protección (`core/config.py`): `translate_concurrency_default()` devuelve **1** para `google`/`ollama` y **4** para `libre` (o `NOVEL_TRANSLATE_CONCURRENCY` si se define). `effective_translate_concurrency(requested)` es la capa de protección: **fuerza 1** si el backend es `google` o `ollama` (rate-limit / una GPU) y limita a `TRANSLATE_MAX_CONCURRENCY` (16) para `libre`. El pacer default es 1500 ms (google) / 250 ms (libre) / 0 (ollama), sobrescribible por `NOVEL_TRANSLATE_PACER_MS`. El `source` de cada capítulo viaja desde `manifest.language_code` (`"auto"` → el default del backend: `en` para Ollama). Ambos se aplican en `run_pipeline` (y en `--translate-pending`).

### 5.7 Pipeline (`core/services/pipeline.py`)

`run_pipeline(...)` orquesta todo. Decisiones clave:

- **Descarga por tomos**: `_download_batch()` devuelve el primer tomo pendiente (primeros `volume_size` capítulos del TOC sin archivo en `raw/`) salvo `--all` o `volume_size=None`. Re-ejecutar avanza al siguiente tomo.
- **EPUB incremental**: `_generate_epubs()` escribe solo los EPUB que falten (o todos con `--force`); al re-ejecutar añade `Novela 51-100.epub` sin reescribir `1-50`.
- `_load_all_chapters()` carga solo capítulos con archivo en disco → nunca genera EPUB vacíos de tomos no descargados.
- **Notificaciones**: `run_pipeline(..., notifier=..., operation=...)` emite un `job_started` al inicio y luego `NotificationEvent`s estructurados en los hitos (`scrape_done`, `download_done`, `epub_original_done`, `translate_done`, `epub_translated_done`) con los contadores/idioma en `data`, y un `job_done`/`job_error` terminal con `operation` (descarga/sync/traducción/re-traducción). La emisión va envuelta para que un fallo del notifier nunca rompa el pipeline; `_phase_from_error()` clasifica la excepción (descarga/traducción/epub-manifest) para el aviso.

### 5.8 Importación de PDFs (`core/services/pdf_import.py`)

Reutiliza **pdf-to-epub** como librería (dependencia `pdf-to-epub` en `pyproject.toml`,
editable desde `../pdf-to-epub`):

- `convert_pdf(pdf_path, workdir, ...)`: llama a `pdf_to_epub.core.pipeline.run()` con
  `keep_intermediate=True` (CPU intensivo; en la web se ejecuta en `asyncio.to_thread`) y a
  `extract_docx_chapters(docx_path)` → mapea `TextChapter` a `Chapter` (párrafos planos).
- `run_pdf_pipeline(...)`: genera el **EPUB original** (el de pdf-to-epub, formato rico),
  guarda `source.pdf` + portada, escribe `raw/<NNNN>.md` y, si `target != source`, traduce
  (`translate_chapters(source=...)`) y genera el EPUB traducido con el builder de novel_cli.
- `Manifest.source_pdf` distingue novelas PDF de web: `rebuild_volumes`/`volume-size`
  regeneran **solo el traducido** y conservan intacto el original rico.
- Reutiliza los helpers del pipeline (ahora públicos): `generate_epubs`,
  `build_epub_chapters`, `load_all_from_disk`, `translated_placeholder`,
  `cleanup_orphan_epubs`.

### 5.9 CLI (`cli/app.py`, `cli/progress.py`)

- `cli/app.py` expone apps typer separadas y `main()` despacha: `novel-cli <url>` (comando por defecto `run`), `novel-cli pdf`, `novel-cli web` y `novel-cli toc`.
- `run(url, -o, -v, -t, --resume/--no-resume, -f, --all, -p, -c, -V)`.
- `pdf(file, --source, -t, --target, -v, -o)`.
- Validación: URL http(s), `-v ∈ {50, 100}`, `-c ≥ 1` → exit 1.
- `ProgressUI` (`cli/progress.py`) conecta `on_status`/`on_progress` de core a barras `rich.progress` (descarga, traducción, EPUB).

### 5.10 Web (`web/`)

Capa de presentación web (FastAPI + Uvicorn) que reutiliza `core` tal cual. `web/` no contiene lógica de dominio:

- `jobs.py` — **JobManager**: cada job lanza `run_pipeline` como `asyncio.create_task` dentro del event loop de Uvicorn (un job activo a la vez). Construye su propio fetcher/translator/notifier por ejecución y los cierra en `finally`. Los callbacks `on_status`/`on_progress` del pipeline publican **eventos** (`{type, phase, done, total, message}`) a un buffer + suscriptores.
- `routes.py` — API REST: `GET /api/jobs` (lista de jobs con su `state`, para que la UI detecte un job activo), `POST /api/jobs` (valida como el CLI; acepta `target_language`), `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`, `GET /api/novels`, `GET /api/novels/{slug}` (incluye `translated_language`), `GET /api/novels/{slug}/epub/{file}`, `GET /api/novels/{slug}/cover`, `POST /api/novels/{slug}/sync` (hereda idioma y tamaño de tomo), `POST /api/novels/{slug}/retranslate` (solo-traducción de pendientes con opciones del manifest; acepta `{target_language}` y **fuerza la re-traducción** si el idioma cambia), `POST /api/novels/{slug}/volume-size` (cambia el tamaño de tomo y reconstruye los EPUBs desde el disco), `POST /api/novels/{slug}/rebuild` (reconstruye los EPUBs con el mismo `volume_size`, sin cambiar nada: aplica mejoras del builder como la página final), `GET /api/config` (incluye `translate_backend`, `translate_languages`, `default_translate_target` y `telegram_enabled`).
- `ws.py` — WebSocket `/api/jobs/{id}/ws`: reenvía los eventos del job al cliente (reusa el mismo mecanismo de callbacks que `rich`).
- `app.py` — `create_app(output_dir)` monta static/templates y aplica auth opcional por token (`NOVEL_WEB_TOKEN`, cabecera `X-Auth-Token`). Sirve **4 páginas** (`GET /`, `/biblioteca`, `/ayuda` y `/novela/{slug}`). `main()` arranca Uvicorn (`--host`/`--port`/`--no-browser`).
- `templates/` + `static/` — UI **multi-página** responsive sin build (CSS con tokens de `DESIGN.md` + JS vanilla por página): `index.html` (descarga + progreso + novelas recientes), `library.html` (grid de portadas), `novel.html` (ficha de novela con acciones y EPUBs) y `help.html` (guía estática de acciones). El JS se parte en módulos compartidos: `common.js` (auth/api/toast/config/escapeHtml), `jobs.js` (job lock, WebSocket + polling, panel de progreso, cancelar, sync/retraducción) y uno por página (`app.js`, `library.js`, `novel.js`). Las páginas leen los datos de la API existente; el slug de la ficha lo obtiene `novel.js` de la ruta.

El **sync** (`POST /api/novels/{slug}/sync`) es el "obtener nuevos capítulos" de la biblioteca: carga el `Manifest` del slug, valida su `source_url` y crea un job con `url = manifest.source_url`, `resume=true`, `all=false`, heredando `volume_size` y `translate` (si la novela ya se traducía, los nuevos capítulos también se traducen). Como el pipeline con `resume` y sin `--all` descarga el **siguiente tomo pendiente**, el sync avanza la novela un tomo sin re-pegar la URL.

Sobre puertos: la web escucha en **un único puerto** (default `8000`). El WebSocket no abre otro puerto: usa el mismo del servidor HTTP en `/api/jobs/{id}/ws` (upgrade HTTP→WS). Los demás números que aparecen en los logs de Uvicorn (p. ej. `127.0.0.1:41570`) son **puertos efímeros de origen** del cliente, asignados por el SO a cada conexión TCP y cambiantes en cada request; no hay que abrirlos en el firewall.

### 5.10 Notificaciones (`core/notifications.py`, `notifications/`)

- **Contrato en core**: `NotificationEvent` (`@dataclass`: `kind`, `phase`, `title`, `detail`, `ok`, `data`), `Protocol Notifier` (`notify`/`aclose`) y `NullNotifier`. `core` no importa `telegram`.
- **Adaptador**: `notifications/telegram.py` implementa `TelegramNotifier` con `telegram.Bot` (python-telegram-bot, solo `send_message`; sin `Updater`/polling/webhook). Acumula los hitos y, al recibir `job_done`, manda **un resumen** en HTML (`parse_mode=ParseMode.HTML`) con la operación y la duración (medida con `time.monotonic()` desde el `job_started` hasta el evento terminal); ante `job_error` avisa de inmediato con la fase. La línea de traducción distingue lo traducido en el run (`translated_new`) del total (`translated_total`). Título y detalle se escapan (`html.escape`) y se recortan. Cada envío va en `try/except` (un fallo de Telegram no afecta al pipeline). `build_default_notifier()` (en `notifications/__init__.py`) devuelve el notifier de Telegram si `config.telegram_enabled()`, o `NullNotifier`.
- **Inyección**: CLI y web construyen el notifier y lo cierran en su `finally`; `/api/config` expone `telegram_enabled`.
- **Dependencia**: `python-telegram-bot>=21` (exige `httpx>=0.27,<0.29`, por eso `pyproject.toml` acota `httpx`).

### 5.11 Logging e historial (`logging_setup.py`, `run_history.py`)

- **`core` puro**: los módulos de dominio solo usan `logging.getLogger(__name__)`; no configuran handlers. `fetcher`, `download`, `translate`, `toc` y `pipeline` registran fases, reintentos/backoff, `429`/`Retry-After`, fallback HTTP→Playwright, capítulos vacíos y caché de traducción.
- **`configure_logging(*, output_dir, verbose=False, force=False)`** (infra, invocado por los `main()`/entrypoints, nunca por `create_app`): fichero `output/logs/novel-cli.log` con `RotatingFileHandler` (5 MiB × 3, o `NOVEL_LOG_FILE`/`NOVEL_LOG_MAX_BYTES`/`NOVEL_LOG_BACKUPS`) y consola a WARNING (DEBUG con `-V`). El nivel del fichero es `NOVEL_LOG_LEVEL` o DEBUG con `verbose`. Idempotente y con `propagate=False` en el logger `novel_cli`.
- **`job_id`**: `contextvars.ContextVar` fijado por `JobManager._run` (y `"cli"` en el run de CLI); un `logging.Filter` lo inyecta en cada registro (`[job_id]`), de modo que los logs concurrentes de la web quedan correlacionados.
- **Historial**: `run_history.RunRecord` (`@dataclass`) + `append_run(output_dir, record)` escribe `output/logs/runs.jsonl` (una línea por ejecución, con operación, estado, duración, contadores del manifest y error). `record_from_manifest()` construye el registro desde el manifest final. CLI y web lo llaman en éxito/error/cancelación; un fallo al escribir el historial se registra pero no rompe el job.
- **Privacidad**: nunca se escriben tokens de Telegram ni API keys.

### 5.12 Caché del TOC (`core/models/toc.py`)

- **Problema**: `crawl_toc` recorre todo el listado paginado; en sitios grandes son ~54 peticiones por Sync aunque no haya novedades (riesgo de 429/bloqueo).
- **`TocCache`** (`output/<slug>/.toc.json`): `version`, `source_url`, `fetched_at`, `listing_pages` (primera/última página con capítulos) y `chapters:[{num,title,url}]`.
- **`_resolve_toc`** (en `pipeline.py`):
  1. Busca un manifest por `source_url` (variante no-lanzante).
  2. Con caché y `resume`/sin `force`/sin `refresh_toc`:
     - **fresca** (`age <= NOVEL_TOC_TTL_HOURS`) → `site_from_cache` (0 peticiones);
     - **caducada** → `toc_changed` (peek de 2 páginas: `num` máximo o `rel=next` nuevo) → crawl solo si hay novedades; si no, reutiliza y actualiza `fetched_at`.
  3. Sin caché usable → `crawl_toc` y guarda `.toc.json` (`make_cache`).
- **Pacer de listado**: `NOVEL_TOC_PACER_MS` (default 1000 ms) se aplica en cada página del crawl/peek.
- **CLI**: `--refresh-toc` (bypass) y subcomando manual `novel-cli toc [--slug|--all] [--pacer-ms]`. **Migración**: lazy (las novelas existentes crean su caché en el primer Sync).

## 6. Estado en disco y reanudación

```
output/<slug>/
├── .manifest.json   # índice/estado
├── cover.jpg
├── raw/0001.md ... raw/NNNN.md       # idioma original
├── translated/0001.md ...            # traducción (si -t)
└── Novela 1-50.epub ...              # + (ES) si -t
```

Reglas:

- La **existencia del archivo** es la fuente de verdad de "ya descargado/traducido"; el manifest es caché/índice.
- `--resume` (default): se saltan fases completas y no se reescriben EPUB existentes.
- `--force`: re-descarga y re-traduce todo.
- `--no-resume`: no consulta el manifest, pero la existencia de archivos sigue evitando re-descargas.
- Tras cada fase se escribe el manifest (`chapters_total`/`chapters_downloaded`/`chapters_translated` consistentes).

Ciclo de vida de un capítulo (la existencia de archivo en disco manda; el manifest es caché):

```mermaid
stateDiagram-v2
    [*] --> Pendiente: capítulo en el TOC
    Pendiente --> Descargado: raw/NNNN.md con párrafos
    Pendiente --> Vacio: el parser devuelve 0 párrafos
    Vacio --> Descargado: reintento al final del lote
    Vacio --> ReintentoPendiente: persisten vacíos (EMPTY_RETRIES)
    ReintentoPendiente --> Descargado: re-ejecutar (un archivo vacío no cuenta)
    Descargado --> Traducido: --translate / --translate-pending
    Traducido --> [*]
```

## 7. Errores y códigos de salida

| Código | Origen |
|---|---|
| `0` | Éxito |
| `1` | Validación de entrada |
| `2` | `FetchError` / `DownloadError` (red/descarga, incl. fallback PW) |
| `3` | `TranslateError` |
| `4` | `PipelineError` u otro inesperado (EPUB/manifest) |

Excepciones de dominio: `FetchError`, `FetchRateLimitedError`, `DownloadError`, `TranslateError`, `PipelineError`. `core` las lanza; `cli/app.py` las mapea a códigos.

## 8. Concurrencia y pacing

- Descarga: `asyncio.Semaphore` (default 4 workers) + `Pacer` compartido (300 ms) → ~3.3 req/s agregadas.
- Traducción: `asyncio.Semaphore` (default 1 google/ollama / 4 libre, `-tc`) + `Pacer` compartido (1500 ms google / 250 ms libre / 0 ollama). El pacer limita el ritmo **agregado global** de peticiones, por lo que el paralelismo solapa latencia/CPU sin disparar el rate global.
- Protección: `effective_translate_concurrency()` fuerza 1 para `google` (no quemar el endpoint gratuito) y `ollama` (una GPU) y topa en `TRANSLATE_MAX_CONCURRENCY` (16) para `libre`.
- Cool-down de pool ante 429: `CooldownGate` compartido (tope 30 s) frena a todos los workers.

## 9. Testing

- **Unit tests sin red**: fixtures HTML en `tests/fixtures/` (`novelfire_cover.html`, `novelfire_toc.html`, `novelfire_chapter.html`, `generic_toc.html`, `generic_no_toc.html`).
- **HTTP falso con `respx`**: `test_fetcher.py` (429/Retry-After/transient/cool-down/fallback), `test_download.py`, `test_translate.py`.
- **Web con `TestClient` de FastAPI** (`test_web.py`): se mockea `web.jobs.run_pipeline` para no tocar la red; se prueban rutas, validación, auth por token y descarga de EPUB.
- **Notificaciones** (`test_notify.py`): `FakeNotifier` captura los eventos del pipeline (hitos + `job_done`/`job_error`), se prueba el formato del resumen/error, la selección por env (`build_default_notifier`/`telegram_enabled`) y que un notifier roto no rompe el pipeline. Nunca se instancia el bot real.
- **Logging/historial** (`test_logging.py`): `configure_logging` (fichero, niveles, rotación, idempotencia), `_JobIdFilter`, `append_run` (JSONL) y `record_from_manifest`; `create_app()` no escribe ficheros.
- **Caché del TOC** (`test_toc_cache.py`): round-trip de `TocCache`, `crawl_toc` (páginas + orden), `toc_changed` (sin cambios / capítulo nuevo / página nueva) y `_resolve_toc` (caché fresca → 0 peticiones, peek, `force`/`refresh_toc`).
- `pytest-asyncio` (`asyncio_mode="auto"`) para las funciones async.
- `pytest.ini_options.addopts = "-m 'not integration'"`: Playwright queda fuera del CI unitario (marcas `integration` reservadas).
- Comandos: `uv run pytest -q` y `uv run ruff check .` (rules `E,F,I,UP,B`, line-length 100, target py311).

## 10. Convenciones de código

- Modelos de dominio: `@dataclass`; estado: `pydantic`.
- Interfaces intercambiables: `typing.Protocol` (`Fetcher`, `SiteAdapter`, `Translator`, `Notifier`).
- `core` no importa `typer`/`rich`/`argv`; el progreso entra por callbacks.
- Naming estable en `core/utils/names.py` (`slugify`, `volume_name`, `chapter_filename`).
- `from __future__ import annotations`, docstrings en módulos, `# noqa` solo cuando aporta.