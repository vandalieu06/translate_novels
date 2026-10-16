"""Unit tests de la cache del TOC (sin red, fetcher/adapter falsos)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from novel_cli.core import config
from novel_cli.core.models.novel import Chapter, NovelMetadata, SiteMetadata
from novel_cli.core.models.state import Manifest
from novel_cli.core.models.toc import CachedChapter, TocCache, make_cache
from novel_cli.core.services.pipeline import _resolve_toc
from novel_cli.core.services.toc import crawl_toc, site_from_cache, toc_changed

URL = "https://site.example/novel"
LISTING = f"{URL}/chapters"
LISTING_2 = f"{URL}/chapters?page=2"


class _FakeSite:
    def __init__(self) -> None:
        self.title = "Test Novel"
        self.pages: dict[str, list[tuple[int, str]]] = {}
        self.next: dict[str, str | None] = {}

    def add_page(self, url: str, chapters: list[tuple[int, str]], next_url=None) -> None:
        self.pages[url] = chapters
        self.next[url] = next_url


class _FakeFetcher:
    def __init__(self, site: _FakeSite) -> None:
        self.site = site
        self.fetches: list[str] = []

    async def fetch_html(self, url: str, *, headers: dict | None = None) -> str:
        self.fetches.append(url)
        return f"<html>{url}</html>"

    async def fetch_bytes(self, url: str, *, headers: dict | None = None) -> bytes:
        return b"cover"

    async def aclose(self) -> None:
        return None


class _FakeAdapter:
    name = "fake"

    def __init__(self, site: _FakeSite) -> None:
        self.site = site

    def tocs(self, novel_url: str) -> list[str]:
        return [f"{novel_url}/chapters"]

    def parse_toc(self, html: str, base_url: str) -> SiteMetadata:
        chapters = [
            Chapter(num=num, title=f"Ch {num}", url=chap_url)
            for num, chap_url in self.site.pages.get(base_url, [])
        ]
        return SiteMetadata(
            metadata=NovelMetadata(title=self.site.title, source_url=base_url),
            chapters=chapters,
        )

    def parse_chapter(self, html: str, chapter_url: str) -> list[str]:
        return ["Text"]

    def next_page(self, html: str, base_url: str) -> str | None:
        return self.site.next.get(base_url)


def _two_page_site() -> _FakeSite:
    site = _FakeSite()
    site.add_page(LISTING, [(1, "u1"), (2, "u2"), (3, "u3")], LISTING_2)
    site.add_page(LISTING_2, [(4, "u4"), (5, "u5"), (6, "u6")], None)
    return site


# --- Modelo / cache --------------------------------------------------------


def test_toc_cache_roundtrip(tmp_path):
    cache = TocCache(
        source_url=URL,
        fetched_at=datetime.now(UTC).isoformat(),
        listing_pages=[LISTING],
        chapters=[CachedChapter(num=1, title="Ch 1", url="u1")],
    )
    cache.save(tmp_path)
    loaded = TocCache.load(tmp_path)
    assert loaded is not None
    assert loaded.source_url == URL
    assert loaded.max_num() == 1
    assert (tmp_path / ".toc.json").exists()


def test_toc_cache_load_missing_and_invalid(tmp_path):
    assert TocCache.load(tmp_path) is None
    (tmp_path / ".toc.json").write_text("{no-json", encoding="utf-8")
    assert TocCache.load(tmp_path) is None


def test_make_cache_and_site_from_cache():
    manifest = Manifest(
        slug="novela", title="Novela", author="A", source_url=URL, cover_path="c.jpg"
    )
    chapters = [Chapter(num=1, title="Ch 1", url="u1")]
    cache = make_cache(URL, chapters, [LISTING])
    assert cache.max_num() == 1
    site = site_from_cache(manifest, cache)
    assert site.metadata.title == "Novela"
    assert [c.url for c in site.chapters] == ["u1"]


def test_toc_ttl_env(monkeypatch):
    monkeypatch.delenv("NOVEL_TOC_TTL_HOURS", raising=False)
    assert config.toc_ttl_seconds() == config.DEFAULT_TOC_TTL_HOURS * 3600
    monkeypatch.setenv("NOVEL_TOC_TTL_HOURS", "0")
    assert config.toc_ttl_seconds() == 0
    monkeypatch.setenv("NOVEL_TOC_TTL_HOURS", "abc")
    assert config.toc_ttl_seconds() == config.DEFAULT_TOC_TTL_HOURS * 3600


# --- crawl / peek ----------------------------------------------------------


async def test_crawl_toc_merges_and_records_listing_pages():
    site = _two_page_site()
    fetcher = _FakeFetcher(site)
    site_meta, listing_pages = await crawl_toc(fetcher, _FakeAdapter(site), URL)
    assert [c.num for c in site_meta.chapters] == [1, 2, 3, 4, 5, 6]
    assert listing_pages == [LISTING, LISTING_2]
    assert fetcher.fetches == [LISTING, LISTING_2]


async def _crawl_cache(site: _FakeSite, listing_pages: list[str]) -> TocCache:
    site_meta, _ = await crawl_toc(_FakeFetcher(site), _FakeAdapter(site), URL)
    return make_cache(URL, site_meta.chapters, listing_pages)


async def test_toc_changed_false_without_news():
    site = _two_page_site()
    cache = await _crawl_cache(site, [LISTING, LISTING_2])
    fetcher = _FakeFetcher(site)
    assert await toc_changed(fetcher, _FakeAdapter(site), cache) is False
    assert fetcher.fetches == [LISTING, LISTING_2]


async def test_toc_changed_true_on_new_chapter():
    site = _two_page_site()
    cache = await _crawl_cache(site, [LISTING, LISTING_2])
    site.add_page(LISTING_2, [(4, "u4"), (5, "u5"), (6, "u6"), (7, "u7")], None)
    assert await toc_changed(_FakeFetcher(site), _FakeAdapter(site), cache) is True


async def test_toc_changed_true_on_new_page():
    site = _FakeSite()
    site.add_page(LISTING, [(1, "u1"), (2, "u2")], None)
    cache = await _crawl_cache(site, [LISTING])
    site.next[LISTING] = LISTING_2
    assert await toc_changed(_FakeFetcher(site), _FakeAdapter(site), cache) is True


# --- Resolucion en el pipeline --------------------------------------------


def _warm(tmp_path, fetched_at: str, listing_pages: list[str], chapters):
    url = URL
    slug_dir = tmp_path / "novela"
    slug_dir.mkdir(exist_ok=True)
    Manifest(slug="novela", title="Novela", source_url=url).save(slug_dir)
    TocCache(
        source_url=url,
        fetched_at=fetched_at,
        listing_pages=listing_pages,
        chapters=[CachedChapter(num=n, title=f"Ch {n}", url=u) for n, u in chapters],
    ).save(slug_dir)
    return slug_dir


async def test_resolve_toc_uses_fresh_cache(tmp_path):
    _warm(
        tmp_path,
        datetime.now(UTC).isoformat(),
        [LISTING, LISTING_2],
        [(1, "u1"), (2, "u2")],
    )
    site = _two_page_site()
    fetcher = _FakeFetcher(site)
    result, _pages, crawled = await _resolve_toc(
        fetcher=fetcher,
        adapter=_FakeAdapter(site),
        url=URL,
        output_dir=tmp_path,
        resume=True,
        force=False,
        refresh_toc=False,
    )
    assert crawled is False
    assert [c.num for c in result.chapters] == [1, 2]
    assert fetcher.fetches == []


async def test_resolve_toc_stale_peek_no_news(tmp_path):
    old = (datetime.now(UTC) - timedelta(hours=10)).isoformat()
    _warm(tmp_path, old, [LISTING, LISTING_2], [(1, "u1"), (6, "u6")])
    site = _two_page_site()
    fetcher = _FakeFetcher(site)
    _result, _pages, crawled = await _resolve_toc(
        fetcher=fetcher,
        adapter=_FakeAdapter(site),
        url=URL,
        output_dir=tmp_path,
        resume=True,
        force=False,
        refresh_toc=False,
    )
    assert crawled is False
    assert fetcher.fetches == [LISTING, LISTING_2]  # solo el peek
    assert TocCache.load(tmp_path / "novela").age_seconds() < 5


async def test_resolve_toc_stale_with_news_crawls(tmp_path):
    old = (datetime.now(UTC) - timedelta(hours=10)).isoformat()
    _warm(tmp_path, old, [LISTING, LISTING_2], [(1, "u1"), (2, "u2")])
    site = _two_page_site()
    fetcher = _FakeFetcher(site)
    _result, _pages, crawled = await _resolve_toc(
        fetcher=fetcher,
        adapter=_FakeAdapter(site),
        url=URL,
        output_dir=tmp_path,
        resume=True,
        force=False,
        refresh_toc=False,
    )
    assert crawled is True
    assert LISTING in fetcher.fetches and LISTING_2 in fetcher.fetches


async def test_resolve_toc_force_and_refresh_bypass_cache(tmp_path):
    _warm(tmp_path, datetime.now(UTC).isoformat(), [LISTING], [(1, "u1")])
    site = _two_page_site()
    for kwargs in ({"force": True, "refresh_toc": False}, {"force": False, "refresh_toc": True}):
        fetcher = _FakeFetcher(site)
        _result, _pages, crawled = await _resolve_toc(
            fetcher=fetcher,
            adapter=_FakeAdapter(site),
            url=URL,
            output_dir=tmp_path,
            resume=True,
            **kwargs,
        )
        assert crawled is True
        assert fetcher.fetches == [LISTING, LISTING_2]


async def test_resolve_toc_peek_toc_bypasses_fresh_cache(tmp_path):
    """peek_toc=True fuerza el peek aunque la cache este fresca (y crawlea si hay novedades)."""
    _warm(
        tmp_path,
        datetime.now(UTC).isoformat(),
        [LISTING, LISTING_2],
        [(1, "u1"), (2, "u2")],
    )
    site = _two_page_site()
    fetcher = _FakeFetcher(site)
    result, _pages, crawled = await _resolve_toc(
        fetcher=fetcher,
        adapter=_FakeAdapter(site),
        url=URL,
        output_dir=tmp_path,
        resume=True,
        force=False,
        refresh_toc=False,
        peek_toc=True,
    )
    assert crawled is True
    assert [c.num for c in result.chapters] == [1, 2, 3, 4, 5, 6]


async def test_resolve_toc_peek_toc_no_news_uses_cache(tmp_path):
    """Con peek_toc, si el peek no ve novedades se reutiliza la cache (solo 2 peticiones)."""
    _warm(
        tmp_path,
        datetime.now(UTC).isoformat(),
        [LISTING, LISTING_2],
        [(1, "u1"), (6, "u6")],
    )
    site = _two_page_site()
    fetcher = _FakeFetcher(site)
    result, _pages, crawled = await _resolve_toc(
        fetcher=fetcher,
        adapter=_FakeAdapter(site),
        url=URL,
        output_dir=tmp_path,
        resume=True,
        force=False,
        refresh_toc=False,
        peek_toc=True,
    )
    assert crawled is False
    assert [c.num for c in result.chapters] == [1, 6]
    assert fetcher.fetches == [LISTING, LISTING_2]
