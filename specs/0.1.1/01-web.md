# 01 — Web (FastAPI + UI)

- Estado: implementado · Versión spec: 0.1.1 · Relacionado: 0.1.0 (la web estaba fuera de alcance v1)

## Propósito

Dar control de novel-cli desde el navegador (móvil/tablet/PC) sin SSH: lanzar
descargas, seguir el progreso en vivo, sync, re-traducir, cambiar tamaño de
tomo y descargar EPUBs.

## Contexto / Problema

0.1.0 era solo CLI. La web reutiliza `core` tal cual (capa de presentación pura).

## Cambio propuesto

- `web/app.py`: `create_app()` FastAPI + auth opcional (`NOVEL_WEB_TOKEN`), UI servida por el propio backend, `GET /api/config` (incluye `translate_backend`).
- `web/jobs.py`: `JobManager` corre `run_pipeline` como background task (un job activo a la vez) con eventos.
- `web/routes.py`: API REST — `GET/POST /api/jobs`, `GET /api/jobs/{id}`, cancel, `GET /api/novels`, EPUB/cover, `POST /novels/{slug}/sync`, `POST /novels/{slug}/retranslate`, `POST /novels/{slug}/volume-size`.
- `web/ws.py`: WebSocket `/api/jobs/{id}/ws` para progreso en vivo.
- `web/static/*` + `web/templates/*`: UI vanilla (HTML/CSS/JS), modal de tomos (pills 50/100/150/200/ALL).
- **Job lock en servidor**: `hasActiveJob()` consulta `GET /api/jobs` (estados `pending`/`running`) en vez del estado local; `currentJobId` se limpia al terminar.

## Decisión técnica

`core` intacto; web inyecta fetcher/translator y callbacks de progreso. Tests mockean `web.jobs.run_pipeline`.

## Archivos afectados

`src/novel_cli/web/*`, `tests/test_web.py`, `docs/uso.md` (sección web).

## Tests

Rutas, validación, auth por token, jobs (crear/listar/estados), retranslate y volume-size (200/404/400).

## Criterios de aceptación

- Tras terminar un job, "Lanzar descarga"/"Sync" vuelven a funcionar.
- Re-traducir y cambiar tamaño de tomo regeneran los EPUBs y actualizan el manifest.