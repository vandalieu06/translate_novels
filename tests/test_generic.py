"""Unit tests del adaptador generico (heuristica estilo Readest chapterList.ts)."""

from __future__ import annotations

from novel_cli.core.scraper.registry import get_adapter
from novel_cli.core.scraper.sites.generic import GenericAdapter

GENERIC_URL = "https://readhere.example/eternal-journey"


def test_registry_uses_generic_for_unknown_domain():
    assert isinstance(get_adapter(GENERIC_URL), GenericAdapter)


def test_registry_uses_novelfire_for_novelfire_domain():
    adapter = get_adapter("https://novelfire.net/book/something")
    assert adapter.name == "novelfire"


def test_registry_matches_subdomain():
    adapter = get_adapter("https://www.novelfire.net/book/something")
    assert adapter.name == "novelfire"


def test_parse_toc_generic(fixture_loader):
    adapter = GenericAdapter()
    html = fixture_loader("generic_toc.html")
    site = adapter.parse_toc(html, base_url=GENERIC_URL)

    assert site.metadata.title == "The Eternal Journey"
    assert site.metadata.author == "Jane Doe"
    assert site.metadata.cover_url == "https://example.com/eternal.jpg"
    assert site.metadata.description == "A long web novel about journeys."
    assert site.metadata.source_url == GENERIC_URL

    assert len(site.chapters) == 4
    assert [c.num for c in site.chapters] == [1, 2, 3, 4]
    assert site.chapters[0].title == "Chapter 1 - The Road"
    assert site.chapters[0].url == "https://readhere.example/eternal/chapter/1"


def test_parse_toc_dedupes_urls(fixture_loader):
    adapter = GenericAdapter()
    html = fixture_loader("generic_toc.html").replace(
        "</ul>",
        '<li><a href="/eternal/chapter/2">Chapter 2 - Duplicate</a></li></ul>',
        1,
    )
    site = adapter.parse_toc(html, base_url=GENERIC_URL)
    urls = [c.url for c in site.chapters]
    assert len(urls) == len(set(urls)) == 4


def test_parse_toc_rejects_non_toc(fixture_loader):
    adapter = GenericAdapter()
    html = fixture_loader("generic_no_toc.html")
    site = adapter.parse_toc(html, base_url=GENERIC_URL)
    assert site.chapters == []


def test_generic_no_pagination():
    adapter = GenericAdapter()
    assert adapter.next_page("<html></html>", GENERIC_URL) is None


def test_generic_tocs_is_novel_url():
    adapter = GenericAdapter()
    assert adapter.tocs(GENERIC_URL) == [GENERIC_URL]