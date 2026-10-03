# Features de novel-cli

## Features actuales (implementadas)

### Descarga y scraping
- **HTTP primero, Playwright como fallback**: `httpx` async con headers de navegador; si falla, reenvío por Playwright (navegador persistente). `-p/--playwright` fuerza el navegador.
- **Adaptador NovelFire** (`novelfire.net`) con selectores específicos y paginación de listado.
- **Adaptador genérico**: heurística de TOC estilo Readest (enlaces numerados, dedupe, orden, `og:title`/`og:image`/`meta author`) para cualquier sitio.
- **Descarga por tomos**: por defecto baja solo el primer tomo (50 capítulos); re-ejecutar el mismo comando avanza al siguiente tomo. `--all` descarga todo de golpe. Tamaños: `-v 50|100|150|200`.
- **Concurrencia configurable** (`-c`, default 4) con pacing (~300 ms) y cool-down de pool ante 429/`Retry-After` (lecciones de Readest).
- **Capítulos vacíos**: si un capítulo sale sin contenido (0 párrafos), se **reintenta** al final del lote con backoff; si persiste queda como "pendiente de reintento" (`chapters_empty` en manifest), **no cuenta como descargado** y se vuelve a descargar al re-ejecutar.

### Estado y reanudación
- **Sin SQLite**: `.manifest.json` por novela + capítulos en `raw/` y `translated/`.
- **`--resume`** (default): salta fases completadas y no reescribe EPUB existentes (idempotente).
- **`--force`**: re-descarga y re-traduce todo desde cero.
- La existencia de archivo en disco es la fuente de verdad de "ya descargado/traducido".

### EPUB
- **ebooklib + lxml**: `content.opf`, `toc.ncx`, `nav.xhtml`, un XHTML por capítulo con `<h1>` + un `<p>` por párrafo (estructura original 1:1).
- **Volúmenes**: `-v 50|100|150|200` → `Novela 1-50.epub`, `Novela 51-100.epub`, ... con la **misma portada** (imagen local o SVG generado). `volume_size=None` genera un único EPUB ("ALL").
- **Identificador estable** derivado de la URL (re-imports deterministas).
- **Placeholders**: un capítulo sin contenido (raw vacío o sin traducción) lleva un aviso (`(Chapter content not available…)` en original, `(Capítulo sin contenido disponible…)` en ES) en vez de salir en blanco.
- **Tomos alineados**: el EPUB traducido usa la misma partición que el original aunque falten capítulos (`_build_epub_chapters`).
- **Regeneración**: las vías de traducción reescriben los EPUB `(ES)` existentes (`rebuild=True`); los EPUBs huérfanos (fuera del manifest) se limpian del disco. `rebuild_volumes` reconstruye los EPUBs con un nuevo tamaño desde el disco sin red.

### Traducción
- **Endpoint gratuito de Google Translate** (`translate_a/single` con `client=gtx`), sin clave ni token.
- **Backend intercambiable**: local **LibreTranslate** (`NOVEL_TRANSLATE_BACKEND=libre`, Docker/podman) o **LLM local vía Ollama** (`ollama`, p. ej. `translategemma:4b`) con el prompt oficial de TranslateGemma, sin dependencias Python extra. Config persistente con un `.env` (cargado al arrancar). Con `LT_API_KEYS`/`NOVEL_TRANSLATE_API_KEY` se omite el rate-limit por defecto de LibreTranslate (200 req/día/IP) que rompía re-traducciones largas con 429.
- **Aceleración CUDA**: `docker-compose.cuda.yaml` usa la imagen `latest-cuda` con GPU NVIDIA (se lanza con `sudo docker compose`), DNS público fijado para evitar el fallo por MagicDNS de Tailscale.
- **Párrafo a párrafo** con chunking (~400 palabras) y **reensamblado 1:1**; el EPUB traducido conserva la estructura del original.
- **Caché en disco** (`translated/<NNNN>.md`): no re-traduce lo ya hecho; retry/pacing ante 429/503. Un `translated/` vacío (heredado de un capítulo sin contenido) no cuenta como traducido: se re-traduce si el raw se arregló y se limpia si sigue vacío.
- **Traducción en paralelo por lotes** (`-tc/--translate-concurrency`): traduce varios capítulos a la vez con pool async (patrón igual a la descarga). Default inteligente por backend (1 google/ollama / 4 libre) y **capa de protección**: google y ollama fuerzan 1 (endpoint gratuito / una GPU), libre topa en 16. El pacer compartido mantiene el ritmo global de peticiones.
- **Idioma destino elegible** (`--target <lang>`): lista curada (`config.TRANSLATE_TARGET_LANGUAGES`: es, en, fr, de, it, pt, ru, ja, ko, zh; env `NOVEL_TRANSLATE_TARGET`). `-t/--translate` genera el EPUB original **y** el traducido (`Novela 1-50 (ES).epub`, sufijo según idioma).
- **`--translate-pending`**: traduce solo los capítulos pendientes (ya descargados, sin traducir) sin descargar nuevos ni tocar el TOC — ideal para retomar una traducción cortada por rate-limit.

### Importación de PDFs (spec 0.3.0/01)
- **`novel-cli pdf <archivo>`**: importa un PDF de novela (webnovel o light novel con
  ilustraciones) reutilizando **pdf-to-epub** como librería.
- **EPUB original rico**: lo genera pdf-to-epub y conserva imágenes, tablas y formato del
  PDF (`{titulo}.epub`, un solo tomo). El PDF y la portada se guardan en
  `output/<slug>/source.pdf` y `output/<slug>/cover.<ext>`.
- **Texto plano extraído del DOCX** intermedio (`raw/<NNNN>.md`) para traducir y regenerar
  tomos; el EPUB traducido se genera con el builder de novel_cli (tomos según `--volume-size`).
- **Traducción opcional**: `-t/--translate` + `--source <lang>` (default `es`) + `--target`;
  si `target != source` genera el EPUB traducido además del original. Nunca `auto` como origen.
- **`Manifest.source_pdf`**: distingue novelas PDF de web; `rebuild_volumes`/`volume-size`
  regeneran **solo el EPUB traducido** y conservan intacto el original rico.
- **Límite de subida** para la web: `NOVEL_UPLOAD_MAX_MB` (default 100).

### CLI
- Comando único `novel-cli <url>` con flags `-o`, `-v`, `-t`, `--resume/--no-resume`, `-f`, `--all`, `-p`, `-c`, `-tc`, `-V`.
- Comando **`novel-cli pdf <archivo>`** para importar PDFs (con `--source`, `-t`, `--target`, `-v`).
- **Códigos de salida** `0-4` (éxito, validación, red/descarga, traducción, EPUB/manifest).
- **Barras de progreso** con `rich` (descarga, traducción, EPUB) y logs detallados con `-V`.
- Ruta por defecto: env `NOVEL_OUTPUT_DIR` o `./output`.
- **Config vía `.env`**: `_load_dotenv` carga un `.env` del directorio de trabajo (o `NOVEL_CLI_ENV_FILE`) al arrancar, sin sobrescribir variables ya exportadas.

### Web (`novel-cli web`)
- **FastAPI + Uvicorn**: servidor con UI responsive (mobile-first) servida por el propio backend, sin toolchain de build (HTML + CSS + JS vanilla).
- **Diseño MOSH** (`DESIGN.md`): coral `#fa6f78` + grayscale, IBM Plex Sans JP / system-ui, CTA negros, flat con bordes 1px, headings weight 400, degular para números grandes.
- **Jobs en background**: cada descarga/traducción corre como `run_pipeline` en un job (un job activo a la vez) con su propio fetcher/translator y cierre limpio.
- **Concurrencia de traducción en la UI**: campo "Concurrencia traducción" en el form, visible solo al activar "Traducir"; se envía como `translate_concurrency`.
- **Progreso en vivo por WebSocket** (`/api/jobs/{id}/ws`): fases de descarga, traducción y EPUB con los mismos callbacks que `rich`.
- **Sync de novelas** (`POST /api/novels/{slug}/sync`): botón **↻ Sync** en cada ficha para obtener nuevos capítulos sin re-pegar la URL; hereda traducción, idioma y tamaño de tomo de la novela.
- **Traducir** (`POST /api/novels/{slug}/retranslate` con `{target_language}`): botón **🌐 Traducir** en la ficha de novelas no traducidas que abre un **modal de idiomas**; si el idioma cambia, re-traduce todo (sin descargar). **📝 Re-traducir** (novelas traducidas) traduce solo los pendientes y regenera los EPUB en el idioma guardado.
- **Cambiar tamaño de tomo** (`POST /api/novels/{slug}/volume-size`): botón **📄 Tomos N** abre un modal con píldoras **50 · 100 · 150 · 200 · ALL**; al elegir una se reconstruyen los EPUBs (original y traducido) con el nuevo tamaño y se actualiza el manifest.
- **Regenerar EPUBs** (`POST /api/novels/{slug}/rebuild`): botón **♻ Regenerar EPUBs** en la ficha; reconstruye los tomos (original y traducido) desde disco sin cambiar el tamaño ni descargar (aplica mejoras del generador, como la página final `FIN`).
- **Job lock en el servidor**: la UI consulta `GET /api/jobs` (estados `pending`/`running`) para saber si hay un job activo en vez de fiarse del estado local, y lo permite de nuevo al terminar.
- **Web multi-página**: `/` (descarga + progreso + novelas recientes), `/biblioteca` (grid de solo portadas, tap → ficha), `/novela/{slug}` (ficha individual: info, acciones Traducir/Sync/Re-traducir/Tomos, progreso del job y listado de EPUBs Original/Traducción) y `/ayuda` (guía estática de qué hace cada acción). JS partido en módulos compartidos (`common.js`, `jobs.js`) + uno por página.
- **API REST**: `GET /api/jobs`, `POST /api/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`, `GET /api/novels`, `GET /api/novels/{slug}`, descarga de EPUB y portada, `POST /api/novels/{slug}/sync`, `POST /api/novels/{slug}/retranslate`, `POST /api/novels/{slug}/volume-size`, `POST /api/novels/{slug}/rebuild`, `POST /api/upload` (PDF multipart), `GET /api/config` (incluye `translate_backend`, `ollama_model`, `translate_languages`, `default_translate_target`, `telegram_enabled`, `upload_enabled`, `upload_max_mb`, `source_languages`).
- **Subida de PDFs** (`POST /api/upload`): tarjeta "Subir un PDF" en la portada con archivo, idioma del PDF (default `es`), traducción opcional, idioma destino y tomos. Crea un job `pdf` que reusa `run_pdf_pipeline` con el mismo panel de progreso (status + barras). El archivo va a staging y se limpia al terminar.
- **Novelas PDF en la biblioteca**: badge `PDF` en portadas y ficha; **Sync oculto** (no hay URL); **Re-traducir** funciona por slug (`pdf-retranslate`), regenerando solo el EPUB traducido y conservando el original rico.
- **Auth opcional** con `NOVEL_WEB_TOKEN` (cabecera `X-Auth-Token`); `--host`/`--port`/`--no-browser` configurables.
- Entry points: `novel-cli web` y `novel-cli-web`.

### Notificaciones (Telegram)
- **Bot opcional** ([python-telegram-bot](https://docs.python-telegram-bot.org/)): con `NOVEL_TELEGRAM_BOT_TOKEN` y `NOVEL_TELEGRAM_CHAT_ID` en el `.env`, cada ejecución del pipeline (CLI o web) envía **un resumen** al terminar y **un aviso inmediato** si falla, con la fase (scrape/descarga/traducción/EPUB).
- **Resumen por job en HTML**: cabecera con la **operación** (Descarga/Sync/Traducción/Re-traducción) y la **duración real** del job (desde `job_started`, incluye scrape/traducción), y líneas con capítulos descargados/totales (y vacíos pendientes), tomos del EPUB original, traducción a `<LANG>` (nuevos/total) y tomos del EPUB traducido. Título y detalle del error se escapan para no romper el formato. No se usa polling ni webhook: solo `Bot.send_message` de salida.
- **Aislado de fallos**: la notificación nunca interrumpe el pipeline; sin token/chat el comportamiento no cambia (`NullNotifier`). `NOVEL_TELEGRAM_ENABLED=off` la desactiva explícitamente.

### Logs e historial
- **Log técnico rotativo** (`output/logs/novel-cli.log`): timestamp, nivel, módulo y `job_id`; registra fases, reintentos/backoff, `429`/`Retry-After`, fallback HTTP→Playwright, capítulos vacíos y caché de traducción. `RotatingFileHandler` (5 MiB × 3) e idempotente; se configura solo en los entrypoints (los tests no escriben ficheros).
- **`-V/--verbose`** sube el fichero (y la consola) a `DEBUG`; sin `-V`, fichero `INFO` y consola solo avisos/errores (no ensucia las barras de `rich`).
- **Historial `output/logs/runs.jsonl`**: una línea JSON por ejecución (CLI o job web) con `operation`, `status`, `duration_s`, contadores del manifest, `slug`/`title`/`url` y `error`. Independiente del logging; útil para auditar y para depurar.
- **`job_id` por job** en la web (contextvar + filtro) para correlacionar los logs concurrentes; los tokens/API keys nunca se escriben.

### Caché del TOC
- **Índice cacheado** en `output/<slug>/.toc.json` (`TocCache`): evita re-escanear el listado completo en cada Sync. Un re-sync con la caché fresca hace **0 peticiones** al listado; caducada, solo un **peek de 2 páginas** (primera/última) para detectar capítulos nuevos.
- **TTL** `NOVEL_TOC_TTL_HOURS` (default 6 h; `0` = peeks siempre) y **pacer de listado** `NOVEL_TOC_PACER_MS` (default 1000 ms) para reducir `429`.
- **`--refresh-toc`** fuerza el re-escaneo; el subcomando manual **`novel-cli toc [--slug|--all]`** pre-genera las cachés. Migración **lazy**: las novelas existentes la crean en el siguiente Sync.

### Calidad
- **254 tests unitarios sin red** (fixtures + `respx`) y `ruff` limpio.
- Separación estricta `core/` (dominio puro) vs `cli/` (typer/rich) vs `notifications/` (Telegram) vs `logging_setup`/`run_history` (infraestructura).

---

## Posibles features a futuro (roadmap)

### Altas / más probable
- **CI GitHub Actions**: `uv sync --dev`, `ruff`, `pytest -q` (sin integración) en cada push/PR.
- **Validar el adaptador genérico en 1-2 sitios reales más** (Royal Road, biquge, Scribble Hub) con fixtures propios por sitio.
- **`--translate-title`**: traducir también el título de la novela/metadata (hoy se conserva el original).

### Medias
- **Descarga de imágenes dentro de los capítulos** (hoy el EPUB queda autocontenido sin imágenes internas).
- **Control de rango de capítulos**: `--start <num> --end <num>` para bajar solo un tramo concreto.
- **Flag `--next` explícito** para avanzar de tomo (hoy la re-ejecución con `--resume` ya avanza).
- **Auto-detección de idioma origen** vía la respuesta del endpoint (hoy se envía `source=auto`).
- **Más métricas en el manifest**: fecha por fase, número de EPUB, versión del esquema → migraciones suaves.

### Bajas / experimentales
- **Modo interactivo / TUI** de selección de tomos y sitios (parcialmente cubierto por la web).
- **Soporte de EPUB de terceros** (leer/editar existentes) — hoy solo generamos.
- **Perfil de prioridad/cola de novelas** (descarga programada de varias novelas).
- **Reporte final en Markdown/JSON** del resultado por ejecución.
- **Detección de anti-bot avanzado** (Cloudflare real) y reintento con espera humana — fuera de alcance v1.

---

Ver también: [uso del CLI](uso.md) y [arquitectura](arquitectura.md) (incluye diagramas Mermaid de dependencias, pipeline, red y ciclo de vida del capítulo).