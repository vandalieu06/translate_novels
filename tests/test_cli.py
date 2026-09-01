"""Unit tests del CLI (typer CliRunner): validacion, codigos de salida, help."""

from __future__ import annotations

import importlib
from typing import Any

from typer.testing import CliRunner

from novel_cli.cli.app import app
from novel_cli.core.models.state import Manifest
from novel_cli.core.scraper.fetcher import FetchError
from novel_cli.core.services.pipeline import PipelineError
from novel_cli.core.services.translate import GoogleFreeTranslator, TranslateError

cli_app_module = importlib.import_module("novel_cli.cli.app")

runner = CliRunner()

NOVEL_URL = "https://example.com/novel"


def test_help_documents_command():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "run" in result.output
    assert "URL de la web novel" in result.output
    for flag in ("--output", "--volume-size", "--translate", "--resume", "--force",
                 "--playwright", "--concurrency", "--verbose", "--all",
                 "--translate-pending"):
        assert flag in result.output


def test_invalid_url_exit_1():
    result = runner.invoke(app, ["not-a-url"])
    assert result.exit_code == 1
    assert "URL invalida" in result.output


def test_invalid_volume_size_exit_1():
    result = runner.invoke(app, [NOVEL_URL, "--volume-size", "75"])
    assert result.exit_code == 1
    assert "50 o 100" in result.output


def test_volume_size_zero_rejected_exit_1():
    result = runner.invoke(app, [NOVEL_URL, "--volume-size", "0"])
    assert result.exit_code == 1
    assert "50 o 100" in result.output


def test_invalid_concurrency_exit_1():
    result = runner.invoke(app, [NOVEL_URL, "--concurrency", "0"])
    assert result.exit_code == 1
    assert "concurrency" in result.output


async def _fake_pipeline(**kwargs: Any) -> Manifest:
    return Manifest(slug="novela", title="Novela")


def test_default_volume_size_50(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> Manifest:
        captured.update(kwargs)
        return Manifest(slug="novela", title="Novela")

    monkeypatch.setattr(cli_app_module, "run_pipeline", fake)
    result = runner.invoke(app, [NOVEL_URL, "-o", str(tmp_path)])
    assert result.exit_code == 0
    assert captured["volume_size"] == 50
    assert captured["download_all"] is False


def test_all_flag_passes_download_all(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> Manifest:
        captured.update(kwargs)
        return Manifest(slug="novela", title="Novela")

    monkeypatch.setattr(cli_app_module, "run_pipeline", fake)
    result = runner.invoke(app, [NOVEL_URL, "-o", str(tmp_path), "--all", "-v", "100"])
    assert result.exit_code == 0
    assert captured["volume_size"] == 100
    assert captured["download_all"] is True


def test_translate_pending_flag_builds_translator(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> Manifest:
        captured.update(kwargs)
        return Manifest(slug="novela", title="Novela")

    monkeypatch.setattr(cli_app_module, "run_pipeline", fake)
    result = runner.invoke(app, [NOVEL_URL, "-o", str(tmp_path), "--translate-pending"])
    assert result.exit_code == 0
    assert captured["translate_pending"] is True
    assert captured["translate"] is False
    assert isinstance(captured["translator"], GoogleFreeTranslator)


def test_success_exit_0(monkeypatch, tmp_path):
    monkeypatch.setattr(cli_app_module, "run_pipeline", _fake_pipeline)
    result = runner.invoke(app, [NOVEL_URL, "-o", str(tmp_path)])
    assert result.exit_code == 0
    assert "Listo" in result.output


def test_network_error_exit_2(monkeypatch, tmp_path):
    async def boom(**kwargs: Any) -> Manifest:
        raise FetchError("network down")

    monkeypatch.setattr(cli_app_module, "run_pipeline", boom)
    result = runner.invoke(app, [NOVEL_URL, "-o", str(tmp_path)])
    assert result.exit_code == 2
    assert "network down" in result.output


def test_translation_error_exit_3(monkeypatch, tmp_path):
    async def boom(**kwargs: Any) -> Manifest:
        raise TranslateError("translate boom")

    monkeypatch.setattr(cli_app_module, "run_pipeline", boom)
    result = runner.invoke(app, [NOVEL_URL, "-o", str(tmp_path), "--translate"])
    assert result.exit_code == 3
    assert "translate boom" in result.output


def test_pipeline_error_exit_4(monkeypatch, tmp_path):
    async def boom(**kwargs: Any) -> Manifest:
        raise PipelineError("epub boom")

    monkeypatch.setattr(cli_app_module, "run_pipeline", boom)
    result = runner.invoke(app, [NOVEL_URL, "-o", str(tmp_path)])
    assert result.exit_code == 4
    assert "epub boom" in result.output


def test_validation_error_not_call_pipeline(monkeypatch):
    called = {"yes": False}

    async def fake(**kwargs: Any) -> Manifest:
        called["yes"] = True
        return Manifest(slug="novela", title="Novela")

    monkeypatch.setattr(cli_app_module, "run_pipeline", fake)
    runner.invoke(app, ["bad-url"])
    assert called["yes"] is False


def test_no_args_requires_url():
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "Missing argument 'url'" in result.output


def test_translate_concurrency_flag_passed(monkeypatch, tmp_path):
    captured: dict[str, Any] = {}

    async def fake(**kwargs: Any) -> Manifest:
        captured.update(kwargs)
        return Manifest(slug="novela", title="Novela")

    monkeypatch.setattr(cli_app_module, "run_pipeline", fake)
    result = runner.invoke(
        app,
        [NOVEL_URL, "-o", str(tmp_path), "--translate", "-tc", "8"],
    )
    assert result.exit_code == 0
    assert captured["translate_concurrency"] == 8


def test_translate_concurrency_zero_rejected_exit_1(monkeypatch, tmp_path):
    result = runner.invoke(app, [NOVEL_URL, "-tc", "0"])
    assert result.exit_code == 1
    assert "translate-concurrency" in result.output