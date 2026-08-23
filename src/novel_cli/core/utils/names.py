"""Naming estable: slug de novela, nombres de volumenes y archivos de capitulo."""

from __future__ import annotations

import re


def slugify(title: str) -> str:
    """Slug estable para la carpeta de la novela (ej: inner-voice-...)."""
    slug = re.sub(r"[^\w]+", "-", title.lower(), flags=re.UNICODE)
    return slug.strip("-")


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