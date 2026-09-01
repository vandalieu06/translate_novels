"""Unit tests de la descarga async: pool, pacing, resume y manifest."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from novel_cli.core.models.novel import Chapter, NovelMetadata
from novel_cli.core.models.state import Manifest
from novel_cli.core.scraper.fetcher import Pacer
from novel_cli.core.services.download import (
    DownloadError,
    download_chapters,
    format_chapter,
    is_chapter_empty,
    load_chapter,
)
from novel_cli.core.utils.names import chapter_filename

CH_HTML = "<html><body><div id='content'><p>p1</p><p>p2</p></div></body></html>"


class FakeAdapter:
    name = "fake"

    def tocs(self, novel_url: str) -> list[str]:
        return [novel_url]

    def parse_toc(self, html: str, base_url: str):
        from novel_cli.core.models.novel import SiteMetadata

        return SiteMetadata(metadata=NovelMetadata(title="T"), chapters=[])

    def parse_chapter(self, html: str, chapter_url: str) -> list[str]:
        return ["p1", "p2"]

    def next_page(self, html: str, base_url: str) -> str | None:
        return None


class FakeFetcher:
    def __init__(self, html: str = CH_HTML):
        self.html = html
        self.calls: list[str] = []
        self.starts: list[float] = []
        self.fail_urls: set[str] = set()

    async def fetch_html(self, url: str, *, headers: dict | None = None) -> str:
        self.calls.append(url)
        self.starts.append(time.monotonic())
        if url in self.fail_urls:
            from novel_cli.core.scraper.fetcher import FetchError

            raise FetchError(f"failed {url}")
        return self.html

    async def fetch_bytes(self, url: str, *, headers: dict | None = None) -> bytes:
        return b"data"

    async def aclose(self) -> None:
        return None


def make_chapters(n: int) -> list[Chapter]:
    return [
        Chapter(
            num=i,
            title=f"Chapter {i}",
            url=f"https://example.com/chapter/{i}",
            paragraphs=[],
        )
        for i in range(1, n + 1)
    ]


def make_manifest(slug_dir) -> Manifest:
    return Manifest(slug="novela", title="Novela")


@pytest.mark.asyncio
async def test_downloads_all_chapters_and_writes_raw(tmp_path):
    chapters = make_chapters(3)
    fetcher = FakeFetcher()
    manifest = make_manifest(tmp_path)
    await download_chapters(
        fetcher=fetcher,
        adapter=FakeAdapter(),
        metadata=NovelMetadata(title="Novela"),
        chapters=chapters,
        slug_dir=tmp_path,
        manifest=manifest,
        pacer=Pacer(0),
    )
    assert fetcher.calls == [c.url for c in chapters]
    for ch in chapters:
        path = tmp_path / "raw" / chapter_filename(ch.num)
        assert path.exists()
        content = path.read_text(encoding="utf-8")
        assert content.startswith(f"# {ch.title}\n\n")
        assert "p1\n\np2" in content
    assert manifest.chapters_downloaded == 3
    assert manifest.chapters_total == 3
    assert (tmp_path / ".manifest.json").exists()


@pytest.mark.asyncio
async def test_resume_skips_existing_files(tmp_path):
    chapters = make_chapters(3)
    fetcher = FakeFetcher()
    manifest = make_manifest(tmp_path)
    # simular capitulo 2 ya descargado
    raw = tmp_path / "raw"
    raw.mkdir()
    raw.joinpath(chapter_filename(2)).write_text("# Chapter 2\n\np1\n\np2\n", encoding="utf-8")

    await download_chapters(
        fetcher=fetcher,
        adapter=FakeAdapter(),
        metadata=NovelMetadata(title="Novela"),
        chapters=chapters,
        slug_dir=tmp_path,
        manifest=manifest,
        pacer=Pacer(0),
    )
    assert set(fetcher.calls) == {
        "https://example.com/chapter/1",
        "https://example.com/chapter/3",
    }
    assert manifest.chapters_downloaded == 3


@pytest.mark.asyncio
async def test_force_redownloads_all(tmp_path):
    chapters = make_chapters(2)
    fetcher = FakeFetcher()
    manifest = make_manifest(tmp_path)
    raw = tmp_path / "raw"
    raw.mkdir()
    raw.joinpath(chapter_filename(1)).write_text("# old", encoding="utf-8")

    await download_chapters(
        fetcher=fetcher,
        adapter=FakeAdapter(),
        metadata=NovelMetadata(title="Novela"),
        chapters=chapters,
        slug_dir=tmp_path,
        manifest=manifest,
        force=True,
        pacer=Pacer(0),
    )
    assert fetcher.calls == [c.url for c in chapters]
    content = (raw / chapter_filename(1)).read_text(encoding="utf-8")
    assert content.startswith("# Chapter 1")


@pytest.mark.asyncio
async def test_pacing_min_interval(tmp_path):
    chapters = make_chapters(3)
    fetcher = FakeFetcher()
    manifest = make_manifest(tmp_path)
    await download_chapters(
        fetcher=fetcher,
        adapter=FakeAdapter(),
        metadata=NovelMetadata(title="Novela"),
        chapters=chapters,
        slug_dir=tmp_path,
        manifest=manifest,
        concurrency=4,
        pacer=Pacer(300),
    )
    assert len(fetcher.starts) == 3
    gaps = [b - a for a, b in zip(fetcher.starts, fetcher.starts[1:], strict=False)]
    assert min(gaps) >= 0.28


@pytest.mark.asyncio
async def test_concurrency_limited(tmp_path):
    chapters = make_chapters(6)
    fetcher = FakeFetcher()
    manifest = make_manifest(tmp_path)

    max_active = 0
    active = 0
    lock = asyncio.Lock()
    original_fetch = fetcher.fetch_html

    async def slow_fetch(url: str, *, headers: dict | None = None) -> str:
        nonlocal max_active, active
        async with lock:
            active += 1
            max_active = max(max_active, active)
        await asyncio.sleep(0.01)
        async with lock:
            active -= 1
        return await original_fetch(url, headers=headers)

    fetcher.fetch_html = slow_fetch  # type: ignore[method-assign]
    await download_chapters(
        fetcher=fetcher,
        adapter=FakeAdapter(),
        metadata=NovelMetadata(title="Novela"),
        chapters=chapters,
        slug_dir=tmp_path,
        manifest=manifest,
        concurrency=2,
        pacer=Pacer(0),
    )
    assert max_active <= 2
    assert manifest.chapters_downloaded == 6


@pytest.mark.asyncio
async def test_failure_raises_download_error(tmp_path):
    chapters = make_chapters(2)
    fetcher = FakeFetcher()
    fetcher.fail_urls = {"https://example.com/chapter/2"}
    manifest = make_manifest(tmp_path)
    with pytest.raises(DownloadError):
        await download_chapters(
            fetcher=fetcher,
            adapter=FakeAdapter(),
            metadata=NovelMetadata(title="Novela"),
            chapters=chapters,
            slug_dir=tmp_path,
            manifest=manifest,
            pacer=Pacer(0),
        )
    # el capitulo 1 quedo guardado para reanudar
    assert (tmp_path / "raw" / chapter_filename(1)).exists()


@pytest.mark.asyncio
async def test_all_downloaded_skips_fetch(tmp_path):
    chapters = make_chapters(2)
    fetcher = FakeFetcher()
    manifest = make_manifest(tmp_path)
    raw = tmp_path / "raw"
    raw.mkdir()
    for ch in chapters:
        raw.joinpath(chapter_filename(ch.num)).write_text(
            f"# {ch.title}\n\np\n", encoding="utf-8"
        )
    await download_chapters(
        fetcher=fetcher,
        adapter=FakeAdapter(),
        metadata=NovelMetadata(title="Novela"),
        chapters=chapters,
        slug_dir=tmp_path,
        manifest=manifest,
        pacer=Pacer(0),
    )
    assert fetcher.calls == []
    assert manifest.chapters_downloaded == 2


@pytest.mark.asyncio
async def test_progress_callback(tmp_path):
    chapters = make_chapters(3)
    fetcher = FakeFetcher()
    manifest = make_manifest(tmp_path)
    events: list[tuple[int, int]] = []

    await download_chapters(
        fetcher=fetcher,
        adapter=FakeAdapter(),
        metadata=NovelMetadata(title="Novela"),
        chapters=chapters,
        slug_dir=tmp_path,
        manifest=manifest,
        pacer=Pacer(0),
        on_progress=lambda done, total: events.append((done, total)),
    )
    assert events[-1] == (3, 3)
    assert [d for d, _ in events] == [1, 2, 3]


def test_load_chapter_roundtrip(tmp_path):
    ch = Chapter(
        num=42,
        title="Chapter 42",
        url="https://example.com/42",
        paragraphs=["a", "b", "c"],
    )
    path = tmp_path / "0042.md"
    path.write_text(format_chapter(ch, ch.paragraphs), encoding="utf-8")
    loaded = load_chapter(path, 42, ch.url)
    assert loaded.num == 42
    assert loaded.title == "Chapter 42"
    assert loaded.paragraphs == ["a", "b", "c"]


def test_load_chapter_without_header(tmp_path):
    path = tmp_path / "0001.md"
    path.write_text("p1\n\np2", encoding="utf-8")
    loaded = load_chapter(path, 1, "https://example.com/1")
    assert loaded.title == ""
    assert loaded.paragraphs == ["p1", "p2"]


@pytest.mark.asyncio
async def test_download_with_respx_http_fetcher(tmp_path):
    chapters = make_chapters(2)
    manifest = make_manifest(tmp_path)
    with respx.mock() as router:
        for ch in chapters:
            router.get(ch.url).mock(return_value=httpx.Response(200, text=CH_HTML))
        from novel_cli.core.scraper.fetcher import HttpFetcher

        fetcher = HttpFetcher(pacer=Pacer(0))
        try:
            await download_chapters(
                fetcher=fetcher,
                adapter=FakeAdapter(),
                metadata=NovelMetadata(title="Novela"),
                chapters=chapters,
                slug_dir=tmp_path,
                manifest=manifest,
                pacer=Pacer(0),
            )
        finally:
            await fetcher.aclose()
    assert manifest.chapters_downloaded == 2


def test_is_chapter_empty():
    assert is_chapter_empty([])
    assert is_chapter_empty([""])
    assert is_chapter_empty(["   ", "\n"])
    assert not is_chapter_empty(["text"])
    assert not is_chapter_empty(["", "text"])


@pytest.mark.asyncio
async def test_empty_chapter_retried_and_resolved(tmp_path):
    """Un capitulo vacio al primer fetch se reintenta y se resuelve."""
    chapters = make_chapters(2)

    class EmptyThenOkAdapter:
        name = "fake"
        calls: dict[str, int] = {}

        def parse_chapter(self, html: str, chapter_url: str) -> list[str]:
            self.calls[chapter_url] = self.calls.get(chapter_url, 0) + 1
            if self.calls[chapter_url] == 1:
                return []
            return ["p1", "p2"]

    adapter = EmptyThenOkAdapter()
    manifest = make_manifest(tmp_path)
    await download_chapters(
        fetcher=FakeFetcher(),
        adapter=adapter,
        metadata=NovelMetadata(title="Novela"),
        chapters=chapters,
        slug_dir=tmp_path,
        manifest=manifest,
        pacer=Pacer(0),
        empty_retries=2,
    )
    # el capitulo 1 quedo resuelto tras el reintento
    content = (tmp_path / "raw" / chapter_filename(1)).read_text(encoding="utf-8")
    assert "p1" in content
    assert manifest.chapters_downloaded == 2
    assert manifest.chapters_empty == 0


@pytest.mark.asyncio
async def test_still_empty_chapter_reported_not_downloaded(tmp_path):
    """Un capitulo vacio persistente se reporta y no cuenta como descargado."""
    chapters = make_chapters(2)

    class AlwaysEmptyAdapter:
        name = "fake"

        def parse_chapter(self, html: str, chapter_url: str) -> list[str]:
            return []

    manifest = make_manifest(tmp_path)
    await download_chapters(
        fetcher=FakeFetcher(),
        adapter=AlwaysEmptyAdapter(),
        metadata=NovelMetadata(title="Novela"),
        chapters=chapters,
        slug_dir=tmp_path,
        manifest=manifest,
        pacer=Pacer(0),
        empty_retries=1,
    )
    assert manifest.chapters_empty == 2
    assert manifest.chapters_empty_nums == [1, 2]
    assert manifest.chapters_downloaded == 0


@pytest.mark.asyncio
async def test_empty_existing_file_re_downloaded(tmp_path):
    """Un archivo vacio en disco se vuelve a descargar (no cuenta como hecho)."""
    chapters = make_chapters(2)
    raw = tmp_path / "raw"
    raw.mkdir()
    raw.joinpath(chapter_filename(1)).write_text("# Chapter 1\n\n", encoding="utf-8")

    fetcher = FakeFetcher()
    manifest = make_manifest(tmp_path)
    await download_chapters(
        fetcher=fetcher,
        adapter=FakeAdapter(),
        metadata=NovelMetadata(title="Novela"),
        chapters=chapters,
        slug_dir=tmp_path,
        manifest=manifest,
        pacer=Pacer(0),
    )
    # el 1 vacio se volvio a descargar y ahora tiene contenido
    assert set(fetcher.calls) == {
        "https://example.com/chapter/1",
        "https://example.com/chapter/2",
    }
    content = (raw / chapter_filename(1)).read_text(encoding="utf-8")
    assert "p1" in content
    assert manifest.chapters_downloaded == 2