"""Unit tests del adaptador NovelFire (fixtures, sin red)."""

from __future__ import annotations

from novel_cli.core.scraper.sites.novelfire import NovelfireAdapter

BOOK_URL = "https://novelfire.net/book/inner-voice-all-heroines-hear-my-inner-voice"
CHAPTER_BASE = (
    "https://novelfire.net/book/inner-voice-all-heroines-hear-my-inner-voice/chapters"
)


def test_tocs_include_cover_and_chapters_page():
    adapter = NovelfireAdapter()
    assert adapter.tocs(BOOK_URL) == [BOOK_URL, f"{BOOK_URL}/chapters"]


def test_parse_toc_cover_page_extracts_title_and_cover(fixture_loader):
    adapter = NovelfireAdapter()
    html = fixture_loader("novelfire_cover.html")
    site = adapter.parse_toc(html, base_url=BOOK_URL)
    assert site.metadata.title == "Inner Voice: All Heroines Hear My Inner Voice"
    assert site.metadata.cover_url == "https://img.novelfire.net/cover.jpg"
    assert site.metadata.source_url == BOOK_URL
    assert site.chapters == []


def test_parse_toc_chapters_page_extracts_chapters(fixture_loader):
    adapter = NovelfireAdapter()
    html = fixture_loader("novelfire_toc.html")
    site = adapter.parse_toc(html, base_url=CHAPTER_BASE)
    assert len(site.chapters) == 3
    first = site.chapters[0]
    assert first.num == 1
    assert first.title == "Chapter 1: Beginning"
    assert first.url == (
        "https://novelfire.net/book/inner-voice-all-heroines-hear-my-inner-voice/chapter/1"
    )
    assert [c.num for c in site.chapters] == [1, 2, 3]


def test_next_page_enabled(fixture_loader):
    adapter = NovelfireAdapter()
    html = fixture_loader("novelfire_toc.html")
    assert adapter.next_page(html, CHAPTER_BASE) == f"{CHAPTER_BASE}?page=2"


def test_next_page_none_when_no_pagination(fixture_loader):
    adapter = NovelfireAdapter()
    html = fixture_loader("novelfire_cover.html")
    assert adapter.next_page(html, BOOK_URL) is None


def test_parse_chapter_paragraphs_in_order(fixture_loader):
    adapter = NovelfireAdapter()
    html = fixture_loader("novelfire_chapter.html")
    paragraphs = adapter.parse_chapter(html, chapter_url=CHAPTER_BASE)
    assert paragraphs == [
        "First paragraph of the story.",
        "Second paragraph, with more text here.",
        "Third and last paragraph.",
    ]


def test_parse_chapter_skips_empty_paragraphs(fixture_loader):
    adapter = NovelfireAdapter()
    html = fixture_loader("novelfire_chapter.html").replace(
        "<p>Third and last paragraph.</p>", "<p>   </p>"
    )
    paragraphs = adapter.parse_chapter(html, chapter_url=CHAPTER_BASE)
    assert len(paragraphs) == 2