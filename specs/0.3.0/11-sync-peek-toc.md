---
code: "11"
title: "El Sync de la web hace siempre el peek del TOC (detecta novedades con cache fresca)"
project: "novel_cli"
status: completed
version: "0.3.0"
date: 2026-10-17
tags: [spec, sdd, web, scraper]
affected_files:
  - src/novel_cli/core/services/pipeline.py
  - src/novel_cli/web/jobs.py
  - src/novel_cli/web/routes.py
  - tests/test_toc_cache.py
  - tests/test_web.py
---

# 11 — El Sync de la web hace siempre el peek del TOC (detecta novedades con cache fresca)

## Purpose

Que el boton **Actualizar / Sync** de la ficha detecte capitulos nuevos aunque
la cache del TOC (`.toc.json`) siga dentro de su TTL, gastando el **minimo de
peticiones** (un *peek* de 2 paginas; el crawl completo solo si hay novedades).

## Context

`_resolve_toc` reutiliza la cache **sin ninguna peticion** mientras su edad sea
menor que `NOVEL_TOC_TTL_HOURS` (default **6 h**); solo hace el *peek* cuando la
cache ha caducado. El Sync de la web no forzaba nada, asi que con la cache
fresca seguia con el indice viejo.

Reproducido con `agent-browser` sobre una copia real
(`my-step-daughters-are-the-villainesses`; el sitio tiene 257 capitulos y la
cache tenia 100 con ~20 min): pulsar **Actualizar** terminaba "Listo" pero el
manifest no cambiaba y solo existia el tomo **1-100**.

Restriccion de diseno: el usuario pidio minimizar peticiones para no arriesgar
un baneo de IP. El coste real de un Sync es: 2 peticiones del peek (+N de crawl
solo si hay novedades), y las descargas/traducciones ya estan acotadas por
`volume_size` y con pacer. Por eso se descarta `refresh_toc` (que siempre hace
crawl completo) en favor del peek.

## Proposed change (antes → despues)

- **Antes**: Sync → `refresh_toc=False` → con cache fresca no consulta nada.
- **Despues**: se anade `peek_toc` al pipeline y el Sync de la web lo activa:
  - `peek_toc=True` salta el atajo de cache fresca y va directo al **peek**
    (`toc_changed`): 2 peticiones. Si no hay novedades, reutiliza la cache
    (la "toca"). Si las hay, hace el **crawl completo** y actualiza `.toc.json`.

## Technical decision

- `run_pipeline(..., peek_toc=False)` → `_resolve_toc(..., peek_toc=False)`:
  - condicion de atajo `age <= ttl and not peek_toc`;
  - el resto (peek → crawl) ya existia.
- `web/jobs.py` mapea `peek_toc` desde las opciones; `routes.py::sync_novel` lo
  pone en `True`. El CLI y la descarga normal conservan el TTL (y siguen
  disponibles `--refresh-toc`/`novel-cli toc`).
- Coste: **2 peticiones** por Sync en el caso normal; ~N (paginas del listado)
  solo cuando hay capitulos nuevos. Ninguna ruta lanza "miles" de peticiones:
  las descargas van de `volume_size` en `volume_size`.

## Affected files

- `src/novel_cli/core/services/pipeline.py` — parametro `peek_toc` en
  `run_pipeline` y `_resolve_toc`.
- `src/novel_cli/web/jobs.py` — `peek_toc=bool(options.get("peek_toc"))`.
- `src/novel_cli/web/routes.py` — `sync_novel`: `"peek_toc": True`.
- `tests/test_toc_cache.py` — peek con cache fresca (con y sin novedades).
- `tests/test_web.py` — el Sync crea el job con `peek_toc=True`.

## Tests

- `test_resolve_toc_peek_toc_bypasses_fresh_cache`: cache fresca + novedades →
  `crawled=True` y todos los capitulos.
- `test_resolve_toc_peek_toc_no_news_uses_cache`: cache fresca sin novedades →
  `crawled=False` y solo 2 fetches (el peek).
- `test_sync_novel_creates_job`: `captured["peek_toc"] is True`.

## Acceptance criteria

- `POST /api/novels/{slug}/sync` crea el job con `peek_toc=True`.
- Con cache fresca de 100 y 257 en el sitio, **Actualizar** hace el peek,
  re-escanea el TOC, descarga los 201-257 y regenera los tomos **1-100, 101-200
  y 201-257** (original y traducido). Verificado end-to-end con `agent-browser`:
  `total 257 / downloaded 257 / translated 257` y 6 EPUBs.
- `uv run pytest -q` y `uv run ruff check .` pasan.
