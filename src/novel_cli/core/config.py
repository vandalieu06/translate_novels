"""Configuracion global de novel_cli (core puro, sin dependencias de CLI)."""

from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv(path: Path | None = None) -> None:
    """Carga variables KEY=VALUE de un .env en os.environ sin sobrescribir.

    Sirve para fijar la configuracion (p. ej. NOVEL_TRANSLATE_BACKEND) sin
    exportar variables en cada arranque. No requiere dependencias externas.
    """
    path = path or Path(os.environ.get("NOVEL_CLI_ENV_FILE", ".env"))
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()


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
DEFAULT_TRANSLATE_TARGET = os.environ.get("NOVEL_TRANSLATE_TARGET", "es")

# Idiomas destino de traduccion (codigo -> etiqueta) para CLI/UI. Lista curada:
# Google acepta cualquiera; con LibreTranslate requiere que el modelo este instalado.
TRANSLATE_TARGET_LANGUAGES: dict[str, str] = {
    "es": "Español",
    "en": "English",
    "fr": "Français",
    "de": "Deutsch",
    "it": "Italiano",
    "pt": "Português",
    "ru": "Русский",
    "ja": "日本語",
    "ko": "한국어",
    "zh": "中文",
}

# Nombre del idioma en ingles (para el prompt del backend LLM, p. ej.
# "English (en) to Spanish (es)"). Fallback: el propio codigo.
TRANSLATE_LANGUAGE_NAMES_EN: dict[str, str] = {
    "es": "Spanish",
    "en": "English",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
}


def language_name_en(code: str) -> str:
    """Nombre en ingles del idioma; si no esta en la lista, devuelve el codigo."""
    return TRANSLATE_LANGUAGE_NAMES_EN.get(code, code)

DEFAULT_VOLUME_SIZE = 50

# Selector de backend de traduccion (para pruebas locales con LibreTranslate o LLM).
# google | libre | ollama
TRANSLATE_BACKEND = os.environ.get("NOVEL_TRANSLATE_BACKEND", "google")
TRANSLATE_URL = os.environ.get("NOVEL_TRANSLATE_URL", "http://localhost:5000")
TRANSLATE_API_KEY = os.environ.get("NOVEL_TRANSLATE_API_KEY") or None

# Backend LLM local via Ollama (default: TranslateGemma 4B, prompt oficial).
OLLAMA_URL = os.environ.get("NOVEL_OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("NOVEL_OLLAMA_MODEL", "translategemma:4b")
OLLAMA_SOURCE_LANG = os.environ.get("NOVEL_OLLAMA_SOURCE_LANG", "en")
OLLAMA_TIMEOUT_SECONDS = _int_env("NOVEL_OLLAMA_TIMEOUT", 300)
OLLAMA_MAX_WORDS_PER_CHUNK = _int_env("NOVEL_OLLAMA_MAX_WORDS_PER_CHUNK", 400)
OLLAMA_KEEP_ALIVE = os.environ.get("NOVEL_OLLAMA_KEEP_ALIVE", "10m")

# Traduccion: capa de tiempos conservadora para no quemar el endpoint gratuito.
# El pacer por defecto depende del backend: conservador (1500ms) para google,
# agresivo (250ms) para LibreTranslate local, 0 (local sin rate-limit) para Ollama.
# Env NOVEL_TRANSLATE_PACER_MS lo sobrescribe.
DEFAULT_TRANSLATE_PACER_MS = 1500
LIBRE_TRANSLATE_PACER_MS = 250
OLLAMA_TRANSLATE_PACER_MS = 0


def _default_translate_pacer_ms() -> int:
    if TRANSLATE_BACKEND == "libre":
        return LIBRE_TRANSLATE_PACER_MS
    if TRANSLATE_BACKEND == "ollama":
        return OLLAMA_TRANSLATE_PACER_MS
    return DEFAULT_TRANSLATE_PACER_MS


TRANSLATE_REQUEST_MIN_INTERVAL_MS = _int_env(
    "NOVEL_TRANSLATE_PACER_MS", _default_translate_pacer_ms()
)
TRANSLATE_RETRY_RATE_LIMIT = 5
TRANSLATE_BACKOFF_BASE_SECONDS = 5.0
TRANSLATE_RETRY_AFTER_MAX_SECONDS = 60.0

# Concurrencia de traduccion (capitulos en paralelo).
# Default por backend: 4 para LibreTranslate local (CPU alta), 1 para google/ollama.
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
    """Capa de proteccion: google/ollama siempre 1; libre con tope maximo."""
    value = (
        requested
        if requested is not None and requested > 0
        else translate_concurrency_default()
    )
    if TRANSLATE_BACKEND in ("google", "ollama"):
        return 1
    return max(1, min(value, TRANSLATE_MAX_CONCURRENCY))


def translate_max_words_per_chunk() -> int:
    """Palabras por chunk de traduccion segun el backend activo."""
    if TRANSLATE_BACKEND == "ollama":
        return OLLAMA_MAX_WORDS_PER_CHUNK
    return DEFAULT_MAX_WORDS_PER_CHUNK


def translate_target_default() -> str:
    """Idioma destino por defecto (validado contra la lista curada)."""
    target = DEFAULT_TRANSLATE_TARGET
    return target if target in TRANSLATE_TARGET_LANGUAGES else "es"


def is_valid_translate_target(target: str) -> bool:
    return target in TRANSLATE_TARGET_LANGUAGES


# --- Importacion de PDFs ----------------------------------------------------
# Idiomas origen soportados para PDFs (el usuario lo indica; nunca auto).
SOURCE_LANGUAGES: dict[str, str] = dict(TRANSLATE_TARGET_LANGUAGES)

UPLOAD_MAX_MB = _int_env("NOVEL_UPLOAD_MAX_MB", 100)


def upload_max_bytes() -> int:
    """Tamano maximo de subida de PDFs (env NOVEL_UPLOAD_MAX_MB)."""
    return UPLOAD_MAX_MB * 1024 * 1024


def is_valid_source_language(code: str) -> bool:
    return code in SOURCE_LANGUAGES


# --- Cache del TOC (indice de capitulos) ------------------------------------
# Pausa entre paginas de listado (mas conservadora que la de descarga).
TOC_REQUEST_MIN_INTERVAL_MS = _int_env("NOVEL_TOC_PACER_MS", 1000)
DEFAULT_TOC_TTL_HOURS = 6.0


def toc_ttl_seconds() -> float:
    """TTL de la cache del TOC en segundos (env NOVEL_TOC_TTL_HOURS; 0 = siempre peek)."""
    raw = os.environ.get("NOVEL_TOC_TTL_HOURS")
    if raw is None or not raw.strip():
        return DEFAULT_TOC_TTL_HOURS * 3600
    try:
        return max(0.0, float(raw)) * 3600
    except ValueError:
        return DEFAULT_TOC_TTL_HOURS * 3600


# --- Notificaciones por Telegram (opcionales) -------------------------------
# Sin token y chat_id no se notifica. Se leen en cada llamada para que los
# tests puedan configurarlas con monkeypatch.
def telegram_bot_token() -> str | None:
    return os.environ.get("NOVEL_TELEGRAM_BOT_TOKEN") or None


def telegram_chat_id() -> str | None:
    return os.environ.get("NOVEL_TELEGRAM_CHAT_ID") or None


def telegram_enabled() -> bool:
    """Activo si hay token+chat y no se desactiva explicitamente."""
    if not telegram_bot_token() or not telegram_chat_id():
        return False
    raw = os.environ.get("NOVEL_TELEGRAM_ENABLED")
    if raw is None or not raw.strip():
        return True
    return raw.strip().lower() in ("1", "true", "yes", "on")


def default_output() -> Path:
    """Directorio de salida por defecto.

    1. Env ``NOVEL_OUTPUT_DIR`` si esta definida, o
    2. ``./output`` relativo al directorio de trabajo.
    """
    env = os.environ.get("NOVEL_OUTPUT_DIR")
    if env:
        return Path(env).expanduser()
    return Path("output")