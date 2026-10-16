"""Unit tests del adaptador NovelFire (fixtures, sin red)."""

from __future__ import annotations

from novel_cli.core.scraper.sites.novelfire import NovelfireAdapter
from novel_cli.core.services.toc import crawl_toc

BOOK_URL = "https://novelfire.net/book/inner-voice-all-heroines-hear-my-inner-voice"
CHAPTER_BASE = (
    "https://novelfire.net/book/inner-voice-all-heroines-hear-my-inner-voice/chapters"
)
RANGE_BASE = "https://novelphoenix.com/novel/my-step-daughters-are-the-villainesses"


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


def test_next_page_follows_range_pager(fixture_loader):
    """Paginador de novelphoenix.com (.chapter-range-pager, sin rel=next)."""
    adapter = NovelfireAdapter()
    html = fixture_loader("novelfire_range_pager.html")
    base = f"{RANGE_BASE}/chapters"
    assert adapter.next_page(html, base) == f"{base}?page=2"


def test_next_page_range_pager_disabled_is_last(fixture_loader):
    adapter = NovelfireAdapter()
    html = fixture_loader("novelfire_range_pager.html").replace(
        '<a href="?page=2" aria-label="Next chapter range">',
        '<a href="?page=3" aria-label="Next chapter range" aria-disabled="true">',
    )
    base = f"{RANGE_BASE}/chapters"
    assert adapter.next_page(html, base) is None


class _FakeFetcher:
    """Fetcher en memoria: mapea URL -> HTML (sin red)."""

    def __init__(self, pages: dict[str, str]):
        self.pages = pages

    async def fetch_html(self, url: str, *, headers: dict | None = None) -> str:
        return self.pages[url]


def _range_page(nums, *, next_page=None, last=False) -> str:
    links = "".join(
        f'<li><a href="/novel/x/chapter-{n}">Chapter {n}: C{n}</a></li>' for n in nums
    )
    next_link = (
        '<a href="?page={p}" aria-label="Next chapter range"{d}>&#8250;</a>'.format(
            p=next_page, d=' aria-disabled="true"' if last else ""
        )
    )
    return (
        '<html><body><div id="chpagedlist"><ul class="chapter-list">'
        f"{links}</ul><div class=\"chapter-range-pager\">{next_link}"
        "</div></div></body></html>"
    )


async def test_crawl_toc_follows_range_pager(fixture_loader):
    """El crawl recorre las 3 paginas del paginador de rangos."""
    adapter = NovelfireAdapter()
    chapters_url = f"{RANGE_BASE}/chapters"
    pages = {
        RANGE_BASE: "<html><head><title>My Step-Daughters</title></head></html>",
        chapters_url: _range_page([1, 2], next_page=2),
        f"{chapters_url}?page=2": _range_page([3, 4], next_page=3),
        f"{chapters_url}?page=3": _range_page([5], last=True),
    }
    site, listing = await crawl_toc(_FakeFetcher(pages), adapter, RANGE_BASE)
    assert [c.num for c in site.chapters] == [1, 2, 3, 4, 5]
    assert listing == [chapters_url, f"{chapters_url}?page=3"]


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