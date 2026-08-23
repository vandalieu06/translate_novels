"""Utilidades de texto: limpieza, deteccion de numero de capitulo y chunking."""

from __future__ import annotations

import re

_CHAPTER_NUM = re.compile(
    r"(?:chapter|ch\.?|cap(?:itulo)?|第|章节)\s*\.?\s*(\d+)", re.IGNORECASE
)
_HREF_CHAPTER = re.compile(r"/chapter[s]?[-/](\d+)", re.IGNORECASE)


def clean_text(raw: str) -> str:
    """Colapsa whitespace y recorta."""
    return " ".join(raw.split())


def anchor_title(anchor) -> str:
    """Texto limpio de un enlace: prioriza el atributo ``title``."""
    raw = anchor.get("title")
    if raw:
        return clean_text(raw)
    return clean_text(anchor.text_content())


def guess_chapter_num(text: str, href: str, fallback: int) -> int:
    """Extrae el numero de capitulo del texto o del href; si no, usa fallback."""
    match = _CHAPTER_NUM.search(text)
    if match:
        return int(match.group(1))
    match = _HREF_CHAPTER.search(href)
    if match:
        return int(match.group(1))
    return fallback


def split_text_by_words(
    paragraphs: list[str], max_words_per_chunk: int = 400
) -> list[str]:
    """Divide párrafos en chunks respetando el máximo de palabras por chunk.

    Cada chunk une sus párrafos con ``\\n``; al reensamblar se re-dividen
    por ``\\n`` para reconstruir los párrafos 1:1.
    """
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_word_count = 0

    for paragraph in paragraphs:
        paragraph_words = len(paragraph.split())
        if (
            current_word_count + paragraph_words > max_words_per_chunk
            and current_chunk
        ):
            chunks.append("\n".join(current_chunk))
            current_chunk = [paragraph]
            current_word_count = paragraph_words
        else:
            current_chunk.append(paragraph)
            current_word_count += paragraph_words

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks