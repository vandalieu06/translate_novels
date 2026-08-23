"""Unit tests del pipeline completo (fetcher + translator fake, sin red)."""

from __future__ import annotations

import io
import zipfile

import pytest

from novel_cli.core.scraper.fetcher import Pacer
from novel_cli.core.scraper.sites.generic import GenericAdapter
from novel_cli.core.services.pipeline import PipelineError, run_pipeline

NOVEL_URL = "https://readhere.example/eternal-journey"
CHAPTER_HTML = (
    "<html><body><article>"
    "<p>Hello there.</p><p>Goodbye now.</p>"
    "</article></body></html>"
)


class FakeFetcher:
    def __init__(self, toc_html: str):
        self.toc_html = toc_html
        self.toc_calls = 0
        self.chapter_calls = 0
        self.bytes_calls = 0

    async def fetch_html(self, url: str, *, headers: dict | None = None) -> str:
        if url == NOVEL_URL:
            self.toc_calls += 1
            return self.toc_html
        self.chapter_calls += 1
        return CHAPTER_HTML

    async def fetch_bytes(self, url: str, *, headers: dict | None = None) -> bytes:
        self.bytes_calls += 1
        return b"fakecover"

    async def aclose(self) -> None:
        return None


class FakeTranslator:
    def __init__(self):
        self.calls = 0

    async def translate_text(
        self, text: str, *, source: str = "auto", target: str = "es"
    ) -> str:
        self.calls += 1
        return "\n".join(f"ES:{line}" for line in text.split("\n"))


def run_kwargs(
    tmp_path,
    fetcher,
    *,
    translate=False,
    resume=True,
    force=False,
    volume_size=None,
    translator=None,
):
    return {
        "url": NOVEL_URL,
        "output_dir": tmp_path,
        "volume_size": volume_size,
        "translate": translate,
        "resume": resume,
        "force": force,
        "concurrency": 2,
        "fetcher": fetcher,
        "adapter": GenericAdapter(),
        "translator": translator,
        "pacer": Pacer(0),
    }


def read_epub(path) -> str:
    with zipfile.ZipFile(io.BytesIO(path.read_bytes())) as zf:
        return zf.read("EPUB/chapter0001.xhtml").decode("utf-8")


@pytest.mark.asyncio
async def test_pipeline_full_flow_with_translate(tmp_path, fixture_loader):
    fetcher = FakeFetcher(fixture_loader("generic_toc.html"))
    translator = FakeTranslator()
    manifest = await run_pipeline(
        **run_kwargs(
            tmp_path, fetcher, translate=True, translator=translator
        )
    )

    assert manifest.slug == "the-eternal-journey"
    assert manifest.chapters_total == 4
    assert manifest.chapters_downloaded == 4
    assert manifest.chapters_translated == 4
    assert manifest.translated is True
    assert manifest.volume_size is None
    assert manifest.cover_path == "cover.jpg"
    assert manifest.epub_original == ["The Eternal Journey.epub"]
    assert manifest.epub_translated == ["The Eternal Journey (ES).epub"]

    slug_dir = tmp_path / "the-eternal-journey"
    for i in range(1, 5):
        assert (slug_dir / "raw" / f"{i:04d}.md").exists()
        assert (slug_dir / "translated" / f"{i:04d}.md").exists()
    assert (slug_dir / "cover.jpg").exists()
    assert (slug_dir / "The Eternal Journey.epub").exists()
    assert (slug_dir / "The Eternal Journey (ES).epub").exists()

    assert "<p>Hello there.</p>" in read_epub(slug_dir / "The Eternal Journey.epub")
    assert "<p>ES:Hello there.</p>" in read_epub(
        slug_dir / "The Eternal Journey (ES).epub"
    )
    assert translator.calls == 4


@pytest.mark.asyncio
async def test_pipeline_without_translate(tmp_path, fixture_loader):
    fetcher = FakeFetcher(fixture_loader("generic_toc.html"))
    manifest = await run_pipeline(**run_kwargs(tmp_path, fetcher, translate=False))
    assert manifest.translated is False
    assert manifest.chapters_translated == 0
    assert manifest.epub_translated == []
    slug_dir = tmp_path / "the-eternal-journey"
    assert not (slug_dir / "translated").exists()


@pytest.mark.asyncio
async def test_pipeline_volumes(tmp_path, fixture_loader):
    fetcher = FakeFetcher(fixture_loader("generic_toc.html"))
    manifest = await run_pipeline(
        **run_kwargs(tmp_path, fetcher, volume_size=2)
    )
    assert manifest.epub_original == [
        "The Eternal Journey 1-2.epub",
        "The Eternal Journey 3-4.epub",
    ]
    slug_dir = tmp_path / "the-eternal-journey"
    assert (slug_dir / "The Eternal Journey 1-2.epub").exists()
    assert (slug_dir / "The Eternal Journey 3-4.epub").exists()


@pytest.mark.asyncio
async def test_pipeline_resume_skips_download_and_translate(tmp_path, fixture_loader):
    toc = fixture_loader("generic_toc.html")

    first = FakeFetcher(toc)
    await run_pipeline(**run_kwargs(tmp_path, first, translate=True, translator=FakeTranslator()))
    assert first.chapter_calls == 4

    second = FakeFetcher(toc)
    translator2 = FakeTranslator()
    manifest2 = await run_pipeline(
        **run_kwargs(tmp_path, second, translate=True, translator=translator2)
    )
    assert second.toc_calls == 1
    assert second.chapter_calls == 0
    assert translator2.calls == 0
    assert manifest2.epub_original == ["The Eternal Journey.epub"]
    assert manifest2.epub_translated == ["The Eternal Journey (ES).epub"]


@pytest.mark.asyncio
async def test_pipeline_force_redownloads_and_retranslates(tmp_path, fixture_loader):
    toc = fixture_loader("generic_toc.html")

    first = FakeFetcher(toc)
    await run_pipeline(**run_kwargs(tmp_path, first, translate=True, translator=FakeTranslator()))

    second = FakeFetcher(toc)
    translator2 = FakeTranslator()
    manifest2 = await run_pipeline(
        **run_kwargs(tmp_path, second, translate=True, translator=translator2, force=True)
    )
    assert second.chapter_calls == 4
    assert translator2.calls == 4
    assert manifest2.chapters_downloaded == 4


@pytest.mark.asyncio
async def test_pipeline_no_chapters_raises(tmp_path, fixture_loader):
    fetcher = FakeFetcher(fixture_loader("generic_no_toc.html"))
    with pytest.raises(PipelineError):
        await run_pipeline(**run_kwargs(tmp_path, fetcher))


@pytest.mark.asyncio
async def test_pipeline_translate_without_translator_raises(tmp_path, fixture_loader):
    fetcher = FakeFetcher(fixture_loader("generic_toc.html"))
    with pytest.raises(PipelineError):
        await run_pipeline(**run_kwargs(tmp_path, fetcher, translate=True, translator=None))