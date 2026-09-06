# 04 — EPUB

## Biblioteca

`ebooklib` + `lxml`. Estándar de facto en Python para EPUB 2/3. No reimplementamos lo que ya resuelve Readest con `buildEpub`; en Python `ebooklib` es el equivalente maduro.

## Conservación del formato original

El requisito es conservar el formato original de los capítulos:

- Los párrafos extraídos se mantienen 1:1 (lista `paragraphs`).
- Cada capítulo → un archivo XHTML con:
  - `<h1>${chapter.title}</h1>` como cabecera canónica.
  - Cada párrafo en un `<p>` (`.join` con `\n` y escape XML).
- Sin reflow ni "plain text": el EPUB conserva la estructura de párrafos tal cual venía del sitio.
- Imágenes **dentro** del capítulo: v1 no las incluye (lección de Readest: el EPUB queda autocontenido). Solo la portada se embelece como imagen.

## Estructura del EPUB

```
content.opf            (metadata: title, author, language, cover, manifest, spine)
toc.ncx                (nav de capítulos)
toc.xhtml              (EPUB3 nav opcional)
OEBPS/cover.xhtml
OEBPS/cover.jpg (o .png)
OEBPS/chapter0001.xhtml
OEBPS/chapter0002.xhtml
...
```

- `identifier`: derivado de `source_url` (estable, para re-imports deterministas — lección de Readest `stableIdentifier`).
- `language`: idioma original (del manifest `language_code`, o `auto` → detectado). Para el EPUB traducido, `language="es"`.
- `title` del EPUB: `Novela` (sin rango) para el EPUB completo; con rango para volúmenes (`Novela 1-50`).
- `spine`: en orden numérico de capítulos.
- `toc.ncx` lista todos los capítulos del volumen.

## Volúmenes

- `volume_size` (flag CLI): `50`, `100`, o `None` (único EPUB).
- Se divide la lista ordenada de capítulos en `Volume(start, end, chapters)`:
  - `50` → `1-50`, `51-100`, `101-150`, ... el último volumen puede ser más corto.
  - `None` → un único EPUB con todos los capítulos (`Novela.epub`).
- Naming de archivo (decisión confirmada): `Novela 1-50.epub`, `Novela 51-100.epub`, y `Novela.epub` para el único.
- **Cada volumen reutiliza la misma portada** de la webnovel (no hay múltiples capturas).

## Portada

- Si `cover_path` local existe → se embelee como imagen de portada (`<meta name="cover" content="cover-image"/>`, primer item del manifest/spine).
- Si no hay portada → portada generada por SVG con título/autor (estilo Readest `generateCoverSvg`).

## Funciones del servicio (`core/services/epub.py`)

```python
def build_epub(
    *,
    title: str,
    author: str | None,
    language: str,
    identifier: str,
    chapters: list[Chapter],
    cover_path: str | None,
    translated: bool = False,        # afecta a metadata y al contenido (parágrafos ya traducidos)
) -> bytes:
    """Construye un EPUB a partir de capítulos (ya originales o ya traducidos)."""

def generate_volumes(
    chapters: list[Chapter],
    volume_size: int | None,
) -> list[Volume]:
    """Divide capítulos ordenados en volúmenes (o uno solo)."""
```

- `build_epub` recibe capítulos ya con `paragraphs` en el idioma correcto (el pipeline traduce antes si hace falta). El servicio de EPUB no sabe de traducción.
- Salida: se escribe en `output/<slug>/<nombre>.epub` y se registra en el manifest.

## EPUB traducido (con `--translate`)

- Se genera **además** del original (decisión confirmada: Original + traducido).
- Misma estructura y portada; `language="es"`; contenido desde `translated/<NNNN>.md`.
- Naming: `Novela 1-50 (ES).epub` / `Novela (ES).epub` para distinguir.