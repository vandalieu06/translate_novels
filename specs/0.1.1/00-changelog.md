# 00 — Changelog (0.1.0 → 0.1.1)

Cambios introducidos desde las specs base `0.1.0`. Cada entrada indica qué,
por qué, archivos afectados y estado. Formato estándar de spec de feature:
ver `01-web.md` … `08-roadmap.md`.

| # | Cambio | Por qué | Estado | Commit |
|---|--------|---------|--------|--------|
| 1 | **Control de capítulos vacíos**: detección (`is_chapter_empty`), reintentos al final del lote con backoff, `chapters_empty`/`chapters_empty_nums` en manifest, avisos en CLI/web, archivos vacíos que no cuentan como descargados y se re-descargan. | El parser devolvía 0 párrafos en algunos capítulos y se escribían archivos vacíos que contaban como "descargados" y nunca se reintentaban. | implementado | — |
| 2 | **Traducción de stale/vacíos**: un `translated/<NNNN>.md` vacío no cuenta como traducido (se re-traduce si el raw se arregló, se limpia si sigue vacío); los capítulos vacíos no se traducen ni se marcan. | Tras arreglar el raw, los `translated/` vacíos impedían re-traducir; los EPUBs traducidos incluían capítulos en blanco. | implementado | — |
| 3 | **EPUB: placeholders EN/ES + tomos alineados**: capítulos sin contenido llevan aviso en vez de salir en blanco; la partición del EPUB traducido es idéntica a la del original. | Coherencia y "50 cap/tomo" aunque falten capítulos. | implementado | — |
| 4 | **EPUB: regeneración en flujos de traducción**: `_generate_epubs(rebuild=True)` reescribe los ES existentes; `_cleanup_orphan_epubs` borra EPUBs fuera del manifest. | "Re-traducir"/sync no regeneraban los EPUBs ES (quedaban desactualizados). | implementado | — |
| 5 | **`rebuild_volumes` + cambio de tamaño de tomo**: reconstruye EPUBs desde el disco con un nuevo tamaño (50/100/150/200/ALL) sin red; modal en la web. | Necesidad de re-volumizar sin re-descargar ni re-traducir. | implementado | — |
| 6 | **Job lock en el servidor**: la UI consulta `GET /api/jobs` (pending/running) en vez del estado local; limpieza de `currentJobId`; fix CSS del `hidden`. | Tras terminar un job la UI seguía bloqueando "Lanzar descarga" por estado local obsoleto. | implementado | — |
| 7 | **Backend LibreTranslate**: backend `libre`, pacer 250 ms, concurrencia 4 por defecto, `effective_translate_concurrency` (google fuerza 1). | Evitar el endpoint gratuito y acelerar con motor local. | implementado | — |
| 8 | **Config vía `.env`**: `_load_dotenv` carga variables al arrancar; `translate_backend` expuesto en `/api/config` y badge en la UI. | Fijar la config sin exportar env en cada arranque. | implementado | — |
| 9 | **Rate-limit LibreTranslate**: `LT_API_KEYS=local` + `NOVEL_TRANSLATE_API_KEY=local` (con key se omite el límite de 200 req/día/IP). | El límite por defecto rompía re-traducciones largas con 429. | implementado | — |
| 10 | **CUDA**: `docker-compose.cuda.yaml` (imagen `latest-cuda`, GPU NVIDIA, `sudo docker compose`) + fix DNS (MagicDNS de Tailscale inalcanzable → `dns: 8.8.8.8/1.1.1.1`). | Acelerar la traducción con la GPU local. | implementado | — |

## Formato de spec de feature

```
# NN — <Nombre>
- Estado: propuesto | en desarrollo | implementado | aceptado
- Versión spec: <0.1.1> · Fecha: <...> · Relacionado: <0.1.0/....md si aplica>

## Propósito
## Contexto / Problema
## Cambio propuesto (antes → después)
## Decisión técnica
## Archivos afectados
## Tests
## Criterios de aceptación (Done cuando)
```