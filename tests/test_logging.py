"""Unit tests de logging e historial (sin red)."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler

import pytest

from novel_cli.core.models.state import Manifest
from novel_cli.core.scraper.fetcher import FallbackFetcher, FetchError
from novel_cli.logging_setup import JOB_ID, _JobIdFilter, configure_logging
from novel_cli.run_history import RunRecord, append_run, record_from_manifest
from novel_cli.web.app import create_app

_LOG = "novel_cli"


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest.fixture(autouse=True)
def _clean_logging():
    yield
    logger = logging.getLogger(_LOG)
    for handler in list(logger.handlers):
        if getattr(handler, "_novel_cli", False):
            handler.close()
            logger.removeHandler(handler)
    logger.propagate = True


def _file_handler() -> RotatingFileHandler:
    handler = next(
        h
        for h in logging.getLogger(_LOG).handlers
        if isinstance(h, RotatingFileHandler)
    )
    return handler


def _flush() -> None:
    for handler in logging.getLogger(_LOG).handlers:
        handler.flush()


# --- configure_logging -----------------------------------------------------


def test_configure_logging_writes_file(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVEL_LOG_FILE", raising=False)
    monkeypatch.delenv("NOVEL_LOG_LEVEL", raising=False)
    monkeypatch.delenv("NOVEL_LOG_DIR", raising=False)
    path = configure_logging(output_dir=tmp_path, force=True)
    logging.getLogger("novel_cli.test").info("hola-log")
    _flush()
    assert path == tmp_path / "logs" / "novel-cli.log"
    assert "hola-log" in path.read_text(encoding="utf-8")


def test_configure_logging_is_idempotent(tmp_path):
    configure_logging(output_dir=tmp_path, force=True)
    before = len(logging.getLogger(_LOG).handlers)
    configure_logging(output_dir=tmp_path)
    assert len(logging.getLogger(_LOG).handlers) == before


def test_configure_logging_verbose_debug(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVEL_LOG_LEVEL", raising=False)
    configure_logging(output_dir=tmp_path, verbose=True, force=True)
    assert _file_handler().level == logging.DEBUG


def test_configure_logging_env_level(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVEL_LOG_LEVEL", "ERROR")
    configure_logging(output_dir=tmp_path, force=True)
    assert _file_handler().level == logging.ERROR


def test_configure_logging_rotation(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVEL_LOG_MAX_BYTES", "123")
    monkeypatch.setenv("NOVEL_LOG_BACKUPS", "2")
    configure_logging(output_dir=tmp_path, force=True)
    handler = _file_handler()
    assert handler.maxBytes == 123
    assert handler.backupCount == 2


def test_job_id_filter_injects_context():
    JOB_ID.set("job-123")
    try:
        record = logging.LogRecord("x", logging.INFO, "p", 1, "m", None, None)
        assert _JobIdFilter().filter(record) is True
        assert record.job_id == "job-123"
    finally:
        JOB_ID.set("-")


# --- Historial -------------------------------------------------------------


def test_append_run_writes_jsonl(tmp_path, monkeypatch):
    monkeypatch.delenv("NOVEL_LOG_DIR", raising=False)
    append_run(tmp_path, RunRecord(operation="sync", status="done", duration_s=1.5))
    append_run(tmp_path, RunRecord(operation="download", status="error", error="boom"))
    path = tmp_path / "logs" / "runs.jsonl"
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["operation"] == "sync"
    assert first["status"] == "done"
    assert first["duration_s"] == 1.5
    assert json.loads(lines[1])["error"] == "boom"


def test_record_from_manifest_maps_counters():
    manifest = Manifest(
        slug="novela",
        title="Novela",
        source_url="https://example.com/novel",
        chapters_total=10,
        chapters_downloaded=5,
        chapters_translated=2,
        chapters_empty=1,
        epub_original=["a.epub"],
        epub_translated=["b.epub"],
    )
    record = record_from_manifest(
        manifest, operation="sync", status="done", duration=10.0
    )
    assert record.slug == "novela"
    assert record.url == "https://example.com/novel"
    assert record.epub_original == 1
    assert record.epub_translated == 1
    assert record.duration_s == 10.0


# --- Integracion ligera ----------------------------------------------------


def test_create_app_does_not_write_logs(tmp_path):
    create_app(output_dir=tmp_path)
    assert not (tmp_path / "logs").exists()


@pytest.mark.asyncio
async def test_fallback_logs_playwright():
    class _Http:
        async def fetch_html(self, url, *, headers=None):
            raise FetchError("boom")

        async def fetch_bytes(self, url, *, headers=None):
            raise FetchError("boom")

        async def aclose(self):
            return None

    class _Pw:
        async def fetch_html(self, url, *, headers=None):
            return "<html>ok</html>"

        async def fetch_bytes(self, url, *, headers=None):
            return b"ok"

        async def aclose(self):
            return None

    target_logger = logging.getLogger("novel_cli.core.scraper.fetcher")
    handler = _ListHandler()
    target_logger.addHandler(handler)
    previous_level = target_logger.level
    target_logger.setLevel(logging.INFO)
    try:
        fetcher = FallbackFetcher(_Http(), _Pw())
        html = await fetcher.fetch_html("https://example.com")
    finally:
        target_logger.removeHandler(handler)
        target_logger.setLevel(previous_level)

    assert html == "<html>ok</html>"
    assert any("Playwright" in r.getMessage() for r in handler.records)
