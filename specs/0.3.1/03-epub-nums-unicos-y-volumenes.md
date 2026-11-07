---
code: "03"
title: "EPUB: numeros unicos, sin recursos duplicados y tomos con rangos reales"
project: "novel_cli"
status: completed
version: "0.3.1"
date: 2026-11-07
tags: [spec, sdd, epub, volumes]
affected_files:
  - src/novel_cli/core/services/pipeline.py
  - src/novel_cli/core/services/epub.py
  - tests/test_epub.py
  - tests/test_pipeline.py
---

# 03 — EPUB: numeros unicos, sin recursos duplicados y tomos con rangos reales

## Purpose

Garantizar que cada capitulo tenga un `num` unico antes de descargar/escribir, que el builder de
EPUB no pueda emitir dos recursos con el mismo `href`, y que los nombres de tomo
(`1-50`, `51-100`, …) correspondan a rangos reales de capitulos.

## Context

En la novela de NovelPhoenix, `chapter-8` y `chapter-88` se parsearon ambos como `num=88`
(consecuencia del bug del spec 01). Efectos observados:

- `download_chapters` descargo 50 capitulos pero escribio **49** ficheros: `raw/0088.md` se
  sobrescribio dos veces; el texto del capitulo 8 se perdio.
- `_load_all_chapters` recorre el TOC y anade el fichero **por cada** entrada con el mismo `num`,
  asi que el EPUB 1 quedo con 50 *slots* pero solo 49 capitulos distintos.
- `epub._add_chapter` (`epub.py:98-113`) nombra el XHTML `chapter{num:04d}.xhtml` sin validar
  unicidad. El ZIP resultante tiene **dos** entradas `EPUB/chapter0088.xhtml` y `content.opf` dos
  `<item>` con el mismo `href` (ids distintos): EPUB invalido para epubcheck; `nav.xhtml` tambien
  lo lista dos veces.
- Los nombres `11-3333` / `3434-8383` salen de `volume.start`/`volume.end`
  (`pipeline.py:391-392`, `epub.generate_volumes`), es decir, de los `num` corruptos.

El bug de numeracion se corrige en el spec 01; este spec se ocupa de que **no vuelva a producirse
un EPUB corrupto** si el sitio/parsers introducen colisiones, y de fijar el contrato de rangos de
tomo.

## Proposed change

1. **Validacion temprana de `num` unicos** en `pipeline.run_pipeline`, justo despues de
   `_resolve_toc` y antes de descargar:

   ```python
   duplicate_nums = _duplicate_nums(site.chapters)
   if duplicate_nums:
       detail = ", ".join(
           f"{num}: {', '.join(urls)}" for num, urls in duplicate_nums.items()
       )
       raise PipelineError(f"numeros de capitulo duplicados en el TOC: {detail}")
   ```

   Asi el job falla **antes** de sobrescribir `raw/` o de perder texto. (Alternativa descartada:
   renumerar silenciosamente, porque rompe la identidad de `raw/NNNN.md` entre runs.)

2. **Defensa en `_load_all_chapters`** (`pipeline.py:476-483`): deduplicar por `num` (primera
   entrada gana) y registrar un `WARNING` con la URL ignorada, por si el TOC viene de una cache
   antigua o de un adapter de terceros que no paso la validacion.

3. **Validacion final en el builder**: `generate_volumes` (o `build_epub`) comprueba
   `len({c.num for c in chapters}) == len(chapters)` y lanza `ValueError`/`PipelineError` con un
   mensaje claro. Nunca se vuelve a escribir un EPUB con `href` duplicado.

4. **Contrato de rangos de tomo**:
   - `volume.start` / `volume.end` son el primer y ultimo `num` **real** del bloque (con el spec 01
     ya son 1/50, 51/100, …).
   - Descarga completa (`--all`) de 513 capitulos con `volume_size=50` → **11 tomos**:
     `1-50, 51-100, 101-150, 151-200, 201-250, 251-300, 301-350, 351-400, 401-450, 451-500,
     501-513`.
   - Descarga parcial: el nombre refleja lo que contiene el fichero. Con 100 capitulos →
     `1-50` y `51-100`; con 99 (por un vacio) → `1-50` y `51-99`. Se documenta como comportamiento
     aceptado; no se generan tomos vacios de capitulos no descargados.
   - Queda como mejora futura (fuera de alcance) trocear el **TOC completo** y etiquetar los
     bloques por posicion para que un tomo parcial se siga llamando `51-100`; exigiria pasar el TOC
     a `generate_epubs` y filtrar grupos con al menos un capitulo descargado.

## Technical decision

- **Fail fast sobre datos ambiguos**: dos capitulos con el mismo `num` implican el mismo
  `raw/NNNN.md` y el mismo `chapterNNNN.xhtml`; es preferible abortar el job con un mensaje
  accionable que entregar un EPUB invalido o perder texto en silencio.
- La validacion vive en `pipeline` (no en `epub`) para que los flujos CLI, web, `--translate-pending`
  y `rebuild_volumes` compartan la misma garantia. `build_epub` mantiene una asercion defensiva
  porque es una API publica del modulo.
- No se renombran ficheros existentes: una novela ya corrupta se re-descarga manualmente (la
  limpieza operativa de la novela afectada se documenta en el informe de investigacion; no se
  automatiza en este spec).
- `cleanup_orphan_epubs` sigue igual: cuando el ultimo tomo crece (`501-513` → `501-520`) se genera
  el nuevo nombre y el viejo se borra **al final** del run, nunca antes de escribir el nuevo.
- No se toca la pagina final (`end.xhtml`): su texto `Capitulos {start}–{end}` se vuelve correcto
  automaticamente al arreglar los `num`.

## Affected files

- `src/novel_cli/core/services/pipeline.py` — validacion de duplicados, dedupe en
  `_load_all_chapters`, mensajes.
- `src/novel_cli/core/services/epub.py` — validacion de unicidad en `generate_volumes`/`build_epub`.
- `tests/test_epub.py` — EPUB sin recursos duplicados; error con nums repetidos.
- `tests/test_pipeline.py` — job abortado antes de descargar con TOC duplicado; 11 tomos con 513.

## Tests

- TOC sintetico con `chapter-8` y `chapter-88` mapeados al mismo `num`: `run_pipeline` lanza
  `PipelineError` y `raw/` queda vacio (no se descarga nada).
- `_load_all_chapters` con dos entradas del mismo `num`: carga una sola y emite warning.
- `build_epub`/`generate_volumes` con `nums=[1, 1]`: error claro; el ZIP no se genera.
- `generate_volumes` con 513 capitulos contiguos y `volume_size=50`: 11 volumenes con
  `[(1,50), (51,100), …, (501,513)]`.
- Pipeline completo con 513 capitulos fake y `download_all=True`: 11 EPUBs con esos nombres y sin
  entradas duplicadas en el ZIP (`len(names) == len(set(names))`).
- Pipeline con 100 capitulos: 2 EPUBs `1-50` y `51-100`.
- El caso 99 capitulos (hueco simulado): 2 EPUBs `1-50` y `51-99` (comportamiento documentado).

## Acceptance criteria

- [ ] Es imposible que un job escriba dos capitulos en el mismo `raw/NNNN.md` sin avisar.
- [ ] Un EPUB generado por el pipeline no contiene entradas ZIP ni `<item>` con `href` repetido.
- [ ] `--all` + `volume_size=50` + 513 capitulos → 11 tomos `1-50 … 501-513`.
- [ ] Los nombres de tomo usan numeros reales de capitulo, no IDs ni concatenaciones.
- [ ] Tests y lint en verde; `docs/arquitectura.md` describe el contrato de rangos.
