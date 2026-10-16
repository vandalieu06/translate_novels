---
code: "09"
title: "Arreglar la notificacion Telegram cuando la duracion es menor de 1s"
project: "novel_cli"
status: completed
version: "0.3.0"
date: 2026-10-17
tags: [spec, sdd, notify]
affected_files:
  - src/novel_cli/notifications/telegram.py
  - tests/test_notify.py
---

# 09 — Arreglar la notificacion Telegram cuando la duracion es menor de 1s

## Purpose

Corregir el fallo al enviar el resumen por Telegram cuando un job dura menos de
1 segundo (`telegram.error.BadRequest: Can't parse entities: unsupported start
tag "1s</code"`), de forma que el aviso llegue siempre.

## Context

`_format_duration()` (`telegram.py`) devuelve el literal `"<1s"` para duraciones
menores de 1 s. Ese texto se inserta **sin escapar** dentro del HTML del mensaje:

- resumen: `f"<code>{label} · {_format_duration(duration)}</code>"` → produce
  `<code>Sync completado · <1s</code>`;
- error: `f"<i>tras {_format_duration(duration)}</i>"` → `<i>tras <1s</i>`.

Telegram interpreta `<1s` como etiqueta de apertura y rechaza el mensaje. Un
`sync` sin capítulos nuevos termina en menos de 1 s, así que el resumen falla de
forma sistemática en ese caso. `_send()` captura la excepción y solo la registra
(el pipeline no se rompe), pero el usuario **no recibe la notificación**.

Las pruebas existentes afirman el contrato de `_format_duration(0) == "<1s"` pero
ninguna valida que el HTML resultante sea parseable por Telegram.

## Proposed change (antes → despues)

- **Antes**: `_format_duration(duration)` se inserta crudo en el HTML → `<1s`
  rompe `ParseMode.HTML`.
- **Despues**: se escapa en el punto de inserción con el helper existente
  `_esc(...)`, tanto en el resumen como en el aviso de error:
  - `<code>{label} · {_esc(_format_duration(duration))}</code>` → `&lt;1s`
  - `<i>tras {_esc(_format_duration(duration))}</i>` → `&lt;1s`.
  `_format_duration` **no cambia** (mantiene su contrato y sus tests).

## Technical decision

- Escapar en la inserción (no cambiar `_format_duration`) para no romper su
  contrato ni los tests existentes, y porque el problema es de contexto HTML, no
  del valor.
- Telegram admite `&lt;` en `ParseMode.HTML`, así que se muestra "<1s" correcto.
- Alternativa descartada: cambiar el texto a "0s" o "menos de 1s" (perdería
  precisión y es más invasivo).

## Affected files

- `src/novel_cli/notifications/telegram.py` — `_render_summary` (linea del
  `subtitle`) y `_render_error` (linea del `tras …`).
- `tests/test_notify.py` — pruebas del escapado.

## Tests

- Nuevo: `_render_summary(events, "Novela", 0)` contiene `"&lt;1s"` y **no**
  contiene `"<1s"`.
- Nuevo: `_render_error(event, "Novela", 0.4)` contiene `"&lt;1s"` y **no**
  `"<1s"`.
- Se mantiene `test_format_duration` (el contrato de `_format_duration` no
  cambia).

## Acceptance criteria

- Un resumen o aviso con duración < 1 s produce HTML válido para Telegram (sin
  ningún `<1s` sin escapar) y se muestra "<1s".
- `uv run pytest -q` y `uv run ruff check .` pasan.
