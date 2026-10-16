---
code: "10"
title: "Paginar el TOC de NovelFire/NovelPhoenix por rangos (?page=N)"
project: "novel_cli"
status: completed
version: "0.3.0"
date: 2026-10-17
tags: [spec, sdd, scraper]
affected_files:
  - src/novel_cli/core/scraper/sites/novelfire.py
  - tests/test_novelfire.py
  - tests/fixtures/novelfire_toc.html
---

# 10 — Paginar el TOC de NovelFire/NovelPhoenix por rangos (?page=N)

## Purpose

Que el TOC de `novelphoenix.com` (y sitios con el mismo paginador) recorra
**todas** las páginas del listado, no solo la primera, para detectar y descargar
los capítulos nuevos y generar los tomos completos.

## Context

`novelphoenix.com` está mapeado al `NovelfireAdapter`. Su listado pagina por
**rangos de 100** con `?page=N`:

```html
<div class="chapter-range-pager">
  <a aria-label="Next chapter range" href=".../chapters?page=2">›</a>
  <a aria-label="Last chapter range" href=".../chapters?page=3">»</a>
  <select aria-label="Chapter range">… 1-100 | 101-200 | 201-257 …</select>
</div>
```

`NovelfireAdapter.next_page` solo busca
`#chpagedlist .page-item > .page-link[rel='next']` (marcado de `novelfire.net`),
que **no existe** en esa página → devuelve `None`.

Consecuencias en la novela real `my-step-daughters-are-the-villainesses` (257
capítulos, `volume_size=100`):

- El crawl lee **solo la página 1** → TOC de 100 capítulos; `.toc.json` guarda
  `listing_pages` con la misma URL dos veces (una sola página efectiva).
- `build_epub_chapters` arma los tomos desde `site.chapters` (el TOC), así que el
  EPUB se queda en **1-100** aunque `raw/` tenga 200 capítulos.
- El peek de la caché (`toc_changed`) tampoco ve páginas nuevas (su última página
  no tiene `next_page`), así que reutiliza la caché viejos y **nunca descubre los
  capítulos 101-257**.

## Proposed change (antes → despues)

- **Antes**: `next_page` solo reconoce `rel='next'` dentro de
  `#chpagedlist .page-item`.
- **Despues**: `next_page` intenta, en orden:
  1. el selector actual `rel='next'` (compatibilidad con `novelfire.net`);
  2. el paginador de rangos `.chapter-range-pager a[aria-label='Next chapter range']`,
     devolviendo `None` si el enlace tiene `aria-disabled="true"` (última página).
- No cambia `parse_toc` ni el resto del adaptador.

## Technical decision

- Se añade el selector nuevo como **fallback** y se respeta `aria-disabled` (la
  última página marca `Next`/`Last` como deshabilitados con `href` a sí misma).
- Se evita un fallback "genérico a `?page=N`" para no alterar otros sitios con
  `rel='next'` ya funcional; aquí el pager tiene un contenedor y `aria-label`
  estables.
- Tras el arreglo, el peek de la caché ve la página siguiente y fuerza el
  re-crawl (recuperación automática sin `--refresh-toc`).

## Affected files

- `src/novel_cli/core/scraper/sites/novelfire.py` — `SEL_NEXT` + `next_page`.
- `tests/fixtures/novelfire_toc.html` — añadir/ajustar el paginador de rangos
  (o un fixture nuevo) para cubrir el caso.
- `tests/test_novelfire.py` — pruebas.

## Tests

- `next_page` con el pager `.chapter-range-pager` (aria-label "Next chapter
  range" habilitado) → `...?page=2`.
- `next_page` con la última página (`aria-disabled="true"`) → `None`.
- Se mantiene el test existente de `rel='next'` (novelfire.net).

## Acceptance criteria

- `crawl_toc` sobre un listado con el pager de rangos devuelve los capítulos de
  **las 3 páginas** (1-257), no solo 1-100.
- Un **Sync** de la novela 101-257 existente descubre los capítulos nuevos,
  descarga los pendientes y **regenera los tomos 1-100, 101-200 y 201-257**
  (original y traducido).
- `uv run pytest -q` y `uv run ruff check .` pasan (sin red; fixtures).
