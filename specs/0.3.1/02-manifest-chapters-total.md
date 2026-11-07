---
code: "02"
title: "Manifest: chapters_total es el total del TOC, no lo descargado"
project: "novel_cli"
status: completed
version: "0.3.1"
date: 2026-11-07
tags: [spec, sdd, manifest, web]
affected_files:
  - src/novel_cli/core/services/download.py
  - src/novel_cli/core/services/pipeline.py
  - tests/test_download.py
  - tests/test_pipeline.py
  - tests/test_web.py
  - docs/arquitectura.md
  - docs/uso.md
---

# 02 — Manifest: chapters_total es el total del TOC, no lo descargado

## Purpose

Que `manifest.chapters_total` refleje el tamano del **TOC completo** y
`manifest.chapters_downloaded` los capitulos con contenido en disco, de modo que la API, la web,
la app y el historial muestren el progreso real de una novela descargada por tomos.

## Context

En la novela `surviving-in-womans-world-as-a-novel-villain` el TOC tiene **513** capitulos y
`raw/` tiene **99**, pero el manifest y `GET /api/novels/<slug>` dicen `chapters_total=99` y
`chapters_downloaded=99`. La UI calcula `downloaded / total` (`web/static/js/novel.js:55-60`,
`web/static/js/common.js:135-136`) y muestra **100 %**: la novela parece completa.

Causas:

1. `services/pipeline.py:251`:
   ```python
   manifest.chapters_total = manifest.chapters_downloaded
   ```
   Pisa el total del TOC con lo descargado.
2. `services/download.py:67`:
   ```python
   manifest.chapters_total = len(chapters)   # chapters = lote (<= volume_size)
   ```
   Aunque no existiera el override anterior, el total seria el del lote (50), no el del TOC.

El unico sitio que ya conoce el total correcto es la notificacion `scrape_done`
(`pipeline.py:201`, `len(site.chapters)`), que no se persiste. Por eso Telegram decia 513 y la API
99.

Aclaraciones:

- El contador **no** se usa para reanudar: la fuente de verdad es la existencia de ficheros.
  (La spec `0.1.0/07-state.md:35-36` dice lo contrario y esta desactualizada.)
- `chapters_downloaded` ya cuenta solo ficheros con contenido y numeros unicos
  (`download.py:165-166`); el problema es solo `chapters_total`.

## Proposed change

1. **`services/download.py`** — aceptar el total explicito y no inferirlo del lote:

   ```python
   async def download_chapters(
       ...,
       on_progress: ProgressCallback | None = None,
       total_chapters: int | None = None,
   ) -> list[Chapter]:
       manifest.chapters_total = (
           len(chapters) if total_chapters is None else total_chapters
       )
   ```

   El valor por defecto conserva el comportamiento de llamadas directas/tests antiguos.

2. **`services/pipeline.py`** — pasar el total del TOC y eliminar el override:

   ```python
   await download_chapters(
       ...,
       total_chapters=len(site.chapters),
   )
   ...
   # eliminar:
   # manifest.chapters_total = manifest.chapters_downloaded
   ```

3. **Documentacion** — actualizar `docs/arquitectura.md` (seccion de estado) y
   `docs/uso.md` (ejemplo de `runs.jsonl`) para explicar que `chapters_total` es el TOC y
   `chapters_downloaded` lo que hay en disco. Corregir el drift de `specs/0.1.0/07-state.md`
   (o anotarlo como historico).

## Technical decision

- `chapters_total` es una propiedad del TOC, no del run: no debe depender de `volume_size`,
  `--all`, `--force` ni de cuantos capitulos se hayan bajado en esta ejecucion.
- Se fija al resolver el TOC (`_resolve_toc`) y se pasa a la descarga; cualquier otra fase
  (EPUB, traduccion, rebuild) lo conserva.
- `chapters_downloaded` sigue siendo **derivado del disco** (numeros unicos con parrafos), para
  que `--force`, archivos borrados a mano y capitulos vacios se reflejen sin tocar el total.
- Con descarga por tomos, `downloaded < total` es el estado normal; el porcentaje puede quedarse
  en 10 %, 20 %, … hasta completar la novela. Eso es lo deseado.
- No se anade un campo nuevo al manifest (evita migraciones); `chapters_total` ya existe y el
  contrato de la API no cambia.
- Riesgo: manifests antiguos con `chapters_total` erroneo se corrigen solos en el siguiente run
  que resuelva el TOC (incluido Sync con cache).

## Affected files

- `src/novel_cli/core/services/download.py` — parametro `total_chapters` y asignacion.
- `src/novel_cli/core/services/pipeline.py` — llamada y eliminacion del override.
- `tests/test_pipeline.py` — expectativas de total con lote parcial.
- `tests/test_download.py` — caso de `total_chapters` explicito.
- `tests/test_web.py` — payload de `/api/novels/<slug>` con progreso real.
- `docs/arquitectura.md`, `docs/uso.md` — semantica de los contadores.

## Tests

- TOC de 4 capitulos, lote de 2 (`volume_size=2`, sin `--all`):
  `manifest.chapters_total == 4`, `chapters_downloaded == 2`.
- Segunda ejecucion (avanza el tomo): total sigue 4, downloaded 4.
- Descarga completa (`--all`): total == downloaded == 4.
- `download_chapters(..., total_chapters=10)` con un lote de 3 deja `chapters_total == 10`.
- `GET /api/novels/<slug>` devuelve `chapters_total=4`, `chapters_downloaded=2` y la UI calcula
  50 % (test de payload; el JS no se testea).
- `rebuild_volumes` no modifica `chapters_total`.
- El historial (`runs.jsonl`) y la notificacion `scrape_done` coinciden con el manifest.

## Acceptance criteria

- [ ] Tras el primer tomo de una novela de 513 capitulos, el manifest dice `total=513`,
      `downloaded=50` (o los que se hayan bajado), no `50/50`.
- [ ] El porcentaje de la web/app es < 100 % mientras falten capitulos.
- [ ] Al completar la novela, `downloaded == total`.
- [ ] `chapters_total` no se sobrescribe en ninguna fase posterior a la descarga.
- [ ] La existencia de ficheros sigue siendo la unica fuente de verdad para reanudar.
- [ ] Tests y lint en verde; docs actualizadas.
