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


def test_generic_uses_title_attribute_for_clean_titles(fixture_loader):
    adapter = GenericAdapter()
    html = fixture_loader("novelphoenix_toc.html")
    site = adapter.parse_toc(html, base_url=GENERIC_URL)
    assert [c.title for c in site.chapters] == [
        "Chapter 1: The Beginning",
        "Chapter 2: Facing The Villainesses",
        "Chapter 174: Aftermath of the Dance",
    ]
    assert [c.num for c in site.chapters] == [1, 2, 174]
    assert site.chapters[2].url == (
        "https://readhere.example/novel/"
        "my-step-daughters-are-the-villainesses/chapter-174"
    )


def test_generic_next_page_follows_rel_next(fixture_loader):
    adapter = GenericAdapter()
    html = fixture_loader("novelphoenix_toc.html")
    base = "https://readhere.example/eternal/chapters"
    assert adapter.next_page(html, base) == "https://readhere.example/eternal/chapters?page=2"


def test_generic_href_fallback_num(fixture_loader):
    adapter = GenericAdapter()
    html = fixture_loader("novelphoenix_toc.html").replace(
        'title="Chapter 174: Aftermath of the Dance"',
        'title="A Surprise Chapter"',
    ).replace(
        "Chapter 174: Aftermath of the Dance",
        "A Surprise Chapter",
    )
    site = adapter.parse_toc(html, base_url=GENERIC_URL)
    # sin texto numerado, el numero sale del href /chapter-174
    assert any(c.num == 174 for c in site.chapters)


def test_registry_novelphoenix_maps_to_novelfire():
    adapter = get_adapter("https://novelphoenix.com/novel/something")
    assert adapter.name == "novelfire"