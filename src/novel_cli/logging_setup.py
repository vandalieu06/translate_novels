"""Configuracion de logging (infraestructura, fuera de core).

`core` solo usa ``logging.getLogger(__name__)``; aqui se configuran los
handlers del logger ``novel_cli``: un fichero rotativo (historial tecnico) y la
consola (solo avisos, para no romper las barras de ``rich``). El ``job_id`` se
propaga por ``contextvars`` para etiquetar los registros de cada job web.
"""

from __future__ import annotations

import contextvars
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from novel_cli.core import config

JOB_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "novel_cli_job_id", default="-"
)

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(job_id)s]: %(message)s"
_CONSOLE_FORMAT = "%(levelname)s %(name)s: %(message)s"
_DEFAULT_MAX_BYTES = 5 * 1024 * 1024
_DEFAULT_BACKUPS = 3
_TAG = "_novel_cli"
_NOISY_LOGGERS = ("httpx", "httpcore", "telegram", "uvicorn.access", "urllib3")


class _JobIdFilter(logging.Filter):
    """Inyecta el ``job_id`` del contexto en cada registro."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.job_id = JOB_ID.get()
        return True


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _resolve_path(output_dir: Path) -> Path:
    env = os.environ.get("NOVEL_LOG_FILE")
    if env:
        return Path(env).expanduser()
    return Path(output_dir) / "logs" / "novel-cli.log"


def configure_logging(
    *,
    output_dir: Path | None = None,
    verbose: bool = False,
    force: bool = False,
) -> Path:
    """Configura el logger ``novel_cli`` (idempotente) y devuelve el fichero.

    ``force=True`` recrea los handlers (util en tests o al cambiar de destino).
    El nivel del fichero es ``NOVEL_LOG_LEVEL`` (o DEBUG con ``verbose``); la
    consola se queda en WARNING salvo ``verbose``.
    """
    logger = logging.getLogger("novel_cli")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    if force:
        for handler in list(logger.handlers):
            if getattr(handler, _TAG, False):
                logger.removeHandler(handler)

    resolved = _resolve_path(Path(output_dir) if output_dir else config.default_output())
    configured = any(getattr(h, _TAG, False) for h in logger.handlers)

    if not configured:
        level_name = os.environ.get("NOVEL_LOG_LEVEL", "").strip().upper()
        file_level = getattr(
            logging, level_name, logging.DEBUG if verbose else logging.INFO
        )
        resolved.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            resolved,
            maxBytes=_int_env("NOVEL_LOG_MAX_BYTES", _DEFAULT_MAX_BYTES),
            backupCount=_int_env("NOVEL_LOG_BACKUPS", _DEFAULT_BACKUPS),
            encoding="utf-8",
        )
        file_handler.setLevel(file_level)
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
        file_handler.addFilter(_JobIdFilter())
        setattr(file_handler, _TAG, True)

        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
        console_handler.setFormatter(logging.Formatter(_CONSOLE_FORMAT))
        setattr(console_handler, _TAG, True)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    return resolved
