"""Construccion de EPUBs con ebooklib (original y traducido)."""

from __future__ import annotations

import hashlib
import html
import io
from pathlib import Path

from ebooklib import epub

from novel_cli.core.models.novel import Chapter, Volume


def stable_identifier(source_url: str) -> str:
    """Identificador estable derivado de la URL (re-imports deterministas)."""
    digest = hashlib.sha1(source_url.encode("utf-8")).hexdigest()
    return f"urn:novel-cli:{digest}"


def generate_volumes(
    chapters: list[Chapter], volume_size: int | None
) -> list[Volume]:
    """Divide capitulos ordenados en volumenes (o un solo EPUB)."""
    if not chapters:
        return []
    if volume_size is None:
        return [
            Volume(
                start=chapters[0].num,
                end=chapters[-1].num,
                chapters=list(chapters),
            )
        ]
    volumes: list[Volume] = []
    for start in range(0, len(chapters), volume_size):
        chunk = chapters[start : start + volume_size]
        volumes.append(
            Volume(
                start=chunk[0].num,
                end=chunk[-1].num,
                chapters=list(chunk),
            )
        )
    return volumes


def build_epub(
    *,
    title: str,
    author: str | None,
    language: str,
    identifier: str,
    chapters: list[Chapter],
    cover_path: str | None,
    translated: bool = False,
) -> bytes:
    """Construye un EPUB a partir de capitulos (originales o ya traducidos)."""
    book = epub.EpubBook()
    book.set_identifier(identifier)
    book.set_title(title)
    if author:
        book.add_author(author)
    book.set_language(language)

    epub_chapters = [_add_chapter(book, chapter, language) for chapter in chapters]

    if cover_path and Path(cover_path).exists():
        cover_uid, cover_html = _add_image_cover(book, Path(cover_path), language)
    else:
        cover_uid, cover_html = _add_svg_cover(book, title, author, language)
    book.add_metadata(None, "meta", "", {"name": "cover", "content": cover_uid})

    book.toc = tuple(epub_chapters)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [cover_html, "nav", *epub_chapters]

    buffer = io.BytesIO()
    epub.write_epub(buffer, book)
    return buffer.getvalue()


def _add_chapter(book: epub.EpubBook, chapter: Chapter, language: str) -> epub.EpubHtml:
    item = epub.EpubHtml(
        title=chapter.title,
        file_name=f"chapter{chapter.num:04d}.xhtml",
        lang=language,
    )
    paragraphs = "\n".join(
        f"<p>{html.escape(paragraph)}</p>" for paragraph in chapter.paragraphs
    )
    item.content = (
        "<html xmlns=\"http://www.w3.org/1999/xhtml\">"
        f"<head><title>{html.escape(chapter.title)}</title></head>"
        f"<body><h1>{html.escape(chapter.title)}</h1>\n{paragraphs}</body></html>"
    )
    book.add_item(item)
    return item


def _add_image_cover(
    book: epub.EpubBook, cover_path: Path, language: str
) -> tuple[str, epub.EpubHtml]:
    extension = cover_path.suffix.lstrip(".").lower() or "jpg"
    media_type = (
        "image/jpeg" if extension in ("jpg", "jpeg") else f"image/{extension}"
    )
    file_name = f"cover.{extension}"
    image = epub.EpubItem(
        uid="cover-image",
        file_name=file_name,
        media_type=media_type,
        content=cover_path.read_bytes(),
    )
    book.add_item(image)
    cover_html = epub.EpubHtml(title="Cover", file_name="cover.xhtml", lang=language)
    cover_html.content = (
        "<html xmlns=\"http://www.w3.org/1999/xhtml\">"
        "<head><title>Cover</title></head>"
        f'<body><div style="text-align:center"><img src="{file_name}" '
        'alt="Cover"/></div></body></html>'
    )
    book.add_item(cover_html)
    return "cover-image", cover_html


def _add_svg_cover(
    book: epub.EpubBook,
    title: str,
    author: str | None,
    language: str,
) -> tuple[str, epub.EpubHtml]:
    svg = _generate_cover_svg(title, author)
    image = epub.EpubItem(
        uid="cover-svg",
        file_name="cover.svg",
        media_type="image/svg+xml",
        content=svg,
    )
    book.add_item(image)
    cover_html = epub.EpubHtml(title="Cover", file_name="cover.xhtml", lang=language)
    cover_html.content = (
        "<html xmlns=\"http://www.w3.org/1999/xhtml\">"
        "<head><title>Cover</title></head>"
        '<body><div style="text-align:center"><img src="cover.svg" '
        'alt="Cover"/></div></body></html>'
    )
    book.add_item(cover_html)
    return "cover-svg", cover_html


def _generate_cover_svg(title: str, author: str | None) -> bytes:
    escaped_title = html.escape(title)
    escaped_author = html.escape(author) if author else ""
    subtitle = (
        f'<text x="50%" y="55%" font-size="20" fill="#cccccc" '
        f'text-anchor="middle">{escaped_author}</text>'
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="800" '
        'viewBox="0 0 600 800">'
        '<rect width="100%" height="100%" fill="#2c3e50"/>'
        f'<text x="50%" y="50%" font-size="32" fill="#ffffff" '
        f'text-anchor="middle">{escaped_title}</text>'
        f"{subtitle if escaped_author else ''}"
        "</svg>"
    )
    return svg.encode("utf-8")