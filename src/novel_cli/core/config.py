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

# Reintentos de capitulos vacios (parser devolvio 0 parrafos).
EMPTY_RETRIES = 3
EMPTY_RETRY_BACKOFF = (2.0, 4.0, 6.0)
DEFAULT_TRANSLATE_TARGET = "es"
DEFAULT_VOLUME_SIZE = 50

# Selector de backend de traduccion (para pruebas locales con LibreTranslate).
TRANSLATE_BACKEND = os.environ.get("NOVEL_TRANSLATE_BACKEND", "google")  # google | libre
TRANSLATE_URL = os.environ.get("NOVEL_TRANSLATE_URL", "http://localhost:5000")
TRANSLATE_API_KEY = os.environ.get("NOVEL_TRANSLATE_API_KEY") or None

# Traduccion: capa de tiempos conservadora para no quemar el endpoint gratuito.
# El pacer por defecto depende del backend: conservador (1500ms) para google,
# agresivo (250ms) para LibreTranslate local (env NOVEL_TRANSLATE_PACER_MS lo sobrescribe).
DEFAULT_TRANSLATE_PACER_MS = 1500
LIBRE_TRANSLATE_PACER_MS = 250
TRANSLATE_REQUEST_MIN_INTERVAL_MS = _int_env(
    "NOVEL_TRANSLATE_PACER_MS",
    LIBRE_TRANSLATE_PACER_MS if TRANSLATE_BACKEND == "libre" else DEFAULT_TRANSLATE_PACER_MS,
)
TRANSLATE_RETRY_RATE_LIMIT = 5
TRANSLATE_BACKOFF_BASE_SECONDS = 5.0
TRANSLATE_RETRY_AFTER_MAX_SECONDS = 60.0

# Concurrencia de traduccion (capitulos en paralelo).
# Default inteligente por backend: 4 para LibreTranslate local (CPU alta), 1 para google.
DEFAULT_TRANSLATE_CONCURRENCY = 1
LIBRE_TRANSLATE_CONCURRENCY = 4
TRANSLATE_MAX_CONCURRENCY = _int_env("NOVEL_TRANSLATE_MAX_CONCURRENCY", 16)
TRANSLATE_CONCURRENCY = _int_env("NOVEL_TRANSLATE_CONCURRENCY", 0)  # 0 = automatico


def translate_concurrency_default() -> int:
    """Concurrencia de traduccion por defecto (0 = auto → segun backend)."""
    if TRANSLATE_CONCURRENCY > 0:
        return TRANSLATE_CONCURRENCY
    if TRANSLATE_BACKEND == "libre":
        return LIBRE_TRANSLATE_CONCURRENCY
    return DEFAULT_TRANSLATE_CONCURRENCY


def effective_translate_concurrency(requested: int | None) -> int:
    """Aplica la capa de proteccion: google siempre 1; libre con tope maximo."""
    value = (
        requested
        if requested is not None and requested > 0
        else translate_concurrency_default()
    )
    if TRANSLATE_BACKEND == "google":
        return 1
    return max(1, min(value, TRANSLATE_MAX_CONCURRENCY))


def default_output() -> Path:
    """Directorio de salida por defecto.

    1. Env ``NOVEL_OUTPUT_DIR`` si esta definida, o
    2. ``./output`` relativo al directorio de trabajo.
    """
    env = os.environ.get("NOVEL_OUTPUT_DIR")
    if env:
        return Path(env).expanduser()
    return Path("output")