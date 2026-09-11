"""Adaptadores de notificacion (capa de presentacion).

`core.notifications` define el contrato puro; aqui viven las implementaciones
concretas. `build_default_notifier` crea el notifier segun la config (Telegram)
o un `NullNotifier` si no esta configurado.
"""

from __future__ import annotations

from novel_cli.core import config
from novel_cli.core.notifications import (
    NotificationEvent,
    Notifier,
    NullNotifier,
)

__all__ = [
    "NotificationEvent",
    "Notifier",
    "NullNotifier",
    "build_default_notifier",
]


def build_default_notifier() -> Notifier:
    """Notifier de Telegram si hay token+chat; si no, uno desactivado."""
    if not config.telegram_enabled():
        return NullNotifier()
    from novel_cli.notifications.telegram import TelegramNotifier

    return TelegramNotifier(
        token=config.telegram_bot_token() or "",
        chat_id=config.telegram_chat_id() or "",
    )
