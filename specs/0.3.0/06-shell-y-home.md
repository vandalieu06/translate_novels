---
code: "06"
title: "Rediseno web: shell, Ajustes, job bar global y home de descarga"
project: "novel_cli"
status: completed
version: "0.3.0"
date: 2026-10-16
tags: [spec, sdd, web, ui]
affected_files:
  - src/novel_cli/web/templates/index.html
  - src/novel_cli/web/static/js/common.js
  - src/novel_cli/web/static/js/jobs.js
  - src/novel_cli/web/static/js/app.js
  - src/novel_cli/web/static/css/app.css
  - tests/test_web.py
---

# 06 — Rediseno web: shell, Ajustes, job bar global y home de descarga

## Purpose

Rehacer el marco comun de la app (shell) y la home: un header compacto con
ajustes (token y tema), un **job bar global** visible desde cualquier pagina, y
una home de tarea directa (sin hero de marketing) con selector web/PDF y
opciones avanzadas plegadas.

## Context

Hoy la home arranca con un hero de marketing (eyebrow + `h1` + lead + 3 stats),
seguido de **dos formularios completos apilados** (URL y PDF), un panel de
progreso **duplicado literalmente** en `index.html` y `novel.html`, y el token de
acceso se pide con `window.prompt()` (`common.js`). El panel de progreso solo
existe en las paginas que lo incluyen, asi que al navegar se pierde de vista el
job. Los iconos son emojis. Depende de la spec 05 (tokens + primitivas).

## Proposed change (antes → despues)

- **Antes**: hero + 2 formularios + panel duplicado + `window.prompt` + emojis.
- **Despues**:
  1. **Shell comun** (todas las paginas): header sticky 56px con marca, nav
     (`Descargar` / `Biblioteca` / `Ayuda`), indicador de servidor/job en vivo y
     boton **Ajustes** (Popover con: token de acceso y selector de tema
     auto/claro/oscuro). Footer de una linea.
  2. **Job bar global**: componente unico (markup compartido + `jobs.js`),
     accesible desde cualquier pagina. Al cargar, consulta `GET /api/jobs` y si
     hay un job pendiente/en curso **se reconecta** (WebSocket + polling
     fallback). Sustituye el panel duplicado. Muestra fases (descarga /
     traduccion / EPUB), linea de estado, cancelar y, al terminar, refresca.
  3. **Home `/`**:
     - Sin hero ni kickers: un titulo de tarea y una unica **tarjeta de tarea**.
     - **Segmented "Desde web / Desde PDF"** en lugar de dos formularios
       apilados.
     - Formulario web: URL + boton; **"Opciones avanzadas"** plegadas (capitulos
       por tomo, concurrencia descarga, concurrencia traduccion, traducir +
       idioma destino, todos, pendientes, forzar, playwright).
     - **Recordar ultimas opciones** (`localStorage["novel_web_options"]`) para
       relanzar en un clic.
     - **Confirmacion** al marcar *Forzar re-descarga* y *Todos los capitulos*.
     - **Ayuda inline**: icono "?" (Tooltip/Popover) junto a los controles no
       obvios.
     - "Recientes": lista compacta con estado + enlace a la biblioteca.
  4. **Iconos SVG** (helper de 05) — se eliminan los emojis.

## Technical decision

- **Sin motor de plantillas**: el shell (header/footer/job bar) se inserta en
  tiempo de servido con un helper Python minimo en `app.py::_template` que
  reemplaza placeholders (`<!--shell:header-->`, `<!--shell:jobbar-->`,
  `<!--shell:footer-->`) por parciales de `templates/partials/`. Asi no hay FOUC
  ni dependencia nueva. (Alternativa JS descartada por el parpadeo.)
- El **estado del job** vive en `common.js`/`jobs.js`; cualquier pagina puede
  engancharse al job bar global reutilizando el WebSocket existente
  (`/api/jobs/{id}/ws`).
- `localStorage`: `novel_web_theme` (05), `novel_web_token` (ya existe),
  `novel_web_options` (nuevo).
- **Sin cambios** en `routes.py` / `jobs.py` / `ws.py`.

## Affected files

- `src/novel_cli/web/templates/partials/{header,jobbar,footer}.html` — **nuevos**.
- `src/novel_cli/web/templates/index.html` — home reestructurada.
- `src/novel_cli/web/static/js/common.js` — shell, Ajustes, tema, opciones,
  helpers compartidos (`confirmDialog`).
- `src/novel_cli/web/static/js/jobs.js` — job bar global + reconexion al cargar.
- `src/novel_cli/web/static/js/app.js` — home (segmented, opciones, recientes).
- `src/novel_cli/web/static/css/app.css` — estilos de shell y home.
- `src/novel_cli/web/app.py` — helper de parciales en `_template`.
- `tests/test_web.py` — asserts.

## Tests

- `tests/test_web.py`: `/` sigue 200 y contiene el shell (nav) y el contenedor
  del job bar (`id="job-bar"`). Sin red.

## Acceptance criteria

- El shell y el job bar aparecen en las 4 paginas; navegar no pierde el job en
  curso.
- La home permite elegir web/PDF con un Segmented y plegar las opciones
  avanzadas; las ultimas opciones se recuerdan al recargar.
- El token se introduce en **Ajustes** (se elimina `window.prompt`).
- Confirmacion visible en Forzar / Todos; sin emojis.
- `uv run pytest -q` y `uv run ruff check .` pasan.
