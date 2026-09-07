# Specs (plan por versión)

Los specs definen el **contrato/plan** de cada versión. `docs/` es la referencia
autoritativa del **estado actual**; `specs/` registra qué se planeó y qué cambió
en cada versión.

## Versiones

| Versión | Contenido |
|---|---|
| [`0.1.0/`](0.1.0/) | Specs base: plan original del CLI (scrape → download → epub → translate → manifest), antes de la web. |
| [`0.1.1/`](0.1.1/) | Cambios introducidos desde 0.1.0: capa web completa, control de capítulos vacíos, EPUBs con placeholders/rebuild, cambio de tamaño de tomo, backend LibreTranslate (rate-limit + CUDA) y config vía `.env`. |
| [`0.1.2/`](0.1.2/) | Cambios introducidos desde 0.1.1: web multi-página — biblioteca por portadas (`/biblioteca`), ficha individual (`/novela/{slug}`) y guía de acciones (`/ayuda`); refactor de `app.js` en módulos compartidos; **traducción con idioma destino elegible** (botón "Traducir" en la ficha + selector en descarga + `--target` en CLI). |

## Workflow (specs-driven)

Antes de escribir código de una feature/fix, se documenta en un spec de la
versión en curso siguiendo el formato estándar (ver `0.1.1/00-changelog.md` y
el `AGENTS.md`). Al cerrar un conjunto de cambios se bumpa la versión de specs.