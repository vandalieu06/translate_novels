"""Servicio de TOC: obtiene SiteMetadata completo desde la URL de la novela."""

from __future__ import annotations

from novel_cli.core.models.novel import Chapter, NovelMetadata, SiteMetadata
from novel_cli.core.scraper.base import Fetcher, SiteAdapter


async def fetch_site_metadata(
    fetcher: Fetcher, adapter: SiteAdapter, novel_url: str
) -> SiteMetadata:
    """Recorre paginas de listado del adaptador y fusiona TOC + metadatos."""
    metadata: NovelMetadata | None = None
    chapters: list[Chapter] = []
    visited: set[str] = set()
    queue = list(adapter.tocs(novel_url))

    while queue:
        page_url = queue.pop(0)
        if page_url in visited:
            continue
        visited.add(page_url)
        html = await fetcher.fetch_html(page_url)
        site = adapter.parse_toc(html, base_url=page_url)
        if metadata is None and site.metadata.title:
            metadata = site.metadata
        chapters.extend(site.chapters)
        next_url = adapter.next_page(html, page_url)
        if next_url and next_url not in visited and next_url not in queue:
            queue.append(next_url)

    if metadata is None:
        metadata = NovelMetadata(title="Untitled", source_url=novel_url)
    return SiteMetadata(metadata=metadata, chapters=_dedupe_sort(chapters))


def _dedupe_sort(chapters: list[Chapter]) -> list[Chapter]:
    seen: set[str] = set()
    unique: list[Chapter] = []
    for chapter in chapters:
        if chapter.url in seen:
            continue
        seen.add(chapter.url)
        unique.append(chapter)
    unique.sort(key=lambda c: c.num)
    return unique