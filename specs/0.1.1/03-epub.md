# 03 — EPUB: placeholders, regeneración y tomos

- Estado: implementado · Versión spec: 0.1.1

## Propósito

EPUBs coherentes aunque falten capítulos: sin páginas en blanco, tomos
alineados entre original y traducido, regeneración fiable y re-volumizado.

## Contexto / Problema

- Capítulos vacíos salían en blanco y los tomos traducidos tenían rangos
  irregulares (`1-61`, `62-123`…) porque se troceaba la lista traducida (con huecos).
- "Re-traducir"/sync no regeneraban los EPUBs `(ES)` existentes (`resume` los saltaba).
- No había forma de cambiar el tamaño de tomo sin re-descargar.

## Cambio propuesto

- **Placeholders**: `_build_epub_chapters(reference, chapter_dir, placeholder)` devuelve una lista del mismo tamaño/orden que la raw; los capítulos sin contenido llevan `EMPTY_PLACEHOLDER_EN`/`EMPTY_PLACEHOLDER_ES`. Aplica a original (raw) y traducido.
- **Tomos alineados**: con la lista traducida del mismo largo que la raw, `generate_volumes` produce los mismos rangos que el original (50/tomo).
- **Regeneración**: `_generate_epubs(rebuild=True)` reescribe los ES aunque existan (usado por re-traducir/sync). `_cleanup_orphan_epubs` borra `*.epub` que ya no están en el manifest.
- **`rebuild_volumes(slug_dir, volume_size)`**: reconstruye original+traducido desde el disco con el nuevo tamaño (`None` = un único EPUB/ALL); actualiza `manifest.volume_size`.

## Decisión técnica

`generate_volumes` trocea por posición; mantener listas del mismo largo es lo que alinea los rangos. `rebuild_volumes` es síncrono y sin red.

## Archivos afectados

`core/services/pipeline.py` (`_build_epub_chapters`, `_cleanup_orphan_epubs`, `rebuild_volumes`, `rebuild`), `core/services/translate.py`, `web/routes.py` (`POST /novels/{slug}/volume-size`), UI (modal de tomos).

## Tests

Placeholders EN/ES en original y traducido, alineación de tomos, rebuild en translate-pending, limpieza de huérfanos, rebuild_volumes (cambios de tamaño y ALL).

## Criterios de aceptación

- EPUB traducido con los mismos rangos que el original, sin páginas en blanco.
- Re-traducir regenera los ES; la carpeta queda sin EPUBs huérfanos.
- Cambiar tamaño de tomo reconstruye los EPUBs y actualiza el manifest.