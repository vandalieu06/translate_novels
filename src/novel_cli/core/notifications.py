"""Notificaciones de estado (dominio puro).

Define el evento `NotificationEvent`, el `Protocol` `Notifier` y un
`NullNotifier` (no-op). El dominio no conoce el transporte: los adaptadores
(p. ej. Telegram) implementan `Notifier` en la capa de presentacion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class NotificationEvent:
    """Hito o fallo de una ejecucion del pipeline.

    ``kind`` identifica el momento (``scrape_done``, ``download_done``,
    ``epub_original_done``, ``translate_done``, ``epub_translated_done``,
    ``job_done``, ``job_error``). ``ok=False`` marca un fallo terminal.
    ``operation`` es el tipo de job (``download``, ``sync``, ``translate``,
    ``retranslate``) y ``data`` lleva los contadores/idioma de cada hito.
    """

    kind: str
    phase: str = ""
    title: str | None = None
    detail: str | None = None
    ok: bool = True
    operation: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


class Notifier(Protocol):
    """Canal de notificaciones; async y tolerante a fallos."""

    async def notify(self, event: NotificationEvent) -> None: ...

    async def aclose(self) -> None: ...


class NullNotifier:
    """Notifier desactivado: no hace nada."""

    async def notify(self, event: NotificationEvent) -> None:
        return None

    async def aclose(self) -> None:
        return None
