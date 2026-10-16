---
code: "08"
title: "Rediseno web: ayuda, ayuda inline, microcopy y accesibilidad"
project: "novel_cli"
status: completed
version: "0.3.0"
date: 2026-10-16
tags: [spec, sdd, web, ui, a11y]
affected_files:
  - src/novel_cli/web/templates/help.html
  - src/novel_cli/web/static/js/common.js
  - src/novel_cli/web/static/js/jobs.js
  - src/novel_cli/web/static/css/app.css
  - docs/features.md
  - docs/arquitectura.md
  - README.md
  - tests/test_web.py
---

# 08 — Rediseno web: ayuda, ayuda inline, microcopy y accesibilidad

## Purpose

Cerrar el rediseno: reducir la pagina de ayuda a una guia compacta y agruparla,
llevar la explicacion al contexto (ayuda inline junto a cada control), hacer una
pasada de microcopy (sin relleno de marketing) y asegurar accesibilidad basica
(teclado, foco, `aria-live`, `alt`). Actualizar `docs/` y `README.md`.

## Context

`/ayuda` son 15 tarjetas con emoji y parrafos (muro de documentacion que se lee
mal en movil); no hay ayuda contextual en los controles; el testigo de foco y el
`aria-live` son incompletos; los `alt` de portada estan vacios. `docs/features.md`
y `docs/arquitectura.md` describen "diseno MOSH", que ya no existe. Es la ultima
spec del conjunto y depende de 05, 06 y 07.

## Proposed change (antes → despues)

- **Antes**: 15 tarjetas con emoji; ayuda solo en `/ayuda`; sin focus trap; docs
  hablando de MOSH.
- **Despues**:
  1. **`/ayuda` compacta**: 3-4 bloques con encabezados (Descarga · Traduccion ·
     EPUB · Estado), sin emojis, sentence case, contenido completo pero directo.
  2. **Ayuda inline**: icono "?" (Tooltip/Popover) junto a los controles no
     obvios, con `aria-describedby`; el texto coincide con la guia.
  3. **Microcopy**: revisar titulos, botones y estados; quitar frases de
     marketing; verbos concretos; error concreto (no "Oops").
  4. **Accesibilidad**:
     - **Focus trap** en Dialog/Sheet + devolver el foco al cerrar.
     - `aria-live="polite"` en `#toast` y en la linea de estado del job bar.
     - `alt` significativo en portadas (`alt = titulo`), decorativos con
       `aria-hidden`.
     - Navegacion completa por teclado; targets >= 44px en movil.
     - `prefers-reduced-motion` respetado (ya existe; se conserva).
  5. **Docs**: actualizar `docs/features.md` (describir el design system propio),
     `docs/arquitectura.md` (`static/` con CSS partido + `theme.js`) y
     `README.md`.

## Technical decision

- Focus trap en vanilla JS (sin dependencias): engancha `Tab`/`Shift+Tab` dentro
  del contenedor con `role="dialog"` y restaura el foco previo al cerrar.
- Ayuda inline como `<button aria-describedby>` + Popover/Tooltip de 05; el texto
  vive en el DOM (no en `title` nativo) para que sea accesible.
- **Sin cambios** en `routes.py` / `jobs.py` / `ws.py`.

## Affected files

- `src/novel_cli/web/templates/help.html` — ayuda compacta y agrupada.
- `src/novel_cli/web/static/js/common.js` — focus trap, toast accesible, dialogos.
- `src/novel_cli/web/static/js/jobs.js` — `aria-live` en la linea de estado.
- `src/novel_cli/web/static/css/app.css` — estilos de la guia y foco visible.
- `docs/features.md`, `docs/arquitectura.md`, `README.md` — documentacion viva.
- `tests/test_web.py` — asserts.

## Tests

- `tests/test_web.py::test_ayuda_served`: actualizar el assert al nuevo titulo o
  encabezado de la guia (ya no "Que hace cada accion" si cambia el texto).
- Sin red.

## Acceptance criteria

- `/ayuda` es una guia compacta y agrupada, sin emojis.
- Hay ayuda inline en los controles no obvios de home y ficha.
- Recorrido completo por teclado (incluido el cierre de Dialog/Sheet) con foco
  visible; toasts y estado anunciados por `aria-live`.
- `docs/features.md`, `docs/arquitectura.md` y `README.md` ya no mencionan MOSH y
  describen el sistema actual.
- `uv run pytest -q` y `uv run ruff check .` pasan.
