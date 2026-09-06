# 02 — Modelos de dominio

Ubicación: `core/models/novel.py` y `core/models/state.py`. Todos son `@dataclass` (convención del proyecto viejo) salvo `Manifest` que usa `pydantic` para validación JSON.

## Novel / metadata de sitio

```python
@dataclass
class NovelMetadata:
    """Metadatos extraídos de la portada/TOC del sitio."""
    title: str
    author: str | None
    cover_url: str | None
    description: str | None = None
    language_code: str = "auto"   # 'en', 'zh', etc.; 'auto' => detectar al traducir
    source_url: str = ""          # URL canónica de la novela
```

## Chapter

```python
@dataclass
class Chapter:
    num: int               # número de capítulo (1-based)
    title: str
    url: str               # URL del capítulo
    paragraphs: list[str]  # contenido crudo (párrafos), idioma original
```

- `num` se usa para ordenar y para el naming de volúmenes (`1-50`, `51-100`).
- `paragraphs` conserva el **formato original** (la separación en párrafos se mantiene 1:1 al generar el XHTML).

## SiteMetadata (TOC extraído)

```python
@dataclass
class SiteMetadata:
    metadata: NovelMetadata
    chapters: list[Chapter]
```

## Volume (agrupación)

```python
@dataclass
class Volume:
    start: int       # num del primer capítulo
    end: int         # num del último capítulo
    chapters: list[Chapter]
```

- El agrupado lo calcula `core/utils/names.py` a partir del tamaño de volumen (50 o 100) o `None` para un único EPUB.
- Cada volumen reutiliza **la misma portada** de la webnovel (decisión confirmada).

## Manifest (estado en disco, `state.py`)

```python
class Manifest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    schema_version: int = 1
    slug: str                                  # nombre de carpeta estable
    title: str
    author: str | None = None
    source_url: str = ""
    language_code: str = "auto"
    cover_path: str | None = None              # ruta relativa a la portada local
    chapters_total: int = 0
    chapters_downloaded: int = 0               # conteo para reanudar
    chapters_translated: int = 0
    volume_size: int | None = None             # 50 | 100 | None (único EPUB)
    translated: bool = False                   # se pidió/realizó traducción
    epub_original: list[str] = []              # rutas relativas de EPUB originales
    epub_translated: list[str] = []            # rutas relativas de EPUB traducidos
    created_at: str | None = None              # ISO8601
    updated_at: str | None = None
```

- Se guarda en `output/<slug>/.manifest.json`.
- Al reanudar, `core` lee el manifest: si `chapters_downloaded == chapters_total`, salta la descarga; si `translated` y `chapters_translated == chapters_total`, salta la traducción.
- Capítulos individuales en disco: `raw/<NNNN>.md` (o `.xhtml`) para el idioma original y `translated/<NNNN>.md` para el traducido. La existencia del archivo en disco es la fuente de verdad para "ya descargado/traducido"; el manifest es un índice/caché.

## utils/names.py

- `slugify(title)` → `inner-voice-all-heroines-hear-my-inner-voice` (igual que el proyecto viejo).
- `volume_name(slug, start, end, suffix)` → `inner-voice 1-50.epub`.
- `chapter_filename(num)` → `0042.md` (zero-padded para orden lexicográfico estable).