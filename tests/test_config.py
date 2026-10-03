"""Unit tests de la configuracion (core/config.py): loader .env y envs."""

from __future__ import annotations

import os

from novel_cli.core.config import (
    _load_dotenv,
    default_output,
    is_valid_source_language,
    log_dir,
    upload_max_bytes,
)


def test_load_dotenv_sets_and_does_not_override(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NOVEL_TEST_A=hola\n"
        'NOVEL_TEST_B="con comillas"\n'
        "NOVEL_TEST_C='simple'\n"
        "# comentario\n"
        "\n"
        "SIN_IGUAL\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("NOVEL_TEST_A", raising=False)
    monkeypatch.setenv("NOVEL_TEST_B", "ya-existe")
    _load_dotenv(env_file)
    assert os.environ["NOVEL_TEST_A"] == "hola"
    assert os.environ["NOVEL_TEST_B"] == "ya-existe"  # no sobreescribe
    assert os.environ["NOVEL_TEST_C"] == "simple"
    assert "SIN_IGUAL" not in os.environ


def test_log_dir_from_env(monkeypatch):
    monkeypatch.setenv("NOVEL_LOG_DIR", "/tmp/mis-logs")
    assert log_dir() is not None
    assert str(log_dir()) == "/tmp/mis-logs"


def test_log_dir_default_none(monkeypatch):
    monkeypatch.delenv("NOVEL_LOG_DIR", raising=False)
    assert log_dir() is None


def test_default_output_from_env(monkeypatch):
    monkeypatch.setenv("NOVEL_OUTPUT_DIR", "/tmp/biblioteca")
    assert str(default_output()) == "/tmp/biblioteca"


def test_upload_max_bytes_default(monkeypatch):
    monkeypatch.delenv("NOVEL_UPLOAD_MAX_MB", raising=False)
    assert upload_max_bytes() == 100 * 1024 * 1024


def test_is_valid_source_language():
    assert is_valid_source_language("es")
    assert is_valid_source_language("en")
    assert not is_valid_source_language("xx")