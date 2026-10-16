---
code: "07"
title: "Rediseno web: biblioteca con filtros y ficha de novela reestructurada"
project: "novel_cli"
status: completed
version: "0.3.0"
date: 2026-10-16
tags: [spec, sdd, web, ui]
affected_files:
  - src/novel_cli/web/templates/library.html
  - src/novel_cli/web/templates/novel.html
  - src/novel_cli/web/static/js/library.js
  - src/novel_cli/web/static/js/novel.js
  - src/novel_cli/web/static/css/app.css
  - tests/test_web.py
---

# 07 — Rediseno web: biblioteca con filtros y ficha de novela reestructurada

## Purpose

Convertir la biblioteca en una vista navegable (buscar / filtrar / ordenar) y
reestructurar la ficha de novela: accion primaria clara, acciones agrupadas por
proposito, lista de EPUBs ordenada y dialogos como *sheet* en movil. Se conserva
la idea del grid de portadas, que funciona bien.

## Context

Hoy `/biblioteca` es un grid de portadas sin buscador, filtros ni orden; con
muchas novelas se vuelve incomoda. La ficha `/novela/{slug}` apila acciones
planas (Sync, Traducir/Re-traducir, Tomos, Regenerar, Fuente) sin jerarquia, y
usa modales simples con markup de progreso **duplicado** respecto a la home
(que la spec 06 sustituye por un job bar global). Depende de las specs 05
(primitivas) y 06 (shell + job bar).

## Proposed change (antes → despues)

- **Antes**: grid sin filtros; ficha con acciones planas y panel propio.
- **Despues**:
  1. **Biblioteca `/biblioteca`**:
     - **Buscador** por titulo/autor.
     - **Filtros** por estado: todas / traducida / con vacios / PDF.
     - **Orden**: recientes (`updated_at`) / titulo.
     - Contador de resultados y **estado vacio** con CTA ("pega una URL para
       empezar").
     - **Densidad** grid/list.
     - Filtros, orden y densidad se **persisten** (`localStorage`).
     - Portadas: se conservan los badges (PDF, idioma, % y aviso de vacios) con
       el nuevo `Badge`; `alt` = titulo de la novela.
  2. **Ficha `/novela/{slug}`**:
     - Cabecera: portada + titulo + autor + estado (badges) + progreso.
     - **Accion primaria**: *Actualizar* (web) o *Traducir* (si no traducida).
     - Acciones agrupadas por proposito: *Actualizar* (Sync) · *Traduccion*
       (Traducir / Re-traducir) · *EPUB* (Tomos, Regenerar). Enlace *Fuente*
       solo si hay `source_url`.
     - Lista de EPUBs agrupada Original / Traduccion, con boton Descargar.
     - Dialogos de idioma y de tomos como **Sheet** en movil y **Dialog** en
       desktop (foco atrapado, ver spec 08).
     - Confirmaciones en acciones destructivas/pesadas.
  3. Se **elimina** el markup de progreso propio de la ficha: usa el job bar
     global (06).

## Technical decision

- **Sin cambios de backend**: filtros, orden y busqueda son 100% cliente sobre
  `GET /api/novels` (el payload actual basta: `title`, `author`, `translated`,
  `translated_language`, `source_pdf`, `chapters_empty`, `updated_at`).
- **No se anade** tamano/fecha de EPUB en esta spec (requeriria tocar `routes.py`,
  fuera del guardarrai del rediseno).
- `library.js` / `novel.js` se adaptan al nuevo DOM y consumen las primitivas de
  05 y los helpers de `common.js` (06): `coverCard`, `languageLabel`,
  `confirmDialog`, `openSheet`.
- Se conservan ids estables que los tests afirman (`cover-grid`, `novel-cover`,
  `epub-groups`) o se actualizan a equivalentes estables.

## Affected files

- `src/novel_cli/web/templates/library.html` — controles de filtro/orden + grid.
- `src/novel_cli/web/templates/novel.html` — ficha reestructurada + sheets.
- `src/novel_cli/web/static/js/library.js` — busqueda/filtros/orden/densidad.
- `src/novel_cli/web/static/js/novel.js` — ficha + sheets + confirmaciones.
- `src/novel_cli/web/static/css/app.css` — estilos de biblioteca y ficha.
- `tests/test_web.py` — asserts de markup.

## Tests

- `tests/test_web.py`: `/biblioteca` y `/novela/novela` siguen 200; afirmar ids
  estables (`#cover-grid` o el header de la pagina; `#novel-cover` /
  `#epub-groups`). Sin red.

## Acceptance criteria

- La biblioteca busca, filtra y ordena en cliente; recuerda filtros/orden/densidad.
- La ficha muestra una accion primaria clara y las acciones agrupadas; los
  dialogos son Sheet en movil.
- No hay markup de progreso duplicado en la ficha.
- Sin cambios en `routes.py` / `jobs.py` / `ws.py`.
- `uv run pytest -q` y `uv run ruff check .` pasan.
