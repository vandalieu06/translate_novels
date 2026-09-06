# 04 — Traducción: LibreTranslate, concurrencia y rate-limit

- Estado: implementado · Versión spec: 0.1.1

## Propósito

Backend de traducción intercambiable (Google gratuito | LibreTranslate local),
concurrencia real para `libre` y sin romperse por rate-limit en re-traducciones largas.

## Contexto / Problema

- Con Google, la concurrencia se fuerza a 1 (protección) y el pacer es 1500 ms.
- LibreTranslate por defecto limita a ~200 req/día/IP: una re-traducción de cientos de capítulos fallaba a mitad con 429.
- Los `translated/` vacíos (heredados de capítulos vacíos) impedían re-traducir.

## Cambio propuesto

- **Backend `libre`**: pacer 250 ms y concurrencia default 4; `effective_translate_concurrency` da `>= 1` para libre (tope 16) y fuerza 1 para google.
- **Rate-limit**: `LT_API_KEYS=local` en el compose + `NOVEL_TRANSLATE_API_KEY=local` en `.env` (con API key LibreTranslate omite el límite). Ver `06-infra.md`.
- **Stale/vacíos**: un `translated/<NNNN>.md` vacío no cuenta como traducido → se re-traduce si el raw se arregló, se limpia si sigue vacío (`translate_chapters` filtra capítulos vacíos y borra stale).
- **`--translate-pending`**: traduce solo pendientes sin descargar ni tocar el TOC (base del botón "Re-traducir").

## Decisión técnica

`translate_chapters` usa `asyncio.Semaphore(concurrency)` (patrón igual a la descarga); el Pacer/CooldownGate compartidos limitan el ritmo global.

## Archivos afectados

`core/services/translate.py`, `core/config.py`, `core/services/pipeline.py`, `cli/app.py` (`-tc`), `web/jobs.py`.

## Tests

Concurrencia por backend, chunking/reensamblado 1:1, retry/backoff 429, stale re-traducido/limpiado, load de `.env` (en `test_config.py`).

## Criterios de aceptación

- Con `libre` hay 4+ workers reales (verificado en el job actual).
- Una re-traducción larga no muere por 429 (API key activa).
- Un capítulo que estaba vacío y se arregló se re-traduce; si sigue vacío, su `translated/` vacío se limpia.