"""Notificador por Telegram usando python-telegram-bot (solo envio).

No usa ``Updater``/polling: basta ``telegram.Bot.send_message``. Acumula los
hitos de un job y envia **un resumen** en HTML al recibir ``job_done``; los
errores se avisan de inmediato. Cualquier fallo de Telegram se registra y se
ignora para no romper el pipeline.
"""

from __future__ import annotations

import html
import logging
import time
from typing import Any

from telegram import Bot
from telegram.constants import ParseMode

from novel_cli.core.notifications import NotificationEvent

logger = logging.getLogger(__name__)

_MAX_TITLE = 120
_MAX_DETAIL = 800

_OPERATION_LABELS = {
    "download": "Descarga completada",
    "sync": "Sync completado",
    "translate": "Traducción completada",
    "retranslate": "Re-traducción completada",
}


def _esc(text: str) -> str:
    """Escapa el texto dinamico para el parse_mode HTML de Telegram."""
    return html.escape(text, quote=False)


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def _format_duration(seconds: float) -> str:
    if seconds < 1:
        return "<1s"
    total = int(round(seconds))
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m"


def _operation_label(operation: str | None) -> str:
    return _OPERATION_LABELS.get(operation or "download", "Proceso completado")


def _render_summary(
    events: list[NotificationEvent], title: str | None, duration: float
) -> str:
    """Resumen HTML de un job a partir de los hitos acumulados."""
    operation: str | None = None
    data: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.operation:
            operation = event.operation
        data[event.kind] = event.data

    heading = (
        f"✅ <b>{_esc(_clip(title, _MAX_TITLE))}</b>" if title else "✅ Proceso completado"
    )
    label = _esc(_operation_label(operation))
    subtitle = f"<code>{label} · {_esc(_format_duration(duration))}</code>"

    lines: list[str] = []
    downloaded = data.get("download_done", {}).get("chapters_downloaded")
    if downloaded is not None:
        total = data.get("scrape_done", {}).get("chapters_total")
        empty = data.get("download_done", {}).get("chapters_empty", 0) or 0
        suffix = f" ⚠️ {empty} vacíos" if empty else ""
        range_txt = f"{downloaded}/{total}" if total else f"{downloaded}"
        lines.append(f"📥 Descarga: {range_txt} capítulos{suffix}")

    volumes = data.get("epub_original_done", {}).get("volumes")
    if volumes is not None:
        lines.append(f"📚 EPUB original: {_plural(volumes, 'tomo', 'tomos')}")

    translated_total = data.get("translate_done", {}).get("translated_total")
    translated_new = data.get("translate_done", {}).get("translated_new")
    target = data.get("translate_done", {}).get("target")
    if translated_total is not None:
        lang = (target or "").upper() or "?"
        if translated_new is None:
            count = _plural(translated_total, "capítulo", "capítulos")
        elif translated_new == 0:
            count = f"sin cambios (total {translated_total})"
        elif translated_new == translated_total:
            count = _plural(translated_new, "capítulo", "capítulos")
        else:
            count = f"{translated_new} nuevos (total {translated_total})"
        lines.append(f"🌐 Traducción {lang}: {count}")

    volumes_es = data.get("epub_translated_done", {}).get("volumes")
    if volumes_es is not None:
        lang = (target or "").upper() or "?"
        lines.append(f"📗 EPUB {lang}: {_plural(volumes_es, 'tomo', 'tomos')}")

    if not lines:
        lines = ["Proceso finalizado."]

    return "\n".join([heading, subtitle, "", *lines])


def _render_error(event: NotificationEvent, title: str | None, duration: float) -> str:
    """Aviso inmediato de fallo, con la fase, el titulo y la duracion."""
    heading = f"❌ <b>Error en {_esc(event.phase or 'el pipeline')}</b>"
    if title:
        heading += f" — {_esc(_clip(title, _MAX_TITLE))}"
    detail = _clip(event.detail or "", _MAX_DETAIL)
    parts = [heading]
    if detail:
        parts.append(f"<code>{_esc(detail)}</code>")
    parts.append(f"<i>tras {_esc(_format_duration(duration))}</i>")
    return "\n".join(parts)


class TelegramNotifier:
    """Implementa ``Notifier`` enviando mensajes a un ``chat_id``."""

    def __init__(self, *, token: str, chat_id: str, bot: Bot | None = None):
        self._token = token
        self._chat_id = chat_id
        self._bot = bot
        self._events: list[NotificationEvent] = []
        self._title: str | None = None
        self._started: float | None = None

    async def notify(self, event: NotificationEvent) -> None:
        now = time.monotonic()
        if event.kind == "job_started":
            self._started = now
            if event.title:
                self._title = event.title
            return
        if self._started is None:
            self._started = now
        if event.title:
            self._title = event.title
        if event.ok:
            self._events.append(event)
            if event.kind == "job_done":
                text = _render_summary(
                    self._events, event.title or self._title, now - self._started
                )
                await self._send(text)
                self._events.clear()
            return
        await self._send(_render_error(event, self._title, now - self._started))

    async def _send(self, text: str) -> None:
        try:
            bot = await self._get_bot()
            await bot.send_message(
                chat_id=self._chat_id, text=text, parse_mode=ParseMode.HTML
            )
        except Exception:  # noqa: BLE001 - la notificacion nunca rompe el pipeline
            logger.exception("no se pudo enviar la notificacion de Telegram")

    async def _get_bot(self) -> Bot:
        if self._bot is None:
            self._bot = Bot(token=self._token)
            await self._bot.initialize()
        return self._bot

    async def aclose(self) -> None:
        if self._bot is None:
            return
        try:
            await self._bot.shutdown()
        except Exception:  # noqa: BLE001 - cierre best-effort
            logger.exception("error cerrando el bot de Telegram")
        finally:
            self._bot = None
