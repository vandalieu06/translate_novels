# 03 — Scraper

## Diseño de fetch: httpx primero, Playwright como fallback

Lección de Readest: los sitios de novelas (NovelFire, biquge, Royal Road) son **server-rendered**; el HTTP plano con headers de navegador basta y es mucho más rápido/ligero que un navegador. Playwright solo se usa cuando el HTTP falla (JS-challenge, contenido renderizado por JS).

### Interfaz `Fetcher` (`core/scraper/base.py`)

```python
class Fetcher(Protocol):
    def fetch_html(self, url: str, *, headers: dict | None = None) -> str: ...
```

Dos implementaciones:

1. **`HttpFetcher`** (`httpx.Client`, async): 
   - Headers tipo Chrome (UA, accept, accept-language) — copia conceptual de `pageNavigateHeaders()` de Readest.
   - `timeout` configurable (default 15s).
   - `follow_redirects=True`.
2. **`PlaywrightFetcher`** (fallback):
   - Un **único** navegador persistente para toda la sesión (nada de `launch()` por llamada como el proyecto viejo).
   - `page.goto(url, wait_until="networkidle")` + `page.content()`.
   - Se lanza solo si `HttpFetcher` falla (o el adaptador lo marca como `requires_js=True`).

### Selección de fetcher

```python
def get_fetcher(http: HttpFetcher, pw: PlaywrightFetcher) -> Fetcher:
    # resolver adaptador de sitio → si marca requires_js, devolver Playwright directo
    # si no: HttpFetcher, y en fallback pasar a Playwright
```

Regla por defecto: intentar HTTP; en `HTTPError`/`429`/`403` retry con backoff; si persiste y hay Playwright disponible, reenviar por Playwright.

## Retry + pacing (lección de Readest `novelImport.ts`)

- **Pacer**: mínimo `300ms` entre inicios de requests (constante `CHAPTER_REQUEST_MIN_INTERVAL_MS`). Compartido por el pool de descarga → ~3.3 req/s agregadas.
- **Retry con backoff**:
  - Transient (502/504/52x o timeout): 2 retries con backoff lineal (1s, 2s).
  - Rate-limit (429/503): 3 retries, backoff base 2s, **honrando `Retry-After`** si viene, con tope de 30s.
- **Cool-down de pool**: si un request recibe 429, los demás workers esperan el cool-down antes de seguir (evita el "thundering herd"). El gate es compartido y acotado (máx. 30s).
- `Retry-After` se parsea (segundos o fecha HTTP) igual que `parseRetryAfterMs` de Readest.

Estos ajustes viven en `core/scraper/fetcher.py` (módulo de red) y se reutilizan en `download.py`.

## Adaptadores de sitio (`core/scraper/sites/`)

### `SiteAdapter` (Protocol)

```python
class SiteAdapter(Protocol):
    name: str
    def tocs(self, novel_url: str) -> list[str]: ...          # URLs de páginas de listado (0..n)
    def parse_toc(self, html: str, base_url: str) -> SiteMetadata: ...  # título, portada, capítulos
    def parse_chapter(self, html: str, chapter_url: str) -> list[str]: ...  # párrafos
```

- `registry.py`: mapea dominio → adaptador (ej. `novelfire.net → NovelfireAdapter`). Si no hay match → `GenericAdapter` (heurística).

### NovelfireAdapter (modernización del proyecto viejo)

Reutiliza los selectores existentes (`novelfire.py`) pero:

- En lugar de Playwright por llamada, usa el `Fetcher` (HTTP primero).
- `get_portada` (título, portada, URL de listado) → `parse_toc`.
- `get_chapters_pages` + `get_chapters_links` → se unifican en `tocs()` + `parse_toc`.
- `get_chapter` (título + párrafos) → `parse_chapter`.

Selectores clave (heredados):

```python
title:        '.novel-info .main-head .novel-title'
img_cover:    '.header-body .fixed-img .cover img'
chapters:     '.novel-body.container #chpagedlist .chapter-list > li > a'
chapter_title: '.chapter-title'
paragraphs:   '#chapter-container > #content > p'
```

### GenericAdapter (heurística estilo Readest `chapterList.ts`)

Cuando el dominio no tiene adaptador propio:

- Detecta enlaces de capítulo por: texto numerado (`Chapter N`, `第N章`, `Capítulo N`) o patrón de href compartido (digit runs colapsados).
- Elige el contenedor más profundo que agrupa la mayoría de candidatos.
- Metadatos: `og:title`, `meta[name=author]`, `<title>` limpio; portada `og:image`.
- Dedupe de URLs y orden por número.

## Cobertura de la portada

- Descargar la imagen de portada (`cover_url`) con el `Fetcher` (bytes), guardar en `output/<slug>/cover.<ext>`.
- El manifest apunta a `cover_path`.
- Todos los volúmenes usan la **misma** portada (decisión confirmada).