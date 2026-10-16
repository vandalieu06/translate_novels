---
code: "05"
title: "Rediseno web: design system propio (tokens + primitivas vanilla)"
project: "novel_cli"
status: completed
version: "0.3.0"
date: 2026-10-16
tags: [spec, sdd, web, ui]
affected_files:
  - DESIGN.md
  - src/novel_cli/web/static/css/app.css
  - src/novel_cli/web/static/css/tokens.css
  - src/novel_cli/web/static/css/components.css
  - src/novel_cli/web/static/js/theme.js
  - src/novel_cli/web/templates/index.html
  - src/novel_cli/web/templates/library.html
  - src/novel_cli/web/templates/novel.html
  - src/novel_cli/web/templates/help.html
  - tests/test_web.py
---

# 05 — Rediseno web: design system propio (tokens + primitivas vanilla)

## Purpose

Sustituir el diseno "MOSH" por un design system propio, compacto y orientado a
herramienta (estilo shadcn, escrito a mano en CSS vanilla): tokens claro/oscuro y
un catalogo de primitivas (boton, input, card, badge, alert, dialog/sheet,
toast, progress, popover...) que las specs 06-08 reutilizan. Es la base del
rediseno; va primero y en solitario.

## Context

La web aplica el `DESIGN.md` de MOSH (spec de una landing de marketing japonesa)
a una herramienta personal. El resultado son gradientes (6), sombras en reposo,
**emojis como sistema de iconos**, "eyebrows"/kickers y cinco familias de color
compitiendo (coral decorativo + CTA negro + link azul + semanticos). Todo el CSS
vive en un unico `app.css` (~1500 lineas), sin catalogo de componentes ni
dark mode. No hay motor de plantillas (FastAPI sin Jinja) ni build step, y se
quiere mantener esa virtud.

Guias: `redesign-existing-projects` (auditar y mejorar sin cambiar stack) manda;
de `design-taste-frontend` se toman solo sus *house rules* anti-ornamento (sin
eyebrows, sin gradientes, sin tarjetas con icono arriba, sin labels uppercase
diminutos, sin glass, sin numeracion 01/02, sentence case), descartando su parte
de direccion artistica por no aplicar a pantallas de app.

## Proposed change (antes → despues)

- **Antes**: un `app.css` unico con tokens MOSH (`--brand` coral), IBM Plex Sans
  JP, gradientes/sombras, emojis y sin tema.
- **Despues**:
  1. **`DESIGN.md`** nuevo = design system de *esta* herramienta (tokens, roles,
     reglas, inventario de primitivas). Ya no menciona MOSH.
  2. **CSS partido**: `tokens.css` (variables + reset/base), `components.css`
     (primitivas) y `app.css` (shell + paginas) que pasa a orquestador con
     `@import` de los otros dos (mantiene su ruta publica para no tocar el
     `<link>` de las plantillas).
  3. **Tokens claro/oscuro** con `<html data-theme="auto|light|dark">`; `auto`
     resuelve por `prefers-color-scheme`.
  4. **Fuente `system-ui`** (sin webfont) + `font-variant-numeric: tabular-nums`
     en contadores.
  5. **Un unico accent** (coral suavizado) para seleccion/progreso/foco;
     `--primary` casi negro para las acciones.
  6. **Primitivas**: Button (primary/outline/ghost/destructive, icon-only,
     loading), Input, Select, Checkbox, Switch, Segmented, Badge (tinte suave),
     Alert, Card, Dialog, Sheet (bottom-sheet movil), Toast, Progress,
     EmptyState, Skeleton, Popover/Menu, Tooltip.
  7. **Iconos SVG inline** (helper `icon(name)` en `theme.js` o `common.js`) —
     se eliminan los emojis del shell.
  8. **`theme.js`**: aplica el tema guardado (`localStorage["novel_web_theme"]`),
     expone `setTheme()` para el menu de Ajustes (spec 06) y un bootstrap inline
     en `<head>` evita el FOUC.

## Technical decision

- **Sin dependencias ni build**: tokens como CSS custom properties; el tema es un
  atributo + media query.
- Se quitan de las 4 plantillas los `<link>` a Google Fonts (IBM Plex); cada
  `<head>` incorpora el bootstrap de tema (script inline pequeno) antes del CSS.
- **Paleta** (claro / oscuro):

  | Rol | Claro | Oscuro |
  |---|---|---|
  | `--bg` | `#ffffff` | `#09090b` |
  | `--fg` | `#18181b` | `#fafafa` |
  | `--card` | `#ffffff` | `#121215` |
  | `--muted` | `#f4f4f5` | `#1f1f23` |
  | `--muted-fg` | `#71717a` | `#a1a1aa` |
  | `--border` / `--input` | `#e4e4e7` | `#27272a` |
  | `--primary` / `--primary-fg` | `#18181b` / `#fafafa` | `#fafafa` / `#18181b` |
  | `--accent` | `#e0575f` | `#f2777e` |
  | `--ring` | `--accent` | `--accent` |
  | `--destructive` | `#dc2626` | `#ef4444` |
  | `--success` | `#16a34a` | `#4ade80` |
  | `--warning` | `#d97706` | `#fbbf24` |

- **Escalas**: radios `6 / 8 / 12`; espacio `4 / 8 / 12 / 16 / 24 / 32 / 48`;
  tipos `12 / 13 / 14 / 16 / 20 / 28`; contenedor `1120px`; header sticky `56px`.
- **Reglas**: sin gradientes; sin sombras en reposo (solo dialog/sheet/popover);
  sin emojis; sin uppercase con tracking; sin glass; sentence case; titulares de
  <=2 lineas.

## Affected files

- `DESIGN.md` — reescrito como design system de la herramienta.
- `src/novel_cli/web/static/css/tokens.css` — **nuevo** (variables + reset + tema).
- `src/novel_cli/web/static/css/components.css` — **nuevo** (primitivas).
- `src/novel_cli/web/static/css/app.css` — pasa a orquestador (`@import`) + shell/paginas.
- `src/novel_cli/web/static/js/theme.js` — **nuevo** (tema + iconos SVG).
- 4 plantillas — solo `<head>`: quitar webfont, anadir bootstrap de tema.
- `tests/test_web.py` — actualizar asserts.

## Tests

- Actualizar `tests/test_web.py::test_static_css_served`: afirmar un token del
  nuevo sistema (p. ej. `"--accent"` o `"--bg"`) en lugar de `"--brand"`.
- Nuevo: `GET /static/css/tokens.css` y `/static/css/components.css` responden
  200. Sin red.

## Acceptance criteria

- `/`, `/biblioteca`, `/novela/{slug}` y `/ayuda` cargan con el nuevo sistema
  (sin IBM Plex, sin gradientes ni emojis en el shell).
- El tema conmuta (auto/claro/oscuro) y **persiste al recargar**; respeta
  `prefers-reduced-motion`.
- `DESIGN.md` describe tokens + reglas + primitivas y no menciona MOSH.
- `uv run pytest -q` y `uv run ruff check .` pasan.
