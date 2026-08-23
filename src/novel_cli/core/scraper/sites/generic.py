"""Adaptador generico: heuristica de TOC estilo Readest chapterList.ts."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from lxml import html as lh

from novel_cli.core.models.novel import Chapter, NovelMetadata, SiteMetadata
from novel_cli.core.utils.text import clean_text, guess_chapter_num

_NUMBERED_TITLE = re.compile(r"(?:chapter|ch\.?|cap(?:itulo)?|第|章节)", re.IGNORECASE)
_HREF_DIGIT_RUN = re.compile(r"\d{3,}")


class GenericAdapter:
    """Heuristica de TOC para sitios sin adaptador propio."""

    name = "generic"

    def tocs(self, novel_url: str) -> list[str]:
        return [novel_url]

    def parse_toc(self, html: str, base_url: str) -> SiteMetadata:
        root = lh.fromstring(html)
        candidates = _find_candidates(root)
        container = _best_container(root, candidates)
        links = [
            anchor
            for anchor in candidates
            if container is None or anchor in container.iter()
        ]
        chapters: list[Chapter] = []
        seen: set[str] = set()
        fallback = 1
        for anchor in links:
            href = anchor.get("href") or ""
            url = urljoin(base_url, href)
            if url in seen:
                continue
            seen.add(url)
            text = clean_text(anchor.text_content())
            num = guess_chapter_num(text, href, fallback)
            chapters.append(Chapter(num=num, title=text or href, url=url))
            fallback += 1
        chapters.sort(key=lambda c: c.num)
        return SiteMetadata(
            metadata=NovelMetadata(
                title=_og_title(root, base_url),
                author=_meta_name(root, "author"),
                cover_url=_og_image(root, base_url),
                description=(
                    _meta_prop(root, "og:description") or _meta_name(root, "description")
                ),
                source_url=base_url,
            ),
            chapters=chapters,
        )

    def parse_chapter(self, html: str, chapter_url: str) -> list[str]:
        """Parrafos: todo <p> directo del body principal (heuristica simple)."""
        root = lh.fromstring(html)
        candidates = root.cssselect("article p") or root.cssselect("#content p")
        if not candidates:
            candidates = root.cssselect("p")
        paragraphs = [
            clean_text(p.text_content())
            for p in candidates
            if clean_text(p.text_content())
        ]
        return paragraphs

    def next_page(self, html: str, base_url: str) -> str | None:
        return None


def _find_candidates(root) -> list:
    out: list = []
    for anchor in root.cssselect("a[href]"):
        text = clean_text(anchor.text_content())
        href = anchor.get("href") or ""
        if _NUMBERED_TITLE.search(text) and any(ch.isdigit() for ch in text):
            out.append(anchor)
        elif _HREF_DIGIT_RUN.search(href) and len(text) >= 3:
            out.append(anchor)
    return out


def _best_container(root, candidates) -> object | None:
    counts: dict = {}
    for anchor in candidates:
        for ancestor in anchor.iterancestors():
            counts[ancestor] = counts.get(ancestor, 0) + 1
    best = None
    for element, count in counts.items():
        if count < 2:
            continue
        if best is None or count > counts[best] or (
            count == counts[best] and _depth(element) > _depth(best)
        ):
            best = element
    return best


def _depth(element) -> int:
    depth = 0
    while element.getparent() is not None:
        element = element.getparent()
        depth += 1
    return depth


def _og_title(root, base_url: str) -> str:
    for element in root.cssselect('meta[property="og:title"]'):
        content = element.get("content")
        if content:
            return clean_text(content)
    for element in root.cssselect("title"):
        return clean_text(element.text_content())
    return "Untitled"


def _og_image(root, base_url: str) -> str | None:
    for element in root.cssselect('meta[property="og:image"]'):
        content = element.get("content")
        if content:
            return urljoin(base_url, content)
    return None


def _meta_name(root, name: str) -> str | None:
    for element in root.cssselect(f'meta[name="{name}"]'):
        content = element.get("content")
        if content:
            return clean_text(content)
    return None


def _meta_prop(root, prop: str) -> str | None:
    for element in root.cssselect(f'meta[property="{prop}"]'):
        content = element.get("content")
        if content:
            return clean_text(content)
    return None