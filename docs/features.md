# Features de novel-cli

## Features actuales (implementadas)

### Descarga y scraping
- **HTTP primero, Playwright como fallback**: `httpx` async con headers de navegador; si falla, reenvío por Playwright (navegador persistente). `-p/--playwright` fuerza el navegador.
- **Adaptador NovelFire** (`novelfire.net`) con selectores específicos y paginación de listado.
- **Adaptador genérico**: heurística de TOC estilo Readest (enlaces numerados, dedupe, orden, `og:title`/`og:image`/`meta author`) para cualquier sitio.
- **Descarga por tomos**: por defecto baja solo el primer tomo (50 capítulos); re-ejecutar el mismo comando avanza al siguiente tomo. `--all` descarga todo de golpe.
- **Concurrencia configurable** (`-c`, default 4) con pacing (~300 ms) y cool-down de pool ante 429/`Retry-After` (lecciones de Readest).

### Estado y reanudación
- **Sin SQLite**: `.manifest.json` por novela + capítulos en `raw/` y `translated/`.
- **`--resume`** (default): salta fases completadas y no reescribe EPUB existentes (idempotente).
- **`--force`**: re-descarga y re-traduce todo desde cero.
- La existencia de archivo en disco es la fuente de verdad de "ya descargado/traducido".

### EPUB
- **ebooklib + lxml**: `content.opf`, `toc.ncx`, `nav.xhtml`, un XHTML por capítulo con `<h1>` + un `<p>` por párrafo (estructura original 1:1).
- **Volúmenes**: `-v 50|100` → `Novela 1-50.epub`, `Novela 51-100.epub`, ... con la **misma portada** (imagen local o SVG generado).
- **Identificador estable** derivado de la URL (re-imports deterministas).

### Traducción
- **Endpoint gratuito de Google Translate** (`translate_a/single` con `client=gtx`), sin clave ni token.
- **Párrafo a párrafo** con chunking (~400 palabras) y **reensamblado 1:1**; el EPUB traducido conserva la estructura del original.
- **Caché en disco** (`translated/<NNNN>.md`): no re-traduce lo ya hecho; retry/pacing ante 429/503.
- `-t/--translate` genera el EPUB original **y** el traducido (`Novela 1-50 (ES).epub`).

### CLI
- Comando único `novel-cli <url>` con flags `-o`, `-v`, `-t`, `--resume/--no-resume`, `-f`, `--all`, `-p`, `-c`, `-V`.
- **Códigos de salida** `0-4` (éxito, validación, red/descarga, traducción, EPUB/manifest).
- **Barras de progreso** con `rich` (descarga, traducción, EPUB) y logs detallados con `-V`.
- Ruta por defecto: env `NOVEL_OUTPUT_DIR` o `./output`.

### Calidad
- **102 tests unitarios sin red** (fixtures + `respx`) y `ruff` limpio.
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
- **Multi-idioma destino** (`--target <lang>`) en vez de fijar `es`; auto-detección de idioma origen vía la respuesta del endpoint.
- **Más métricas en el manifest**: fecha por fase, número de EPUB, versión del esquema → migraciones suaves.

### Bajas / experimentales
- **Modo interactivo / TUI** de selección de tomos y sitios.
- **Soporte de EPUB de terceros** (leer/editar existentes) — hoy solo generamos.
- **Perfil de prioridad/cola de novelas** (descarga programada de varias novelas).
- **Reporte final en Markdown/JSON** del resultado por ejecución.
- **Detección de anti-bot avanzado** (Cloudflare real) y reintento con espera humana — fuera de alcance v1.

---

Ver también: [uso del CLI](uso.md) y [arquitectura](arquitectura.md).