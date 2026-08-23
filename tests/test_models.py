"""Unit tests: modelos de dominio, manifest y naming."""

from __future__ import annotations

import json

import pytest

from novel_cli.core.models.novel import Chapter, NovelMetadata, SiteMetadata, Volume
from novel_cli.core.models.state import Manifest
from novel_cli.core.utils.names import (
    chapter_filename,
    epub_name,
    slugify,
    title_to_filename,
    volume_name,
)


def test_slugify():
    assert (
        slugify("Inner Voice: All Heroines Hear My Inner Voice")
        == "inner-voice-all-heroines-hear-my-inner-voice"
    )
    assert slugify("  Hola  Mundo!  ") == "hola-mundo"


def test_title_to_filename():
    assert title_to_filename("Novela: Parte 1") == "Novela Parte 1"
    assert title_to_filename("A/B") == "A B"
    assert title_to_filename("  doble   espacio ") == "doble espacio"


def test_chapter_filename():
    assert chapter_filename(42) == "0042.md"
    assert chapter_filename(1) == "0001.md"
    assert chapter_filename(12345) == "12345.md"


def test_volume_name():
    assert volume_name("inner-voice", 1, 50) == "inner-voice 1-50.epub"
    assert volume_name("Novela", 51, 100) == "Novela 51-100.epub"
    assert volume_name("Novela", 1, 50, " (ES)") == "Novela 1-50 (ES).epub"
    assert epub_name("Novela") == "Novela.epub"
    assert epub_name("Novela", " (ES)") == "Novela (ES).epub"


def test_chapter_dataclass():
    ch = Chapter(num=1, title="Chapter 1", url="https://example.com/1", paragraphs=["a", "b"])
    assert ch.num == 1
    assert ch.paragraphs == ["a", "b"]
    assert Chapter(num=2, title="t", url="u").paragraphs == []


def test_novel_metadata_defaults():
    m = NovelMetadata(title="T", source_url="https://example.com")
    assert m.author is None
    assert m.language_code == "auto"


def test_site_metadata_holds_chapters():
    md = NovelMetadata(title="T")
    chapters = [Chapter(num=i, title=f"c{i}", url=f"u{i}") for i in (1, 2)]
    site = SiteMetadata(metadata=md, chapters=chapters)
    assert len(site.chapters) == 2


def test_volume_grouping():
    chapters = [Chapter(num=i, title=f"c{i}", url=f"u{i}") for i in range(1, 11)]
    vol = Volume(start=1, end=10, chapters=chapters)
    assert vol.start == 1
    assert vol.end == 10
    assert len(vol.chapters) == 10


def test_manifest_roundtrip(tmp_path):
    manifest = Manifest(slug="novela", title="Novela", author="Autor")
    manifest.save(tmp_path)

    loaded = Manifest.load(tmp_path)
    assert loaded is not None
    assert loaded.slug == "novela"
    assert loaded.title == "Novela"
    assert loaded.author == "Autor"
    assert loaded.created_at is not None
    assert loaded.updated_at is not None


def test_manifest_save_updates_updated_at(tmp_path):
    manifest = Manifest(slug="novela", title="Novela")
    manifest.save(tmp_path)
    first = manifest.updated_at
    manifest.save(tmp_path)
    assert manifest.updated_at != first
    assert manifest.created_at == first


def test_manifest_load_missing(tmp_path):
    assert Manifest.load(tmp_path) is None


def test_manifest_load_invalid_json(tmp_path):
    (tmp_path / ".manifest.json").write_text("{not json", encoding="utf-8")
    assert Manifest.load(tmp_path) is None


def test_manifest_extra_keys_ignored(tmp_path):
    (tmp_path / ".manifest.json").write_text(
        json.dumps({"slug": "x", "title": "T", "bogus_field": 1}), encoding="utf-8"
    )
    loaded = Manifest.load(tmp_path)
    assert loaded is not None
    assert loaded.title == "T"
    assert not hasattr(loaded, "bogus_field")


@pytest.mark.parametrize("volume_size", [50, 100, None])
def test_manifest_volume_size(volume_size):
    manifest = Manifest(slug="novela", title="Novela", volume_size=volume_size)
    assert manifest.volume_size == volume_size