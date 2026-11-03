"""Naming estable: slug de novela, nombres de volumenes y archivos de capitulo."""

from __future__ import annotations

import json
import re
from pathlib import Path


def slugify(title: str) -> str:
    """Slug estable para la carpeta de la novela (ej: inner-voice-...)."""
    slug = re.sub(r"[^\w]+", "-", title.lower(), flags=re.UNICODE)
    return slug.strip("-")


def _manifest_sha(slug_dir: Path) -> str | None:
    path = slug_dir / ".manifest.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get("source_pdf_sha256")
    return value if isinstance(value, str) else None


def unique_slug(base: str, output_dir: Path, *, sha256: str | None = None) -> str:
    """Return a slug that does not overwrite a different PDF.

    Re-importing the same PDF (same ``sha256``) reuses its directory; a different
    PDF with the same title gets a ``-2``/``-3`` suffix.
    """
    candidate = base or "novela"
    index = 1
    while True:
        slug = candidate if index == 1 else f"{candidate}-{index}"
        slug_dir = output_dir / slug
        if not slug_dir.exists():
            return slug
        if sha256 is not None and _manifest_sha(slug_dir) == sha256:
            return slug
        index += 1


def title_to_filename(title: str) -> str:
    """Titulo apto para nombre de archivo (conserva espacios, sin path separators)."""
    cleaned = re.sub(r'[\\/:*?"<>|]+', " ", title)
    return re.sub(r"\s+", " ", cleaned).strip()


def volume_name(base: str, start: int, end: int, suffix: str = "") -> str:
    """Nombre de volumen: '{base} {start}-{end}{suffix}.epub'."""
    return f"{base} {start}-{end}{suffix}.epub"


def epub_name(base: str, suffix: str = "") -> str:
    """Nombre de EPUB unico: '{base}{suffix}.epub'."""
    return f"{base}{suffix}.epub"


def chapter_filename(num: int) -> str:
    """Nombre de archivo de capitulo zero-padded: '0042.md'."""
    return f"{num:04d}.md"