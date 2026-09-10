# 04 — Web: regenerar EPUBs (página final) desde la ficha

- Estado: implementado · Versión spec: 0.1.2 · Fecha: 2026-09-10 · Relacionado: 0.1.2/03-epub-end-page.md, 0.1.1/01-web.md

## Propósito

Poder **regenerar los EPUBs de una novela desde la web** con un clic, sin
cambiar el tamaño de tomo ni re-descargar/re-traducir. Necesario para aplicar
cambios del builder (p. ej. la nueva página final `end.xhtml` de
`0.1.2/03-epub-end-page.md`) a EPUBs ya generados.

## Contexto / Problema

`build_epub` ahora añade la página final, pero los EPUBs existentes no se
regeneran solos: el `resume` los salta. Hasta ahora la única forma era cambiar
el tamaño de tomo (`volume-size`) o usar la CLI con `--force`. No había una
acción web explícita de "reconstruir los EPUBs desde disco".

## Cambio propuesto (antes → después)

**Antes:** la ficha (`/novela/{slug}`) solo ofrece Sync, Traducir/Re-traducir,
Tomos y Fuente; no hay forma de regenerar EPUB sin cambiar el tamaño de tomo.

**Después:**
- Nuevo endpoint síncrono `POST /api/novels/{slug}/rebuild` (sin job ni
  WebSocket: es CPU local). Carga el `Manifest`, valida que exista y llama a
  `rebuild_volumes(slug_dir, manifest.volume_size)` (mismo `volume_size`),
  devolviendo `{ok, volume_size, epub_original, epub_translated}`. 404 si no
  hay novela o el pipeline lanza `PipelineError` (p. ej. sin capítulos en disco).
- Botón **"Regenerar EPUBs"** en `#novel-actions` de la ficha, junto a
  Sync/Traducir/Tomos. Al pulsar: `setButtonLoading`, POST, toast
  "EPUBs regenerados" y `refreshNovels()` para refrescar la lista.
- Entrada en `help.html` documentando la acción.

## Decisión técnica

- Se reutiliza `rebuild_volumes` del core (ya reconstruye original+traducido
  desde disco con `rebuild=True`, refresca `chapters_empty` y limpia
  huérfanos). No se duplica lógica ni se toca `pipeline.py`.
- Endpoint síncrono como `volume-size` (no crea `Job`): la operación es local y
  rápida; evita ocupar el lock de jobs y el panel de progreso.
- Sin body ni modelos nuevos; el tamaño de tomo permanece intacto por diseño.

## Archivos afectados

`src/novel_cli/web/routes.py` (endpoint), `src/novel_cli/web/static/js/novel.js`
(botón + handler), `src/novel_cli/web/templates/novel.html` (si hiciera falta
soporte), `src/novel_cli/web/templates/help.html`, `tests/test_web.py`, `docs/`.

## Tests

- `POST /rebuild` con slug inexistente → 404.
- `POST /rebuild` con novela y `raw/` en disco → 200, `ok=True`, reconstruye
  `epub_original`, conserva `volume_size` y los EPUBs incluyen `end.xhtml`.

## Criterios de aceptación (Done cuando)

- En la ficha aparece "Regenerar EPUBs"; al pulsarlo se reconstruyen los tomos
  (original y traducido) con la página final y la lista se refresca.
- `uv run pytest -q` y `uv run ruff check .` pasan.