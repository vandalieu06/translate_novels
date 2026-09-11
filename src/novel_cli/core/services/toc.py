"""Servicio de TOC: obtiene SiteMetadata completo desde la URL de la novela.

Incluye la cache del indice (``.toc.json``): ``crawl_toc`` recorre y pagina el
listado, ``toc_changed`` hace un peek barato para detectar novedades y
``site_from_cache`` reconstruye el TOC sin red desde el manifest + la cache.
"""

from __future__ import annotations

import logging

from novel_cli.core.models.novel import Chapter, NovelMetadata, SiteMetadata
from novel_cli.core.models.state import Manifest
from novel_cli.core.models.toc import TocCache
from novel_cli.core.scraper.base import Fetcher, SiteAdapter
from novel_cli.core.scraper.fetcher import Pacer

logger = logging.getLogger(__name__)


async def fetch_site_metadata(
    fetcher: Fetcher, adapter: SiteAdapter, novel_url: str
) -> SiteMetadata:
    """Wrapper de compatibilidad: devuelve solo el ``SiteMetadata`` del crawl."""
    site, _ = await crawl_toc(fetcher, adapter, novel_url)
    return site


async def crawl_toc(
    fetcher: Fetcher,
    adapter: SiteAdapter,
    novel_url: str,
    *,
    toc_pacer: Pacer | None = None,
) -> tuple[SiteMetadata, list[str]]:
    """Recorre las paginas de listado y fusiona TOC + metadatos.

    Devuelve ``(SiteMetadata, listing_pages)`` donde ``listing_pages`` es
    ``[primera, última]`` pagina que aporto capitulos (para el peek de la cache).
    ``toc_pacer`` aplica una pausa extra entre paginas del listado.
    """
    metadata: NovelMetadata | None = None
    chapters: list[Chapter] = []
    visited: set[str] = set()
    listing: list[str] = []
    queue = list(adapter.tocs(novel_url))

    while queue:
        page_url = queue.pop(0)
        if page_url in visited:
            continue
        visited.add(page_url)
        if toc_pacer is not None:
            await toc_pacer.acquire()
        logger.debug("TOC: leyendo %s", page_url)
        html = await fetcher.fetch_html(page_url)
        site = adapter.parse_toc(html, base_url=page_url)
        if metadata is None and site.metadata.title:
            metadata = site.metadata
        if site.chapters:
            listing.append(page_url)
        chapters.extend(site.chapters)
        next_url = adapter.next_page(html, page_url)
        if next_url and next_url not in visited and next_url not in queue:
            queue.append(next_url)

    if metadata is None:
        metadata = NovelMetadata(title="Untitled", source_url=novel_url)
    result = _dedupe_sort(chapters)
    listing_pages = [listing[0], listing[-1]] if listing else []
    logger.info(
        "TOC resuelto: %d capitulos, titulo=%r, paginas=%d",
        len(result),
        metadata.title,
        len(visited),
    )
    return SiteMetadata(metadata=metadata, chapters=result), listing_pages


async def toc_changed(
    fetcher: Fetcher,
    adapter: SiteAdapter,
    cache: TocCache,
    *,
    toc_pacer: Pacer | None = None,
) -> bool:
    """Peek barato: True si el listado parece tener capitulos nuevos.

    Consulta la primera y la ultima pagina de listado cacheadas. Hay cambio si
    el numero maximo supera el de la cache o si la ultima pagina ahora tiene
    ``rel=next`` (aparecieron paginas nuevas).
    """
    pages = cache.listing_pages
    if not pages:
        return True
    cached_max = cache.max_num()
    targets = list(dict.fromkeys([pages[0], pages[-1]]))
    for page_url in targets:
        if toc_pacer is not None:
            await toc_pacer.acquire()
        logger.debug("TOC: peek %s", page_url)
        html = await fetcher.fetch_html(page_url)
        site = adapter.parse_toc(html, base_url=page_url)
        nums = [chapter.num for chapter in site.chapters]
        if nums and max(nums) > cached_max:
            return True
        if page_url == pages[-1] and adapter.next_page(html, page_url) is not None:
            return True
    return False


def site_from_cache(manifest: Manifest, cache: TocCache) -> SiteMetadata:
    """Reconstruye el ``SiteMetadata`` desde el manifest + la cache (sin red)."""
    metadata = NovelMetadata(
        title=manifest.title,
        author=manifest.author,
        cover_url=manifest.cover_path,
        source_url=manifest.source_url or cache.source_url,
    )
    chapters = [
        Chapter(num=chapter.num, title=chapter.title, url=chapter.url)
        for chapter in cache.chapters
    ]
    return SiteMetadata(metadata=metadata, chapters=chapters)


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
