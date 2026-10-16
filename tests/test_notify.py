"""Unit tests de notificaciones (sin red): formato, factory y eventos del pipeline."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from telegram.constants import ParseMode

from novel_cli.core import config
from novel_cli.core.notifications import NotificationEvent, NullNotifier
from novel_cli.core.scraper.fetcher import Pacer
from novel_cli.core.scraper.sites.generic import GenericAdapter
from novel_cli.core.services.pipeline import PipelineError, run_pipeline
from novel_cli.notifications import build_default_notifier
from novel_cli.notifications.telegram import (
    TelegramNotifier,
    _format_duration,
    _operation_label,
    _render_error,
    _render_summary,
)
from novel_cli.web.app import create_app

NOVEL_URL = "https://readhere.example/eternal-journey"
CHAPTER_HTML = (
    "<html><body><article>"
    "<p>Hello there.</p><p>Goodbye now.</p>"
    "</article></body></html>"
)


class _FakeFetcher:
    def __init__(self, toc_html: str):
        self.toc_html = toc_html

    async def fetch_html(self, url: str, *, headers: dict | None = None) -> str:
        if url == NOVEL_URL:
            return self.toc_html
        return CHAPTER_HTML

    async def fetch_bytes(self, url: str, *, headers: dict | None = None) -> bytes:
        return b"fakecover"

    async def aclose(self) -> None:
        return None


class _FakeTranslator:
    async def translate_text(
        self, text: str, *, source: str = "auto", target: str = "es"
    ) -> str:
        return "\n".join(f"ES:{line}" for line in text.split("\n"))


class _FakeNotifier:
    def __init__(self) -> None:
        self.events: list[NotificationEvent] = []
        self.closed = False

    async def notify(self, event: NotificationEvent) -> None:
        self.events.append(event)

    async def aclose(self) -> None:
        self.closed = True


class _BrokenNotifier:
    async def notify(self, event: NotificationEvent) -> None:
        raise RuntimeError("telegram caido")

    async def aclose(self) -> None:
        return None


class _FakeBot:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)


def _run_kwargs(
    tmp_path, fetcher, *, translate, translator, notifier, operation="download"
):
    return {
        "url": NOVEL_URL,
        "output_dir": tmp_path,
        "volume_size": None,
        "translate": translate,
        "resume": True,
        "force": False,
        "concurrency": 2,
        "fetcher": fetcher,
        "adapter": GenericAdapter(),
        "translator": translator,
        "pacer": Pacer(0),
        "notifier": notifier,
        "operation": operation,
    }


def _ev(kind, *, data=None, operation=None, phase="", title="Novela", detail=None, ok=True):
    return NotificationEvent(
        kind=kind,
        phase=phase,
        title=title,
        detail=detail,
        ok=ok,
        operation=operation,
        data=data or {},
    )


def _translated_events(operation="sync"):
    return [
        _ev("scrape_done", data={"chapters_total": 4}),
        _ev("download_done", data={"chapters_downloaded": 4, "chapters_empty": 0}),
        _ev("epub_original_done", data={"volumes": 1}),
        _ev(
            "translate_done",
            data={"target": "es", "translated_new": 4, "translated_total": 4},
        ),
        _ev("epub_translated_done", data={"target": "es", "volumes": 1}),
        _ev("job_done", operation=operation),
    ]


# --- Formato: resumen ------------------------------------------------------


def test_render_summary_full():
    text = _render_summary(_translated_events(), "Novela", 134)
    assert text.startswith("✅ <b>Novela</b>")
    assert "<code>Sync completado · 2m 14s</code>" in text
    assert "📥 Descarga: 4/4 capítulos" in text
    assert "📚 EPUB original: 1 tomo" in text
    assert "🌐 Traducción ES: 4 capítulos" in text
    assert "📗 EPUB ES: 1 tomo" in text


def test_render_summary_without_translate():
    events = [
        _ev("scrape_done", data={"chapters_total": 50}),
        _ev("download_done", data={"chapters_downloaded": 50, "chapters_empty": 0}),
        _ev("epub_original_done", data={"volumes": 1}),
        _ev("job_done", operation="download"),
    ]
    text = _render_summary(events, "Novela", 42)
    assert "Descarga completada · 42s" in text
    assert "🌐 Traducción" not in text
    assert "📗 EPUB" not in text


def test_render_summary_pluralizes_and_warns_empty():
    events = [
        _ev("scrape_done", data={"chapters_total": 100}),
        _ev("download_done", data={"chapters_downloaded": 100, "chapters_empty": 3}),
        _ev("epub_original_done", data={"volumes": 2}),
        _ev("job_done", operation="sync"),
    ]
    text = _render_summary(events, "Novela", 60)
    assert "📥 Descarga: 100/100 capítulos ⚠️ 3 vacíos" in text
    assert "📚 EPUB original: 2 tomos" in text


def test_render_summary_without_title_or_events():
    text = _render_summary([], None, 0)
    assert text.startswith("✅ Proceso completado")
    assert "Proceso finalizado." in text


def test_render_summary_escapes_dynamic_content():
    events = [_ev("job_done", operation="sync")]
    text = _render_summary(events, "A <b> B & C", 1)
    assert "A &lt;b&gt; B &amp; C" in text


def test_render_summary_escapes_short_duration():
    """Una duracion <1s no debe introducir un '<' crudo (rompe el HTML Telegram)."""
    text = _render_summary([_ev("job_done", operation="sync")], "Novela", 0)
    assert "&lt;1s" in text
    assert "<1s" not in text


# --- Formato: error --------------------------------------------------------


def test_render_error_full():
    event = _ev("job_error", ok=False, phase="descarga", detail="timeout <x>")
    text = _render_error(event, "Novela", 5)
    assert text.startswith("❌ <b>Error en descarga</b> — Novela")
    assert "<code>timeout &lt;x&gt;</code>" in text
    assert "<i>tras 5s</i>" in text


def test_render_error_without_title():
    event = _ev("job_error", ok=False, phase="traduccion", detail="boom", title=None)
    text = _render_error(event, None, 30)
    assert text.startswith("❌ <b>Error en traduccion</b>")
    assert "—" not in text.splitlines()[0]


def test_render_error_clips_long_detail():
    event = _ev("job_error", ok=False, phase="descarga", detail="a" * 2000)
    text = _render_error(event, "Novela", 1)
    assert "…" in text


def test_render_error_escapes_short_duration():
    event = _ev("job_error", ok=False, phase="descarga", detail="boom")
    text = _render_error(event, "Novela", 0.4)
    assert "&lt;1s" in text
    assert "<1s" not in text


# --- Helpers de formato ----------------------------------------------------


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "<1s"),
        (0.4, "<1s"),
        (1, "1s"),
        (45, "45s"),
        (134, "2m 14s"),
        (3725, "1h 2m"),
    ],
)
def test_format_duration(seconds, expected):
    assert _format_duration(seconds) == expected


def test_render_summary_translation_new_vs_total():
    def summary(new, total):
        events = [
            _ev("scrape_done", data={"chapters_total": total}),
            _ev("download_done", data={"chapters_downloaded": 0, "chapters_empty": 0}),
            _ev(
                "translate_done",
                data={"target": "es", "translated_new": new, "translated_total": total},
            ),
            _ev("job_done", operation="retranslate"),
        ]
        return _render_summary(events, "Novela", 5)

    assert "🌐 Traducción ES: sin cambios (total 1000)" in summary(0, 1000)
    assert "🌐 Traducción ES: 2 nuevos (total 1000)" in summary(2, 1000)
    assert "🌐 Traducción ES: 1000 capítulos" in summary(1000, 1000)


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        ("download", "Descarga completada"),
        ("sync", "Sync completado"),
        ("translate", "Traducción completada"),
        ("retranslate", "Re-traducción completada"),
        (None, "Descarga completada"),
        ("desconocida", "Proceso completado"),
    ],
)
def test_operation_label(operation, expected):
    assert _operation_label(operation) == expected


# --- Config / factory ------------------------------------------------------


def test_telegram_disabled_without_env(monkeypatch):
    monkeypatch.delenv("NOVEL_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("NOVEL_TELEGRAM_CHAT_ID", raising=False)
    assert config.telegram_enabled() is False
    assert isinstance(build_default_notifier(), NullNotifier)


def test_telegram_enabled_with_token_and_chat(monkeypatch):
    monkeypatch.setenv("NOVEL_TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("NOVEL_TELEGRAM_CHAT_ID", "42")
    monkeypatch.delenv("NOVEL_TELEGRAM_ENABLED", raising=False)
    assert config.telegram_enabled() is True
    assert isinstance(build_default_notifier(), TelegramNotifier)


def test_telegram_can_be_disabled_explicitly(monkeypatch):
    monkeypatch.setenv("NOVEL_TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("NOVEL_TELEGRAM_CHAT_ID", "42")
    monkeypatch.setenv("NOVEL_TELEGRAM_ENABLED", "off")
    assert config.telegram_enabled() is False


def test_config_endpoint_exposes_telegram_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("NOVEL_TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("NOVEL_TELEGRAM_CHAT_ID", "42")
    client = TestClient(create_app(output_dir=tmp_path))
    assert client.get("/api/config").json()["telegram_enabled"] is True


# --- Eventos del pipeline --------------------------------------------------


@pytest.mark.asyncio
async def test_pipeline_emits_milestones_and_done(tmp_path, fixture_loader):
    notifier = _FakeNotifier()
    await run_pipeline(
        **_run_kwargs(
            tmp_path,
            _FakeFetcher(fixture_loader("generic_toc.html")),
            translate=True,
            translator=_FakeTranslator(),
            notifier=notifier,
            operation="sync",
        )
    )
    events = notifier.events
    assert [event.kind for event in events] == [
        "job_started",
        "scrape_done",
        "download_done",
        "epub_original_done",
        "translate_done",
        "epub_translated_done",
        "job_done",
    ]
    by_kind = {event.kind: event for event in events}
    assert by_kind["scrape_done"].data["chapters_total"] == 4
    assert by_kind["download_done"].data["chapters_downloaded"] == 4
    assert by_kind["translate_done"].data["target"] == "es"
    assert by_kind["translate_done"].data["translated_new"] == 4
    assert by_kind["translate_done"].data["translated_total"] == 4
    assert by_kind["epub_translated_done"].data["volumes"] == 1
    assert by_kind["job_done"].operation == "sync"


@pytest.mark.asyncio
async def test_pipeline_emits_error_and_reraises(tmp_path, fixture_loader):
    notifier = _FakeNotifier()
    with pytest.raises(PipelineError):
        await run_pipeline(
            **_run_kwargs(
                tmp_path,
                _FakeFetcher(fixture_loader("generic_no_toc.html")),
                translate=False,
                translator=None,
                notifier=notifier,
                operation="sync",
            )
        )
    assert [event.kind for event in notifier.events] == ["job_started", "job_error"]
    error = notifier.events[-1]
    assert error.kind == "job_error"
    assert error.ok is False
    assert error.phase == "epub/manifest"
    assert error.operation == "sync"


@pytest.mark.asyncio
async def test_broken_notifier_does_not_break_pipeline(tmp_path, fixture_loader):
    manifest = await run_pipeline(
        **_run_kwargs(
            tmp_path,
            _FakeFetcher(fixture_loader("generic_toc.html")),
            translate=False,
            translator=None,
            notifier=_BrokenNotifier(),
        )
    )
    assert manifest.slug == "the-eternal-journey"


# --- TelegramNotifier ------------------------------------------------------


def test_notifier_sends_one_html_summary():
    notifier = TelegramNotifier(token="tok", chat_id="1")
    sent: list[str] = []

    async def fake_send(text: str) -> None:
        sent.append(text)

    notifier._send = fake_send  # type: ignore[method-assign]

    async def drive() -> None:
        for event in _translated_events():
            await notifier.notify(event)

    asyncio.run(drive())
    assert len(sent) == 1
    assert "<b>Novela</b>" in sent[0]
    assert "📥 Descarga: 4/4 capítulos" in sent[0]


def test_send_uses_html_parse_mode():
    bot = _FakeBot()
    notifier = TelegramNotifier(token="tok", chat_id="1", bot=bot)  # type: ignore[arg-type]

    asyncio.run(notifier._send("hola"))

    assert len(bot.calls) == 1
    assert bot.calls[0]["chat_id"] == "1"
    assert bot.calls[0]["text"] == "hola"
    assert bot.calls[0]["parse_mode"] == ParseMode.HTML


def test_notifier_measures_duration_from_job_started(monkeypatch):
    import itertools

    ticks = itertools.count(100.0, 15.0)
    monkeypatch.setattr(
        "novel_cli.notifications.telegram.time.monotonic", lambda: next(ticks)
    )
    notifier = TelegramNotifier(token="tok", chat_id="1")
    sent: list[str] = []

    async def fake_send(text: str) -> None:
        sent.append(text)

    notifier._send = fake_send  # type: ignore[method-assign]

    async def drive() -> None:
        await notifier.notify(_ev("job_started", operation="sync"))
        await notifier.notify(
            _ev("download_done", data={"chapters_downloaded": 1, "chapters_empty": 0})
        )
        await notifier.notify(_ev("job_done", operation="sync"))

    asyncio.run(drive())
    assert len(sent) == 1
    assert "30s" in sent[0]
    assert "job_started" not in sent[0]


def test_render_summary_ignores_job_started():
    events = [_ev("job_started", operation="sync"), _ev("job_done", operation="sync")]
    text = _render_summary(events, "Novela", 3)
    assert "job_started" not in text
