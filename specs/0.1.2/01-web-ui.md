# 01 — Web multi-página (biblioteca por portadas, ficha de novela y guía)

- Estado: implementado · Versión spec: 0.1.2 · Fecha: 2026-09-07 · Relacionado: 0.1.1/01-web.md

## Propósito

Mejorar la experiencia web desde tablet: separar la biblioteca de la descarga,
ofrecer una ficha individual por novela con sus acciones y EPUBs, y añadir una
guía rápida de qué hace cada acción. UI más visual e interactiva.

## Contexto / Problema

La web actual (spec `0.1.1`) es una SPA de una sola página (`index.html` +
`app.js` + `app.css`) que apila en el mismo scroll: hero/estadísticas, formulario
de descarga, progreso en vivo y la biblioteca completa con todas las acciones por
novela (Sync, Re-traducir, Tomos, descargas de EPUB). El peso de renderizar toda
la biblioteca en la página inicial y la falta de una vista "solo portadas" o de
ficha dedicada degradan la navegación y la sensación visual.

El backend ya cubre todo lo necesario sin cambios en `/api/*`:
`GET /api/novels`, `GET /api/novels/{slug}`, `GET .../cover`, `GET .../epub/{name}`,
`POST .../sync`, `POST .../retranslate`, `POST .../volume-size`, y el progreso por
WebSocket/polling.

## Cambio propuesto (antes → después)

**Antes:** una sola página con todo (descarga + biblioteca completa + acciones).

**Después:**
- `GET /` — landing: hero + estadísticas + formulario de descarga + panel de
  progreso en vivo + franja compacta de **novelas recientes** (portadas) que
  enlaza a la biblioteca.
- `GET /biblioteca` — **grid de solo portadas** (responsive, 2/3/4 columnas según
  pantalla), con indicador de traducido y aviso de capítulos vacíos; tap en la
  portada → ficha de la novela.
- `GET /novela/{slug}` — **ficha individual**: portada grande, título/autor,
  badges, barra de progreso, aviso de vacíos, enlace a la fuente, acciones
  (Sync, Re-traducir, Tomos) con su panel de progreso de job, y listado/grid de
  EPUBs agrupados en Original y ES con botón de descarga.
- `GET /ayuda` — **guía estática** de cada acción disponible (Descargar, Sync,
  Re-traducir, Tomos, EPUB, checkboxes del formulario, Cancelar) con una breve
  descripción de qué hace.

Refactor de JS: `app.js` (548 líneas) se parte en módulos compartidos vanilla
manteniendo el estilo actual — `common.js` (auth/token, `api()`, toast, config,
estado servidor, `escapeHtml`, tarjeta de portada), `jobs.js` (`hasActiveJob`,
WebSocket + polling, panel de progreso, cancelar, sync/retraducción, reutilizable
en landing y ficha), y un módulo por página (`app.js` landing, `library.js`,
`novel.js`). La guía (`/ayuda`) es **HTML estático**, sin JS propio. Navegación
común en todas las páginas: **Descargar · Biblioteca · Ayuda**, con estado activo
por página (`setupNavActive` en `common.js`).

## Decisión técnica

- **Páginas separadas** (no SPA con routing): URLs reales, botón atrás del
  navegador natural, más simple y ligero para tablet. Cada página es un HTML
  estático servido por FastAPI que carga un JS específico; los datos se obtienen
  de la API existente (`/api/*` no cambia).
- La ficha lee el slug de la ruta en `novel.js` y consulta `GET /api/novels/{slug}`.
- El panel de progreso y el modal de tomos se comparten vía `jobs.js` y el mismo
  marcado en `index.html` y `novel.html`.
- **Sin** endpoint nuevo de resumen: los payloads de `GET /api/novels` son
  pequeños (manifest), se reutilizan para el grid.
- `core` intacto; la web sigue siendo capa de presentación pura.

## Archivos afectados

- `src/novel_cli/web/app.py` (servir las 4 páginas)
- `src/novel_cli/web/templates/index.html` (landing: + franja recientes)
- `src/novel_cli/web/templates/library.html` (nuevo)
- `src/novel_cli/web/templates/novel.html` (nuevo)
- `src/novel_cli/web/templates/help.html` (nuevo)
- `src/novel_cli/web/static/js/common.js` (nuevo)
- `src/novel_cli/web/static/js/jobs.js` (nuevo)
- `src/novel_cli/web/static/js/app.js` (landing, refactor)
- `src/novel_cli/web/static/js/library.js` (nuevo)
- `src/novel_cli/web/static/js/novel.js` (nuevo)
- `src/novel_cli/web/static/css/app.css` (grid portadas, ficha, EPUBs)
- `tests/test_web.py`, `docs/arquitectura.md`, `docs/uso.md`, `docs/features.md`

## Tests

- Las 4 páginas (`/`, `/biblioteca`, `/ayuda`, `/novela/{slug}`) se sirven con 200.
- Las páginas nuevas no requieren auth (como `/` actual); `/api/*` sigue protegida.
- Se mantienen los tests existentes con el mock de `web.jobs.run_pipeline`.

## Criterios de aceptación (Done cuando)

- `/`, `/biblioteca`, `/novela/{slug}`, `/ayuda` se sirven y navegan entre sí.
- La biblioteca muestra solo portadas en grid y cada portada abre su ficha.
- La ficha muestra info, acciones y EPUBs; Sync/Re-traducir/Tomos funcionan con
  su progreso en vivo y actualizan la biblioteca.
- `/ayuda` explica cada acción de forma breve.
- `uv run pytest -q` y `uv run ruff check .` pasan.