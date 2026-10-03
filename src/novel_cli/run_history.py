"""Historial de ejecuciones en JSONL (auditoria/debug, fuera de core).

Cada run de CLI o job web anexa una linea a ``output/logs/runs.jsonl`` con la
operacion, el estado, la duracion, los contadores del manifest y el error si lo
hubo. Es independiente del logging tecnico y no acopla ``core`` al formato.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from novel_cli.core import config
from novel_cli.core.models.state import Manifest


@dataclass
class RunRecord:
    """Resumen de una ejecucion (una linea de ``runs.jsonl``)."""

    operation: str
    status: str
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    job_id: str | None = None
    url: str = ""
    slug: str | None = None
    title: str | None = None
    duration_s: float | None = None
    chapters_total: int | None = None
    chapters_downloaded: int | None = None
    chapters_translated: int | None = None
    chapters_empty: int | None = None
    epub_original: int | None = None
    epub_translated: int | None = None
    error: str | None = None


def append_run(output_dir: str | Path, record: RunRecord) -> Path:
    """Anexa ``record`` a ``runs.jsonl`` y devuelve la ruta.

    El destino es ``NOVEL_LOG_DIR`` si esta definido; si no,
    ``<output_dir>/logs/runs.jsonl`` (comportamiento historico).
    """
    log_dir = config.log_dir() or (Path(output_dir) / "logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "runs.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    return path


def record_from_manifest(
    manifest: Manifest,
    *,
    operation: str,
    status: str,
    duration: float,
    job_id: str | None = None,
    url: str = "",
    error: str | None = None,
) -> RunRecord:
    """Construye un ``RunRecord`` a partir del manifest final."""
    return RunRecord(
        operation=operation,
        status=status,
        job_id=job_id,
        url=url or manifest.source_url,
        slug=manifest.slug,
        title=manifest.title,
        duration_s=round(duration, 2),
        chapters_total=manifest.chapters_total,
        chapters_downloaded=manifest.chapters_downloaded,
        chapters_translated=manifest.chapters_translated,
        chapters_empty=manifest.chapters_empty,
        epub_original=len(manifest.epub_original),
        epub_translated=len(manifest.epub_translated),
        error=error,
    )
