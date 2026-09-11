# 01 — Notificaciones por Telegram

- Estado: implementado
- Versión spec: 0.2.0 · Fecha: 2026-09-11 · Relacionado: 0.1.2/00-changelog.md

## Propósito

Avisar por Telegram del resultado de cada sync/descarga: scrape completado,
EPUB generados, traducción a `<LANG>` completada con sus EPUB, errores y
"Sync de `<NOVEL>` completado", para no tener que vigilar la web.

## Contexto / Problema

Hoy el estado solo se ve en la terminal (CLI con `rich`) o en la web (job +
WebSocket). El usuario debe quedarse pendiente de la UI para saber si un proceso
largo terminó o falló. El pipeline ya es async y publica eventos vía callbacks
(`on_status` / `on_progress`), y la web ejecuta `run_pipeline` en el event loop
de Uvicorn, por lo que añadir un notifier async es directo.

## Cambio propuesto (antes → después)

**Antes**: al terminar un job solo queda el estado en la web / salida de la CLI.

**Después**: con un bot configurado, cada ejecución (CLI o web) envía por
Telegram:
- **Un resumen** al terminar el job: scrape, capítulos descargados (y vacíos),
  tomos EPUB originales, traducción a `<LANG>` y sus tomos.
- **Un aviso inmediato** si el pipeline falla, con la fase y el detalle.

Sin config, el comportamiento es idéntico al actual (`NullNotifier`).

### Formato

Mensaje en **HTML** (`parse_mode`), con la operación y la duración del job;
título y detalle del error escapados:

```
✅ Renacido como el Héroe
Sync completado · 2m 14s

📥 Descarga: 50/512 capítulos ⚠️ 2 vacíos
📚 EPUB original: 1 tomo
🌐 Traducción ES: 50 capítulos
📗 EPUB ES: 1 tomo
```

Re-traducción sin capítulos pendientes (duración real, no <1 s de EPUB):

```
✅ Renacido como el Héroe
Re-traducción completada · 2m 37s

🌐 Traducción ES: sin cambios (total 1000)
📗 EPUB ES: 10 tomos
```

```
❌ Error en descarga — Renacido
HTTP 429 tras 3 reintentos
tras 12s
```

## Decisión técnica

- **Dominio puro**: `core/notifications.py` define `NotificationEvent`
  (`@dataclass`) y el `Protocol` `Notifier` (`notify()` / `aclose()`), más
  `NullNotifier`. `core/` no importa `telegram`.
- **Adaptador**: `src/novel_cli/notifications/telegram.py` implementa
  `TelegramNotifier` con `telegram.Bot` de **python-telegram-bot** (async). Solo
  enviar mensajes: no se usa `Updater`/polling ni webhook.
- **Resumen por job**: el pipeline emite un `job_started` al inicio; el notifier
  acumula los hitos (eventos no terminales) y compone **un único mensaje** al
  recibir `job_done`; los `job_error` se envían de inmediato. El mensaje va en
  **HTML** con título en negrita e iconos por fase; título y detalle se escapan
  (evita inyección/errores de parseo) y se recortan al límite de Telegram. La
  duración se mide con `time.monotonic()` **de `job_started` al evento terminal**
  (incluye scrape y traducción; `<1s` si es sub-segundo).
- **Datos estructurados**: los hitos llevan contadores/idioma en `data`
  (`chapters_total`, `chapters_downloaded`, `chapters_empty`, `volumes`,
  `target`, `translated_new`, `translated_total`) y `operation`
  (`download`/`sync`/`translate`/`retranslate`) en el evento terminal; el
  adaptador los formatea (core no pre-formatea texto de presentación). La línea
  de traducción muestra `N capítulos` (si `new == total`), `N nuevos (total M)`
  o `sin cambios (total M)`.
- **Aislamiento de fallos**: todo envío va en `try/except`; un fallo de Telegram
  se registra y **nunca** interrumpe el pipeline.
- **Inyección**: `run_pipeline(..., notifier=None, operation=...)`; CLI
  (`cli/app.py`) y web (`web/jobs.py`, `web/routes.py`) construyen el notifier
  con `build_default_notifier()` y lo cierran en su `finally`. `/api/config`
  expone `telegram_enabled`.
- **Config** en `core/config.py`: `NOVEL_TELEGRAM_BOT_TOKEN`,
  `NOVEL_TELEGRAM_CHAT_ID` (un `chat_id`), `NOVEL_TELEGRAM_ENABLED` (default:
  activo si hay token y chat). Se cargan del `.env` existente.
- **Dependencias**: `python-telegram-bot>=21`; se acota `httpx` a `>=0.27,<0.29`
  (requisito de PTB; el venv ya tiene 0.28.1).

## Archivos afectados

- `src/novel_cli/core/notifications.py` (nuevo): evento, `Notifier`,
  `NullNotifier`.
- `src/novel_cli/notifications/__init__.py` (nuevo) y
  `src/novel_cli/notifications/telegram.py` (nuevo): adaptador + factory.
- `src/novel_cli/core/config.py`: variables de entorno del bot.
- `src/novel_cli/core/services/pipeline.py`: parámetro `notifier`/`operation` y
  emisión de eventos (hitos con `data` + `job_done` / `job_error`).
- `src/novel_cli/cli/app.py`: construye/inyecta/cierra el notifier.
- `src/novel_cli/web/jobs.py`: construye/inyecta/cierra el notifier y reenvía
  `operation`.
- `src/novel_cli/web/routes.py`: `operation` en los jobs de sync/retranslate.
- `src/novel_cli/web/app.py`: `telegram_enabled` en `/api/config`.
- `pyproject.toml`: `python-telegram-bot` + pin `httpx`.
- `tests/test_notify.py` (nuevo).
- `docs/features.md`, `docs/arquitectura.md`, `docs/uso.md`.

## Tests

- `tests/test_notify.py` (sin red):
  - `FakeNotifier` captura eventos; `run_pipeline` emite `job_started`,
    `scrape_done`, `download_done`, `epub_original_done`, `translate_done`,
    `epub_translated_done` y `job_done`, con `data`/`operation` correctos.
  - `job_error` se emite con detalle y `operation` cuando el pipeline falla (y el
    error se re-lanza).
  - Duración medida de `job_started` a `job_done` con reloj falso.
  - `_render_summary`/`_render_error`: con/sin traducción, pluralización,
    vacíos, `translated_new`/`translated_total`, escape HTML y recorte del
    detalle largo.
  - `_format_duration` (incl. `<1s`)/`_operation_label`; `send_message` con
    `parse_mode=HTML`.
  - `build_default_notifier` devuelve `NullNotifier` sin env y `TelegramNotifier`
    con token+chat; `telegram_enabled` en `/api/config`.
- `uv run ruff check .` y `uv run pytest -q` en verde.

## Criterios de aceptación

- Con `NOVEL_TELEGRAM_BOT_TOKEN` y `NOVEL_TELEGRAM_CHAT_ID` definidos, una
  ejecución de CLI o un job web envía **un resumen** al terminar y **un aviso**
  si falla.
- Sin esas variables, el comportamiento es el actual (no-op).
- Un error de Telegram no afecta al resultado del pipeline.
- La suite de tests y `ruff` pasan sin tocar la red.
