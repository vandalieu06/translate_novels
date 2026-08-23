"""Configuracion global de novel_cli (core puro, sin dependencias de CLI)."""

from __future__ import annotations

import os
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


# --- Limites y constantes (lecciones de Readest) ---------------------------
CHAPTER_REQUEST_MIN_INTERVAL_MS = 300
DEFAULT_HTTP_TIMEOUT_SECONDS = 15.0

RETRY_TRANSIENT = 2
RETRY_TRANSIENT_BACKOFF = (1.0, 2.0)
RETRY_RATE_LIMIT = 3
RETRY_BACKOFF_BASE_SECONDS = 2.0
RETRY_AFTER_MAX_SECONDS = 30.0
MAX_COOLDOWN_SECONDS = 30.0

DEFAULT_MAX_WORDS_PER_CHUNK = 400
DEFAULT_CONCURRENCY = 4
DEFAULT_TRANSLATE_TARGET = "es"
DEFAULT_VOLUME_SIZE = 50

# Traduccion: capa de tiempos conservadora para no quemar el endpoint gratuito.
TRANSLATE_REQUEST_MIN_INTERVAL_MS = _int_env("NOVEL_TRANSLATE_PACER_MS", 1500)
TRANSLATE_RETRY_RATE_LIMIT = 5
TRANSLATE_BACKOFF_BASE_SECONDS = 5.0
TRANSLATE_RETRY_AFTER_MAX_SECONDS = 60.0


def default_output() -> Path:
    """Directorio de salida por defecto.

    1. Env ``NOVEL_OUTPUT_DIR`` si esta definida, o
    2. ``./output`` relativo al directorio de trabajo.
    """
    env = os.environ.get("NOVEL_OUTPUT_DIR")
    if env:
        return Path(env).expanduser()
    return Path("output")