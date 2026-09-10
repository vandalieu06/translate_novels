# 00 — Changelog (0.1.1 → 0.1.2)

Cambios introducidos desde las specs `0.1.1`. Cada entrada indica qué, por qué,
archivos afectados y estado. Formato estándar de spec de feature: ver `01-web-ui.md`.

| # | Cambio | Por qué | Estado | Commit |
|---|--------|---------|--------|--------|
| 1 | **Web multi-página**: `/` (descarga + recientes), `/biblioteca` (grid de portadas), `/novela/{slug}` (ficha individual con acciones y EPUBs), `/ayuda` (guía de acciones). Refactor de `app.js` en módulos compartidos (`common.js`, `jobs.js`). | La SPA de una sola página acumulaba descarga + biblioteca completa + acciones por novela; peso excesivo y poca navegabilidad desde tablet. | implementado | — |
| 2 | **EPUBs en lista de una línea**: `.epub-grid` pasa a una sola columna y `.epub-name` muestra el nombre completo (sin ellipsis, con `overflow-wrap: anywhere`). | En el grid de columnas los nombres largos se truncaban y no se sabía a qué tomo hacía referencia. | implementado | — |
| 3 | **Header responsive**: `.backend-pill` oculto ≤960px; nav compacto ≤720px; a ≤560px `flex-wrap` + status a solo punto (sin texto) para eliminar el scroll horizontal en móvil. Fix del hover del brand (azul). | El header desbordaba en anchos pequeños (suma de pill/nav/status + gaps > viewport) y provocaba scroll horizontal. | implementado | — |
| 4 | **Traducción con idioma destino**: lista curada de idiomas (`config.TRANSLATE_TARGET_LANGUAGES`), campo `translated_language` en manifest, `target` cableado en pipeline/CLI (`--target`)/web, `POST /novels/{slug}/retranslate` acepta `{target_language}` (force si cambia de idioma), botón "Traducir" con modal de idiomas en la ficha y selector de idioma en descarga. | Traducir estaba fijado a `es` y no había forma web de traducir una novela no traducida. | implementado | — |
| 5 | **EPUB: página final en cada tomo**: `build_epub` añade `end.xhtml` (FIN/THE END según idioma + ficha: título, rango start–end, autor, idioma de traducción) al final del spine, oculta del TOC, opcional vía `include_end_page`. Aplica a original, traducido y `rebuild_volumes`. | El EPUB terminaba abruptamente tras el último capítulo, sin página de cierre. | implementado | — |

## Formato de spec de feature

```
# NN — <Nombre>
- Estado: propuesto | en desarrollo | implementado | aceptado
- Versión spec: <0.1.2> · Fecha: <...> · Relacionado: <0.1.1/....md si aplica>

## Propósito
## Contexto / Problema
## Cambio propuesto (antes → después)
## Decisión técnica
## Archivos afectados
## Tests
## Criterios de aceptación
```