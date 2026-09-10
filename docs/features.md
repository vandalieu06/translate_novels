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
- **Backend intercambiable**: backend local **LibreTranslate** (Docker/podman) vía `NOVEL_TRANSLATE_BACKEND=libre`. Config persistente con un `.env` (cargado al arrancar). Con `LT_API_KEYS`/`NOVEL_TRANSLATE_API_KEY` se omite el rate-limit por defecto de LibreTranslate (200 req/día/IP) que rompía re-traducciones largas con 429.
- **Aceleración CUDA**: `docker-compose.cuda.yaml` usa la imagen `latest-cuda` con GPU NVIDIA (se lanza con `sudo docker compose`), DNS público fijado para evitar el fallo por MagicDNS de Tailscale.
- **Párrafo a párrafo** con chunking (~400 palabras) y **reensamblado 1:1**; el EPUB traducido conserva la estructura del original.
- **Caché en disco** (`translated/<NNNN>.md`): no re-traduce lo ya hecho; retry/pacing ante 429/503. Un `translated/` vacío (heredado de un capítulo sin contenido) no cuenta como traducido: se re-traduce si el raw se arregló y se limpia si sigue vacío.
- **Traducción en paralelo por lotes** (`-tc/--translate-concurrency`): traduce varios capítulos a la vez con pool async (patrón igual a la descarga). Default inteligente por backend (1 google / 4 libre) y **capa de protección**: google fuerza 1 (no quemar el endpoint), libre topa en 16. El pacer compartido mantiene el ritmo global de peticiones.
- **Idioma destino elegible** (`--target <lang>`): lista curada (`config.TRANSLATE_TARGET_LANGUAGES`: es, en, fr, de, it, pt, ru, ja, ko, zh; env `NOVEL_TRANSLATE_TARGET`). `-t/--translate` genera el EPUB original **y** el traducido (`Novela 1-50 (ES).epub`, sufijo según idioma).
- **`--translate-pending`**: traduce solo los capítulos pendientes (ya descargados, sin traducir) sin descargar nuevos ni tocar el TOC — ideal para retomar una traducción cortada por rate-limit.

### CLI
- Comando único `novel-cli <url>` con flags `-o`, `-v`, `-t`, `--resume/--no-resume`, `-f`, `--all`, `-p`, `-c`, `-tc`, `-V`.
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
- **API REST**: `GET /api/jobs`, `POST /api/jobs`, `GET /api/jobs/{id}`, `POST /api/jobs/{id}/cancel`, `GET /api/novels`, `GET /api/novels/{slug}`, descarga de EPUB y portada, `POST /api/novels/{slug}/sync`, `POST /api/novels/{slug}/retranslate`, `POST /api/novels/{slug}/volume-size`, `POST /api/novels/{slug}/rebuild`, `GET /api/config` (incluye `translate_backend`, `translate_languages` y `default_translate_target`).
- **Auth opcional** con `NOVEL_WEB_TOKEN` (cabecera `X-Auth-Token`); `--host`/`--port`/`--no-browser` configurables.
- Entry points: `novel-cli web` y `novel-cli-web`.

### Calidad
- **182 tests unitarios sin red** (fixtures + `respx`) y `ruff` limpio.
- Separación estricta `core/` (dominio puro) vs `cli/` (typer/rich).

---

## Posibles features a futuro (roadmap)

### Altas / más probable
- **CI GitHub Actions**: `uv sync --dev`, `ruff`, `pytest -q` (sin integración) en cada push/PR.
- **Validar el adaptador genérico en 1-2 sitios reales más** (Royal Road, biquge, Scribble Hub) con fixtures propios por sitio.
- **`--translate-title`**: traducir también el título de la novela/metadata (hoy se conserva el original).
- **`OllamaTranslator`** real como backend opcional (inyectable por env/flag), manteniendo Google como default.

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