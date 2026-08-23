"""Adaptador NovelFire (modernizado del scrapper viejo, usa Fetcher no Playwright)."""

from __future__ import annotations

from urllib.parse import urljoin

from lxml import html as lh

from novel_cli.core.models.novel import Chapter, NovelMetadata, SiteMetadata
from novel_cli.core.utils.text import anchor_title, clean_text, guess_chapter_num

SEL_TITLE = ".novel-title"
SEL_COVER = ".fixed-img .cover img"
SEL_CHAPTER_LINKS = "#chpagedlist .chapter-list li a"
SEL_CHAPTER_TITLE = ".chapter-title"
SEL_PARAGRAPHS = "#chapter-container #content p"
SEL_NEXT = "#chpagedlist .page-item > .page-link[rel='next']"


class NovelfireAdapter:
    """Adaptador para novelfire.net y clones con el mismo markup."""

    name = "novelfire"

    def tocs(self, novel_url: str) -> list[str]:
        """Pagina de portada (titulo/portada) + pagina de listado de capitulos."""
        base = novel_url.rstrip("/")
        return [base, f"{base}/chapters"]

    def parse_toc(self, html: str, base_url: str) -> SiteMetadata:
        root = lh.fromstring(html)
        title = _first_text(root, SEL_TITLE) or _meta_prop(root, "og:title") or _title(root)
        cover = _first_attr(root, SEL_COVER, "src")
        chapters: list[Chapter] = []
        fallback = 1
        for anchor in root.cssselect(SEL_CHAPTER_LINKS):
            href = anchor.get("href")
            if not href:
                continue
            text = anchor_title(anchor)
            if not text:
                continue
            url = urljoin(base_url, href)
            num = guess_chapter_num(text, href, fallback)
            chapters.append(Chapter(num=num, title=text, url=url))
            fallback += 1
        return SiteMetadata(
            metadata=NovelMetadata(
                title=title or "Untitled",
                cover_url=_abs(cover, base_url),
                author=_meta_name(root, "author"),
                source_url=base_url,
            ),
            chapters=chapters,
        )

    def parse_chapter(self, html: str, chapter_url: str) -> list[str]:
        """Devuelve los parrafos del capitulo en orden."""
        root = lh.fromstring(html)
        paragraphs = [
            clean_text(p.text_content())
            for p in root.cssselect(SEL_PARAGRAPHS)
            if clean_text(p.text_content())
        ]
        return paragraphs

    def next_page(self, html: str, base_url: str) -> str | None:
        """URL de la siguiente pagina de listado, o None si es la ultima."""
        root = lh.fromstring(html)
        for link in root.cssselect(SEL_NEXT):
            parent = link.getparent()
            if parent is not None and "disabled" in (parent.get("class") or ""):
                return None
            href = link.get("href")
            if href:
                return urljoin(base_url, href)
        return None


def _first_text(root, selector: str) -> str | None:
    elements = root.cssselect(selector)
    if not elements:
        return None
    return clean_text(elements[0].text_content()) or None


def _first_attr(root, selector: str, attr: str) -> str | None:
    elements = root.cssselect(selector)
    if not elements:
        return None
    return elements[0].get(attr)


def _meta_prop(root, prop: str) -> str | None:
    for element in root.cssselect(f'meta[property="{prop}"]'):
        content = element.get("content")
        if content:
            return clean_text(content)
    return None


def _meta_name(root, name: str) -> str | None:
    for element in root.cssselect(f'meta[name="{name}"]'):
        content = element.get("content")
        if content:
            return clean_text(content)
    return None


def _title(root) -> str | None:
    elements = root.cssselect("title")
    if not elements:
        return None
    return clean_text(elements[0].text_content()) or None


def _abs(url: str | None, base_url: str) -> str | None:
    if not url:
        return None
    return urljoin(base_url, url)