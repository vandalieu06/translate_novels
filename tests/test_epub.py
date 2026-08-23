"""Unit tests del servicio de EPUB (ebooklib): estructura, volumenes, portada."""

from __future__ import annotations

import io
import zipfile

import ebooklib
from ebooklib import epub

from novel_cli.core.models.novel import Chapter
from novel_cli.core.services.epub import (
    build_epub,
    generate_volumes,
    stable_identifier,
)


def make_chapters(n: int) -> list[Chapter]:
    return [
        Chapter(
            num=i,
            title=f"Chapter {i}",
            url=f"https://example.com/{i}",
            paragraphs=["First paragraph.", "Second paragraph."],
        )
        for i in range(1, n + 1)
    ]


def build_and_open(**kw) -> zipfile.ZipFile:
    data = build_epub(**kw)
    return zipfile.ZipFile(io.BytesIO(data))


def test_stable_identifier():
    a = stable_identifier("https://novelfire.net/book/xyz")
    b = stable_identifier("https://novelfire.net/book/xyz")
    c = stable_identifier("https://novelfire.net/book/other")
    assert a == b
    assert a != c
    assert a.startswith("urn:novel-cli:")


def test_build_epub_valid_zip_layout(tmp_path):
    chapters = make_chapters(3)
    zf = build_and_open(
        title="Novela",
        author="Autor",
        language="en",
        identifier="urn:x:1",
        chapters=chapters,
        cover_path=None,
    )
    names = zf.namelist()
    assert "META-INF/container.xml" in names
    assert "EPUB/content.opf" in names
    assert "EPUB/toc.ncx" in names
    assert "EPUB/nav.xhtml" in names
    for ch in chapters:
        assert f"EPUB/chapter{ch.num:04d}.xhtml" in names
    # portada SVG si no hay imagen local
    assert "EPUB/cover.svg" in names
    assert "EPUB/cover.xhtml" in names


def test_build_epub_metadata(tmp_path):
    zf = build_and_open(
        title="Mi Novela",
        author="Jane Doe",
        language="es",
        identifier="urn:x:42",
        chapters=make_chapters(2),
        cover_path=None,
    )
    opf = zf.read("EPUB/content.opf").decode("utf-8")
    assert "<dc:title>Mi Novela</dc:title>" in opf
    assert "<dc:creator" in opf and "Jane Doe" in opf
    assert "<dc:language>es</dc:language>" in opf
    assert "urn:x:42" in opf
    assert '<meta name="cover" content="cover-svg">' in opf


def test_build_epub_chapter_structure(tmp_path):
    chapters = make_chapters(1)
    chapters[0].paragraphs = ["First paragraph.", "Second paragraph."]
    zf = build_and_open(
        title="Novela",
        author=None,
        language="en",
        identifier="urn:x:1",
        chapters=chapters,
        cover_path=None,
    )
    xhtml = zf.read("EPUB/chapter0001.xhtml").decode("utf-8")
    assert "<h1>Chapter 1</h1>" in xhtml
    assert "<p>First paragraph.</p>" in xhtml
    assert "<p>Second paragraph.</p>" in xhtml


def test_build_epub_escapes_xml(tmp_path):
    chapters = [
        Chapter(num=1, title="A & B <C>", url="u", paragraphs=["x < y & z"])
    ]
    zf = build_and_open(
        title="T",
        author=None,
        language="en",
        identifier="urn:x:1",
        chapters=chapters,
        cover_path=None,
    )
    xhtml = zf.read("EPUB/chapter0001.xhtml").decode("utf-8")
    assert "<p>x &lt; y &amp; z</p>" in xhtml
    assert "<h1>A &amp; B &lt;C&gt;</h1>" in xhtml


def test_build_epub_with_local_cover(tmp_path):
    cover = tmp_path / "cover.png"
    cover.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 16)
    zf = build_and_open(
        title="Novela",
        author=None,
        language="en",
        identifier="urn:x:1",
        chapters=make_chapters(1),
        cover_path=str(cover),
    )
    assert "EPUB/cover.png" in zf.namelist()
    opf = zf.read("EPUB/content.opf").decode("utf-8")
    assert '<meta name="cover" content="cover-image">' in opf
    assert 'media-type="image/png"' in opf


def test_build_epub_readable_by_ebooklib(tmp_path):
    chapters = make_chapters(3)
    data = build_epub(
        title="Novela",
        author="Autor",
        language="en",
        identifier="urn:x:1",
        chapters=chapters,
        cover_path=None,
    )
    out = tmp_path / "novela.epub"
    out.write_bytes(data)
    book = epub.read_epub(str(out))
    assert book.get_metadata("DC", "title")[0][0] == "Novela"
    assert len(list(book.get_items_of_type(ebooklib.ITEM_DOCUMENT))) == 5  # cover+nav+3


def test_generate_volumes_none_single():
    chapters = make_chapters(5)
    volumes = generate_volumes(chapters, None)
    assert len(volumes) == 1
    assert volumes[0].start == 1
    assert volumes[0].end == 5
    assert len(volumes[0].chapters) == 5


def test_generate_volumes_50():
    chapters = make_chapters(120)
    volumes = generate_volumes(chapters, 50)
    assert len(volumes) == 3
    assert [(v.start, v.end) for v in volumes] == [(1, 50), (51, 100), (101, 120)]
    assert [len(v.chapters) for v in volumes] == [50, 50, 20]


def test_generate_volumes_exact_multiple():
    chapters = make_chapters(100)
    volumes = generate_volumes(chapters, 50)
    assert len(volumes) == 2
    assert volumes[-1].end == 100


def test_generate_volumes_empty():
    assert generate_volumes([], 50) == []