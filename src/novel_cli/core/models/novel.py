"""Modelos de dominio de una web novel (dataclasses, core puro)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class NovelMetadata:
    """Metadatos extraidos de la portada/TOC del sitio."""

    title: str
    author: str | None = None
    cover_url: str | None = None
    description: str | None = None
    language_code: str = "auto"
    source_url: str = ""


@dataclass
class Chapter:
    """Capitulo con su contenido crudo en el idioma original."""

    num: int
    title: str
    url: str
    paragraphs: list[str] = field(default_factory=list)


@dataclass
class SiteMetadata:
    """TOC extraido: metadatos de la novela + lista de capitulos."""

    metadata: NovelMetadata
    chapters: list[Chapter]


@dataclass
class Volume:
    """Agrupacion de capitulos ordenados (1-50, 51-100, ...)."""

    start: int
    end: int
    chapters: list[Chapter]