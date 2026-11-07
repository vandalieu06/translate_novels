---
code: "04"
title: "Cancelacion observable, sin perder trabajo y con lock por novela"
project: "novel_cli"
status: completed
version: "0.3.1"
date: 2026-11-07
tags: [spec, sdd, web, jobs, cancelacion]
affected_files:
  - src/novel_cli/web/jobs.py
  - src/novel_cli/web/routes.py
  - src/novel_cli/core/services/download.py
  - src/novel_cli/core/services/pipeline.py
  - tests/test_web.py
---

# 04 — Cancelacion observable, sin perder trabajo y con lock por novela

## Purpose

Que cancelar un job desde la web/app (a) detenga el trabajo en un punto seguro, (b) deje el estado
`cancelled` de inmediato, (c) conserve los capitulos ya descargados y (d) impida que dos jobs
escriban a la vez en el mismo directorio de novela.

## Context

En el incidente del 2026-11-07 se creia que "cancelar no frena el worker", pero el log demuestra
que **si funciono**:

```
06:02:20 job 90accac546af iniciado
06:03:18 WARNING job 90accac546af cancelado        # 57,58 s; no escribio ningun raw/*.md
06:11:41 job 886ed96c67d3 iniciado                 # otro job, creado por el cliente
06:12:48 EPUB original generado: 1 tomo(s)         # este EPUB es del job 886..., no del cancelado
```

Aun asi, hay limitaciones reales en `web/jobs.py`:

1. `cancel()` (`jobs.py:143-148`) llama a `task.cancel()`, pero **no** cambia `job.state` ni emite
   un evento; si el task esta en una seccion sincrona, la UI sigue viendo `running` y el endpoint
   responde `{"cancelled": true}` sin esperar a que el task muera.
2. `download_chapters` (`download.py:98-130`) guarda **todos** los capitulos al final, despues del
   `asyncio.gather`. Un cancel a mitad pierde todo lo descargado (aqui, ~57 s de trabajo).
3. La generacion de EPUB (`build_epub`) y `manifest.save` son sincronas: un cancel durante esas
   fases solo se atiende al volver al event loop. Es aceptable, pero debe documentarse y
   comprobarse entre fases.
4. `JobManager` no impone el "un job activo a la vez" que sugiere el docstring (`jobs.py:86-108`).
   Dos jobs sobre la misma novela pueden pisarse: `.manifest.json`, `raw/`, `.toc.json` y EPUBs.
   En el incidente fueron secuenciales, pero es una carrera latente.

## Proposed change

1. **Estado de cancelacion inmediato** (`web/jobs.py`):

   ```python
   JOB_CANCELLING = "cancelling"

   async def cancel(self, job_id: str) -> bool:
       job = self._jobs.get(job_id)
       if job is None or job.task is None or job.task.done():
           return False
       job.state = JOB_CANCELLING
       job.status("cancelling", "Cancelando…")
       job.task.cancel()
       return True
   ```

   `_run_web` mantiene el `except asyncio.CancelledError` que pasa a `JOB_CANCELLED` cuando el task
   confirma la cancelacion. El endpoint puede devolver `{"cancelled": true, "state": "cancelling"}`
   (compatible: se conserva la clave `cancelled`).

2. **Guardado incremental de capitulos** (`core/services/download.py`): escribir cada
   `raw/NNNN.md` en cuanto se parsea, dentro de `fetch_one`, en lugar de acumular resultados y
   guardarlos tras el `gather`. El progreso (`on_progress`) se emite igual; un cancel conserva lo
   ya escrito. Hay que serializar las escrituras (un `asyncio.Lock` o escritura atomica por
   fichero) para no mezclar contenido.

3. **Puntos de cancelacion entre fases** (`core/services/pipeline.py`): tras descarga y antes de
   EPUB/traduccion, un `await asyncio.sleep(0)` (o un helper `_check_cancelled()`) para que un
   cancel pendiente se atienda antes de empezar una fase larga. La fase sincrona de EPUB no se
   interrumpe a mitad; se documenta.

4. **Lock por novela** (`web/jobs.py`):

   - Clave: URL normalizada (`rstrip("/")`) mientras el slug no se conoce; al resolver el TOC,
     pasar a `slug`.
   - `create()` rechaza un segundo job con la misma clave (`JobAlreadyRunning`), y el router
     devuelve `409` con `{"detail": "ya hay un job para esta novela", "job_id": ...}`.
   - El lock se libera en el `finally` de `_run*` (exito, error o cancelacion).
   - Alternativa aceptada si se prefiere no rechazar: dejar el job en `pending` y arrancarlo al
     terminar el actual (cola de uno). El spec implementa el rechazo 409 por simplicidad.

5. **Historial**: en cancelacion, `_record` sigue escribiendo `status="cancelled"` con
   `duration_s` y `error="cancelado"`; no se toca.

## Technical decision

- **No se mata el proceso ni se usan threads**: `asyncio.Task.cancel()` es el mecanismo correcto;
  el problema es de granularidad y de feedback, no de "no detiene la tarea".
- **Guardado incremental** cambia el orden de escritura pero no el formato de `raw/NNNN.md`
  (`format_chapter` no cambia). Un capitulo vacio sigue reintentandose al final.
- La escritura por capitulo hace que un cancel deje un estado **parcial pero valido**: los
  ficheros existen y `chapters_downloaded` se recalcula al inicio del siguiente run.
- El lock es **por novela**, no global: dos novelas distintas pueden seguir descargandose en
  paralelo (comportamiento actual).
- Los jobs viven en memoria; un reinicio del servidor sigue perdiendolos. Persistirlos queda fuera
  de alcance (el estado real esta en `.manifest.json` y `raw/`).

## Affected files

- `src/novel_cli/web/jobs.py` — `JOB_CANCELLING`, `cancel()`, lock por URL/slug, liberacion.
- `src/novel_cli/web/routes.py` — respuesta de `cancel` y `409` en `POST /api/jobs`.
- `src/novel_cli/core/services/download.py` — escritura incremental + lock de escritura.
- `src/novel_cli/core/services/pipeline.py` — checkpoints entre fases (opcional/defensivo).
- `tests/test_web.py` — cancelacion, estado, 409, liberacion de lock.
- `tests/test_download.py` — cancelacion a mitad conserva ficheros.

## Tests

- `JobManager.cancel` deja `job.state == "cancelling"` inmediatamente y emite `status`.
- Cancelar un job en descarga (fetcher fake que espera) deja `state == "cancelled"` y conserva los
  `raw/*.md` ya escritos; los pendientes no se escriben.
- Cancelar un job ya terminado devuelve `False`/404.
- Dos `POST /api/jobs` con la misma URL: el segundo responde `409` con el `job_id` activo.
- Dos URLs distintas: ambos jobs se aceptan y corren.
- Tras terminar (done/error/cancelled), un nuevo job con la misma URL se acepta (lock liberado).
- `cancel` durante la fase de EPUB: el job termina de escribir el tomo actual y luego pasa a
  `cancelled` (test con un `build_epub` fake lento, opcional).

## Acceptance criteria

- [ ] `POST /api/jobs/{id}/cancel` marca el job como `cancelling`/`cancelled` de forma observable
      sin esperar a que termine la fase sincrona.
- [ ] Un cancel a mitad de descarga conserva los capitulos ya descargados.
- [ ] No puede haber dos jobs simultaneos escribiendo en la misma novela (409 o cola).
- [ ] El lock se libera en exito, error y cancelacion.
- [ ] El historial registra la cancelacion con duracion.
- [ ] Tests y lint en verde.
