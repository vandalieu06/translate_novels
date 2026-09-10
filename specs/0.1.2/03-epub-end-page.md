# 03 — EPUB: página final (FIN + ficha) en cada tomo

- Estado: implementado · Versión spec: 0.1.2 · Fecha: 2026-09-10 · Relacionado: 0.1.0/04-epub.md, 0.1.1/03-epub.md

## Propósito

Cerrar cada tomo con una **página final** de portada/cierre: un "FIN" centrado
(según el idioma del EPUB) acompañado de una ficha básica del tomo (título,
rango de capítulos, autor, idioma si es traducción). Evita que el EPUB termine
abruptamente tras el último párrafo.

## Contexto / Problema

`build_epub()` (`core/services/epub.py`) hoy genera `spine = [cover, nav,
*capítulos]`: el libro acaba en la última línea del último capítulo, sin ningún
cierre. No hay forma de marcar el final de un tomo.

## Cambio propuesto (antes → después)

**Antes:** `spine = [cover, nav, *capítulos]`.

**Después:**
- Nuevo parámetro `include_end_page: bool = True` en `build_epub()`.
- Con él activo, el spine termina con una página `end.xhtml`:
  - `FIN` si `language` empieza por `es`, si no `THE END`.
  - Ficha básica: título del tomo, rango `start–end` (derivado de
    `chapters[0].num` / `chapters[-1].num`), autor si existe, y "Traducido a
    <idioma>" si `translated`.
  - Todo el texto escapado con `html.escape` (igual que `_add_chapter`).
- La página queda **fuera del TOC** (`book.toc` no cambia): aparece solo en el
  spine para pasar página.
- Aplica a todos los EPUBs generados por `build_epub` (original, traducido y
  `rebuild_volumes`), porque todos pasan por el mismo builder: cada tomo de
  `generate_volumes` cierra con su propia página final.

## Decisión técnica

- `_add_end_page(book, *, title, author, language, translated, start, end)`
  construye un `epub.EpubHtml(title="Fin", file_name="end.xhtml", lang=language)`
  con XHTML centrado (`style="text-align:center"`) y `book.add_item(item)`.
- El rango se deriva de los capítulos ya recibidos, sin añadir metadatos ni
  cambiar la firma del pipeline: `pipeline.py` ya pasa `volume.chapters` y el
  título del tomo (`"Novela 1-50"`).
- `book.toc = tuple(epub_chapters)` se mantiene intacto → oculta del índice.
- `include_end_page` permite desactivarlo (tests/futuro flag CLI) sin tocar el
  resto de llamadas.

## Archivos afectados

`core/services/epub.py` (`build_epub`, `_add_end_page`), `tests/test_epub.py`,
`docs/arquitectura.md` (§5.5). Sin cambios en `pipeline.py`, manifest, web ni CLI.

## Tests

- `end.xhtml` presente en el zip con `FIN` (language `es`) y el rango/título.
- `language` `en` → `THE END`.
- `include_end_page=False` → no genera `end.xhtml`.
- Escape de caracteres `&<>` en título/autor de la página final.
- `test_build_epub_readable_by_ebooklib`: recuento de documentos pasa a 6
  (cover+nav+3 capítulos+fin).

## Criterios de aceptación (Done cuando)

- Cada EPUB generado cierra con la página FIN + ficha, fuera del TOC.
- Original, traducido y `rebuild_volumes` la incluyen.
- `uv run pytest -q` y `uv run ruff check .` pasan.