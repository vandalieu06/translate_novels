# 00 — Changelog (0.1.2 → 0.2.0)

Cambios introducidos desde las specs `0.1.2`. Cada entrada indica qué, por qué,
archivos afectados y estado. Formato estándar de spec de feature: ver
`01-notifications.md`.

| # | Cambio | Por qué | Estado | Commit |
|---|--------|---------|--------|--------|
| 1 | **Notificaciones por Telegram**: `Notifier` (Protocol) + `NotificationEvent` en `core/notifications.py`; adaptador `TelegramNotifier` (python-telegram-bot) que resume cada job y avisa errores; inyección en el pipeline desde CLI y web; config por `.env` (`NOVEL_TELEGRAM_BOT_TOKEN`, `NOVEL_TELEGRAM_CHAT_ID`). | No haber que vigilar la web para saber si un sync/descarga/traducción terminó o falló. | implementado | — |

## Formato de spec de feature

```
# NN — <Nombre>
- Estado: propuesto | en desarrollo | implementado | aceptado
- Versión spec: <0.2.0> · Fecha: <...> · Relacionado: <0.1.2/....md si aplica>

## Propósito
## Contexto / Problema
## Cambio propuesto (antes → después)
## Decisión técnica
## Archivos afectados
## Tests
## Criterios de aceptación
```
