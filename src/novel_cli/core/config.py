"""Configuracion global de novel_cli (core puro, sin dependencias de CLI)."""

from __future__ import annotations

import os
from pathlib import Path

# --- Limites y constantes (lecciones de Readest) ---------------------------
CHAPTER_REQUEST_MIN_INTERVAL_MS = 300
TRANSLATE_REQUEST_MIN_INTERVAL_MS = 300
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


def default_output() -> Path:
    """Directorio de salida por defecto.

    1. Env ``NOVEL_OUTPUT_DIR`` si esta definida, o
    2. ``./output`` relativo al directorio de trabajo.
    """
    env = os.environ.get("NOVEL_OUTPUT_DIR")
    if env:
        return Path(env).expanduser()
    return Path("output")