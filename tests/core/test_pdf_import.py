"""Unit tests de la importacion de PDFs (convert_pdf/run_pdf_pipeline mockeados)."""

from __future__ import annotations

from pathlib import Path

import pytest

from novel_cli.core.models.novel import Chapter
from novel_cli.core.models.state import Manifest
from novel_cli.core.services.pdf_import import (
    PdfImport,
    PdfImportError,
    convert_pdf,
    run_pdf_pipeline,
    save_chapters,
)
from novel_cli.core.services.pipeline import rebuild_volumes


class FakeTranslator:
    def __init__(self):
        self.calls = 0

    async def translate_text(
        self, text: str, *, source: str = "auto", target: str = "es"
    ) -> str:
        self.calls += 1
        return "\n".join(f"ES:{line}" for line in text.split("\n"))


def make_import(tmp_path: Path, *, title: str = "Sample Novel") -> PdfImport:
    workdir = tmp_path / "work"
    workdir.mkdir(parents=True, exist_ok=True)
    epub = workdir / f"{title}.epub"
    epub.write_bytes(b"fake-epub-original")
    chapters = [
        Chapter(num=1, title="Chapter 1", url="", paragraphs=["Hello world."]),
        Chapter(num=2, title="Chapter 2", url="", paragraphs=["Second chapter."]),
    ]
    return PdfImport(
        title=title,
        author="Author",
        language="en",
        chapters=chapters,
        epub_path=epub,
        cover_path=None,
        docx_path=workdir / "sample.docx",
    )


def test_save_chapters_writes_raw(tmp_path: Path) -> None:
    slug_dir = tmp_path / "novela"
    chapters = [
        Chapter(num=1, title="One", url="", paragraphs=["p1", "p2"]),
        Chapter(num=2, title="Two", url="", paragraphs=["p3"]),
    ]
    save_chapters(slug_dir, chapters)
    assert (slug_dir / "raw" / "0001.md").read_text(encoding="utf-8") == (
        "# One\n\np1\n\np2\n"
    )
    assert (slug_dir / "raw" / "0002.md").exists()


def test_convert_pdf_maps_chapters(tmp_path: Path, monkeypatch) -> None:
    epub = tmp_path / "work" / "Sample Novel.epub"
    epub.parent.mkdir(parents=True, exist_ok=True)
    epub.write_bytes(b"fake-epub-original")
    docx = tmp_path / "work" / "sample.docx"
    docx.write_bytes(b"fake-docx")

    class FakeChapter:
        title = "Chapter 1"
        paragraphs = ["Hello world."]

    class FakeReport:
        title = "Sample Novel"
        author = "Author"
        language = "en"
        output_epub = epub
        cover_path = None
        docx_path = docx

    monkeypatch.setattr(
        "novel_cli.core.services.pdf_import.pdf_to_epub_run",
        lambda options, progress=None: FakeReport(),
    )
    monkeypatch.setattr(
        "novel_cli.core.services.pdf_import.extract_docx_chapters",
        lambda path, *, fallback_title="Book": [FakeChapter()],
    )

    result = convert_pdf(tmp_path / "in.pdf", tmp_path / "work")
    assert result.title == "Sample Novel"
    assert result.author == "Author"
    assert result.language == "en"
    assert result.chapters[0].num == 1
    assert result.chapters[0].title == "Chapter 1"
    assert result.chapters[0].paragraphs == ["Hello world."]
    assert result.epub_path == epub


@pytest.mark.asyncio
async def test_run_pdf_pipeline_with_translate(tmp_path: Path, monkeypatch) -> None:
    fake = make_import(tmp_path)
    monkeypatch.setattr(
        "novel_cli.core.services.pdf_import.convert_pdf",
        lambda pdf_path, workdir, **kw: fake,
    )
    pdf_file = tmp_path / "source.pdf"
    pdf_file.write_bytes(b"%PDF-fake")

    manifest = await run_pdf_pipeline(
        pdf_path=pdf_file,
        output_dir=tmp_path,
        source_language="en",
        translate=True,
        target_language="es",
        volume_size=None,
        translator=FakeTranslator(),
    )

    slug_dir = tmp_path / "sample-novel"
    assert manifest.slug == "sample-novel"
    assert manifest.source_pdf == "source.pdf"
    assert manifest.language_code == "en"
    assert manifest.chapters_total == 2
    assert manifest.epub_original == ["Sample Novel.epub"]
    assert manifest.epub_translated == ["Sample Novel (ES).epub"]
    assert manifest.translated is True
    assert manifest.translated_language == "es"

    assert (slug_dir / "source.pdf").read_bytes() == b"%PDF-fake"
    assert (slug_dir / "Sample Novel.epub").read_bytes() == b"fake-epub-original"
    assert (slug_dir / "Sample Novel (ES).epub").exists()
    for i in (1, 2):
        assert (slug_dir / "raw" / f"{i:04d}.md").exists()
        assert (slug_dir / "translated" / f"{i:04d}.md").exists()


@pytest.mark.asyncio
async def test_run_pdf_pipeline_skips_translate_when_same_language(
    tmp_path: Path, monkeypatch
) -> None:
    fake = make_import(tmp_path)
    monkeypatch.setattr(
        "novel_cli.core.services.pdf_import.convert_pdf",
        lambda pdf_path, workdir, **kw: fake,
    )
    pdf_file = tmp_path / "source.pdf"
    pdf_file.write_bytes(b"%PDF-fake")

    manifest = await run_pdf_pipeline(
        pdf_path=pdf_file,
        output_dir=tmp_path,
        source_language="en",
        translate=True,
        target_language="en",
        volume_size=None,
        translator=FakeTranslator(),
    )
    assert manifest.translated is False
    assert manifest.epub_translated == []
    assert not (tmp_path / "sample-novel" / "translated").exists()


@pytest.mark.asyncio
async def test_run_pdf_pipeline_requires_translator(tmp_path: Path, monkeypatch) -> None:
    fake = make_import(tmp_path)
    monkeypatch.setattr(
        "novel_cli.core.services.pdf_import.convert_pdf",
        lambda pdf_path, workdir, **kw: fake,
    )
    pdf_file = tmp_path / "source.pdf"
    pdf_file.write_bytes(b"%PDF-fake")

    with pytest.raises(PdfImportError):
        await run_pdf_pipeline(
            pdf_path=pdf_file,
            output_dir=tmp_path,
            source_language="en",
            translate=True,
            target_language="es",
            volume_size=None,
            translator=None,
        )


@pytest.mark.asyncio
async def test_run_pdf_pipeline_missing_pdf(tmp_path: Path) -> None:
    with pytest.raises(PdfImportError):
        await run_pdf_pipeline(
            pdf_path=tmp_path / "missing.pdf",
            output_dir=tmp_path,
            source_language="en",
            translate=False,
            target_language=None,
            volume_size=None,
            translator=None,
        )


@pytest.mark.asyncio
async def test_run_pdf_pipeline_copies_cover(tmp_path: Path, monkeypatch) -> None:
    fake = make_import(tmp_path)
    fake.cover_path = tmp_path / "work" / "cover.png"
    fake.cover_path.write_bytes(b"png")
    monkeypatch.setattr(
        "novel_cli.core.services.pdf_import.convert_pdf",
        lambda pdf_path, workdir, **kw: fake,
    )
    pdf_file = tmp_path / "source.pdf"
    pdf_file.write_bytes(b"%PDF-fake")

    manifest = await run_pdf_pipeline(
        pdf_path=pdf_file,
        output_dir=tmp_path,
        source_language="en",
        translate=False,
        target_language=None,
        volume_size=None,
        translator=None,
    )
    slug_dir = tmp_path / "sample-novel"
    assert manifest.cover_path == "cover.png"
    assert (slug_dir / "cover.png").read_bytes() == b"png"


def test_rebuild_volumes_pdf_preserves_original(tmp_path: Path) -> None:
    slug_dir = tmp_path / "sample-novel"
    slug_dir.mkdir()
    Manifest(
        slug="sample-novel",
        title="Sample Novel",
        source_url="",
        source_pdf="source.pdf",
        language_code="en",
        translated=True,
        volume_size=None,
        epub_original=["Sample Novel.epub"],
        chapters_total=2,
        chapters_downloaded=2,
        chapters_translated=2,
    ).save(slug_dir)
    (slug_dir / "Sample Novel.epub").write_bytes(b"rich-original")
    raw = slug_dir / "raw"
    raw.mkdir()
    for i in (1, 2):
        raw.joinpath(f"{i:04d}.md").write_text(
            f"# Chapter {i}\n\nContent {i}\n", encoding="utf-8"
        )
    translated = slug_dir / "translated"
    translated.mkdir()
    for i in (1, 2):
        translated.joinpath(f"{i:04d}.md").write_text(
            f"# Chapter {i}\n\nTraduccion {i}\n", encoding="utf-8"
        )

    manifest = rebuild_volumes(slug_dir, 2)

    # El original rico de pdf-to-epub se conserva intacto.
    assert manifest.epub_original == ["Sample Novel.epub"]
    assert (slug_dir / "Sample Novel.epub").read_bytes() == b"rich-original"
    # El traducido se regenera en tomos.
    assert manifest.epub_translated == [
        "Sample Novel 1-2 (ES).epub",
    ]
    assert (slug_dir / "Sample Novel 1-2 (ES).epub").exists()
    assert manifest.volume_size == 2