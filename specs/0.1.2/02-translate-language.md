# 02 — Traducción con idioma destino elegible

- Estado: implementado · Versión spec: 0.1.2 · Fecha: 2026-09-07 · Relacionado: 0.1.0/05-translation.md, 0.1.1/01-web.md

## Propósito

Permitir elegir el **idioma de traducción** (no fijo a español) tanto al lanzar
una descarga nueva como al **traducir una novela ya descargada que aún no está
traducida** (hoy la UI solo ofrece "Re-traducir" y lo oculta si `!translated`).

## Contexto / Problema

El `Translator` (`core/services/translate.py`) ya acepta `target` por llamada
(Google y LibreTranslate lo pasan), pero el flujo entero lo fija a `"es"`:
`run_pipeline`/`_run_translate_pending` no reciben target, el EPUB usa `language="es"`
y el sufijo `(ES)` está hardcodeado, el manifest no guarda el idioma destino y la
UI muestra "Traducir a español (ES)" fijo. Además, traducir por primera vez una
novela solo es posible por CLI (`-t` al descargar); en la web el botón
"Re-traducir" se oculta salvo que `translated` sea true. Es un item del roadmap
(`specs/0.1.1/08-roadmap.md`) sin spec.

## Cambio propuesto (antes → después)

**Antes:** traducción siempre a `es`; sin forma web de traducir una novela no traducida.

**Después:**
- Lista curada de idiomas destino (`config.TRANSLATE_TARGET_LANGUAGES`) con
  etiqueta, expuesta en `/api/config`.
- Manifest: nuevo campo `translated_language: str | None` (compatible con
  manifests viejos; `translated=True` sin idioma ⇒ `es`).
- Pipeline: `run_pipeline`/`_run_translate_pending` reciben `target` y lo pasan a
  `translate_chapters`, al `language=` del EPUB y al sufijo del nombre
  (`(ES)` → `(<LANG>)`). `rebuild_volumes` usa `manifest.translated_language`.
- CLI: flag `--target <lang>` en `run` (default `es`, validado contra la lista).
- Web: `POST /novels/{slug}/retranslate` acepta `{target_language}`; si cambia de
  idioma se fuerza la re-traducción (solo traducción, sin descargar) y se persiste
  el idioma. `sync` hereda el idioma. `_novel_payload` expone `translated_language`.
- UI: botón **"Traducir"** en la ficha cuando `!translated` que abre un **modal de
  idiomas** (píldoras estilo tomos); selector de idioma en el formulario de
  descarga al activar "Traducir". Badge y "Traducción (ES)" muestran la etiqueta
  del idioma real.

## Decisión técnica

- **Una lengua a la vez** por novela: `translated/` único y `epub_translated`
  único; cambiar de idioma re-traduce todos los capítulos (force solo en el flujo
  translate-only) y los EPUBs viejos se limpian como huérfanos (mecanismo ya
  existente).
- **Lista curada fija** (no dinámica por backend); con LibreTranslate un idioma
  sin modelo instalado fallará con el error de la API (visible en la UI).
- `translate.py` no cambia (ya acepta `target`); solo se cablea el paso del valor.

## Archivos afectados

- `src/novel_cli/core/config.py`
- `src/novel_cli/core/models/state.py`
- `src/novel_cli/core/services/pipeline.py`
- `src/novel_cli/cli/app.py`
- `src/novel_cli/web/routes.py`, `src/novel_cli/web/jobs.py`, `src/novel_cli/web/app.py` (config)
- `src/novel_cli/web/static/js/novel.js`, `jobs.js`, `common.js`
- `src/novel_cli/web/templates/novel.html`, `index.html`, `help.html`
- `src/novel_cli/web/static/css/app.css`
- `tests/`, `docs/`, `specs/`

## Tests

- Retranslate con `target_language` → `target`/`force` pasados a `run_pipeline`.
- Retranslate sin cuerpo → idioma del manifest.
- Sync hereda `translated_language`.
- `_novel_payload` expone `translated_language`; `/api/config` expone idiomas.
- Job nuevo con `translate_language` (form descarga).
- CLI `--target` válido/inválido.

## Criterios de aceptación (Done cuando)

- En la ficha de una novela no traducida aparece "Traducir"; al elegir idioma se
  traduce, se persiste `translated_language`, el badge/EPUBs muestran el idioma.
- En descarga, "Traducir" + selector de idioma funcionan.
- `uv run pytest -q` y `uv run ruff check .` pasan.