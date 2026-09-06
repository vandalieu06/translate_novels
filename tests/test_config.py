"""Unit tests de la configuracion (core/config.py): loader .env y envs."""

from __future__ import annotations

import os

from novel_cli.core.config import _load_dotenv


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