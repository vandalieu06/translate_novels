"""Importacion de novelas desde PDF: convierte con pdf-to-epub y opcionalmente traduce.

El EPUB original lo genera pdf-to-epub (conserva imagenes, tablas y formato del
PDF). El texto plano extraido del DOCX intermedio se guarda como `raw/<NNNN>.md`
para traducirlo con el pipeline existente y generar el EPUB traducido con el
builder de novel_cli (texto plano, tomos).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pdf_to_epub.core.config import ConversionOptions
from pdf_to_epub.core.export import extract_docx_chapters
from pdf_to_epub.core.pipeline import run as pdf_to_epub_run

from novel_cli.core import config
from novel_cli.core.models.novel import Chapter, NovelMetadata
from novel_cli.core.models.state import Manifest
from novel_cli.core.services.download import format_chapter
from novel_cli.core.services.pipeline import (
    build_epub_chapters,
    cleanup_orphan_epubs,
    generate_epubs,
    load_all_from_disk,
    translated_placeholder,
)
from novel_cli.core.services.translate import Translator, translate_chapters
from novel_cli.core.utils.names import epub_name, slugify, title_to_filename

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]


class PdfImportError(Exception):
    """Fallo al importar o convertir un PDF."""


@dataclass
class PdfImport:
    """Resultado de convertir un PDF: EPUB original + capitulos en texto plano + cover."""

    title: str
    author: str | None
    language: str | None
    chapters: list[Chapter]
    epub_path: Path
    cover_path: Path | None
    docx_path: Path


def convert_pdf(
    pdf_path: Path,
    workdir: Path,
    *,
    title: str | None = None,
    author: str | None = None,
    language: str = "es",
    output_epub: Path | None = None,
    on_status: StatusCallback | None = None,
) -> PdfImport:
    """Convierte un PDF con pdf-to-epub y extrae capitulos de texto plano.

    ``pdf_to_epub_run`` es CPU/IO intensivo (pdf2docx): llamalo dentro de un
    thread/executor desde un contexto async. Requiere ``keep_intermediate=True``
    para conservar el DOCX del que se extrae el texto.
    """
    options = ConversionOptions(
        input_pdf=pdf_path,
        output_epub=output_epub,
        workdir=workdir,
        keep_intermediate=True,
        clean_headers_footers=True,
        reflow_paragraphs=True,
        title=title,
        author=author,
        language=language,
    )

    def progress(message: str) -> None:
        if on_status:
            on_status(f"PDF: {message}")

    try:
        report = pdf_to_epub_run(options, progress=progress)
    except Exception as exc:  # noqa: BLE001 - se envuelve en PdfImportError
        raise PdfImportError(f"no se pudo convertir el PDF: {exc}") from exc

    if report.docx_path is None or not report.docx_path.exists():
        raise PdfImportError(
            "pdf-to-epub no dejo el DOCX intermedio; fallo la conversion"
        )

    text_chapters = extract_docx_chapters(
        report.docx_path,
        fallback_title=report.title or pdf_path.stem,
    )
    chapters = [
        Chapter(num=i + 1, title=chapter.title, url="", paragraphs=chapter.paragraphs)
        for i, chapter in enumerate(text_chapters)
    ]
    return PdfImport(
        title=report.title or pdf_path.stem,
        author=report.author,
        language=report.language,
        chapters=chapters,
        epub_path=report.output_epub,
        cover_path=report.cover_path,
        docx_path=report.docx_path,
    )


def save_chapters(slug_dir: Path, chapters: list[Chapter]) -> None:
    """Escribe los capitulos como raw/<NNNN>.md (formato canonico del CLI)."""
    raw_dir = slug_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for chapter in chapters:
        raw_dir.joinpath(f"{chapter.num:04d}.md").write_text(
            format_chapter(chapter, chapter.paragraphs), encoding="utf-8"
        )


async def run_pdf_pipeline(
    *,
    pdf_path: Path,
    output_dir: Path,
    source_language: str,
    translate: bool,
    target_language: str | None,
    volume_size: int | None,
    translator: Translator | None,
    on_status: StatusCallback | None = None,
    on_epub_progress: ProgressCallback | None = None,
    on_translate_progress: ProgressCallback | None = None,
) -> Manifest:
    """Importa un PDF: EPUB original (pdf-to-epub) + traduccion opcional.

    - El EPUB original conserva el formato del PDF (un solo tomo, ``{title}.epub``).
    - Si ``translate`` y ``target != source``, traduce a ``translated/<NNNN>.md``
      y genera el EPUB traducido (tomos segun ``volume_size``).
    - El PDF y la portada se guardan en ``output/<slug>/``.
    """
    if not pdf_path.is_file():
        raise PdfImportError(f"el PDF no existe: {pdf_path}")

    workdir = pdf_path.parent / "work"
    if on_status:
        on_status("Convirtiendo PDF a EPUB y DOCX")
    converted = convert_pdf(
        pdf_path,
        workdir,
        language=source_language,
        on_status=on_status,
    )
    if not converted.chapters:
        raise PdfImportError("no se extrajeron capitulos del PDF")

    slug = slugify(converted.title)
    slug_dir = output_dir / slug
    slug_dir.mkdir(parents=True, exist_ok=True)

    source_name = "source.pdf"
    target_pdf = slug_dir / source_name
    if pdf_path.resolve() != target_pdf.resolve():
        target_pdf.write_bytes(pdf_path.read_bytes())

    cover_path: str | None = None
    if converted.cover_path is not None and converted.cover_path.exists():
        cover_ext = converted.cover_path.suffix.lstrip(".") or "jpg"
        cover_name = f"cover.{cover_ext}"
        (slug_dir / cover_name).write_bytes(converted.cover_path.read_bytes())
        cover_path = cover_name

    manifest = Manifest(
        slug=slug,
        title=converted.title,
        author=converted.author,
        source_url="",
        source_pdf=source_name,
        language_code=source_language,
        cover_path=cover_path,
        volume_size=volume_size,
        chapters_total=len(converted.chapters),
        chapters_downloaded=len(converted.chapters),
    )
    manifest.save(slug_dir)

    save_chapters(slug_dir, converted.chapters)

    base = title_to_filename(converted.title) or slug
    original_name = epub_name(base)
    original_dest = slug_dir / original_name
    if converted.epub_path.resolve() != original_dest.resolve():
        original_dest.write_bytes(converted.epub_path.read_bytes())
    manifest.epub_original = [original_name]

    target = (
        target_language
        or manifest.translated_language
        or config.translate_target_default()
    )
    if translate and target != source_language:
        if translator is None:
            raise PdfImportError("se pidio traduccion sin un Translator")
        if on_status:
            on_status(f"Traduciendo {len(converted.chapters)} capitulos a {target}")
        await translate_chapters(
            translator=translator,
            chapters=converted.chapters,
            slug_dir=slug_dir,
            manifest=manifest,
            target=target,
            source=source_language,
            on_progress=on_translate_progress,
        )
        if on_status:
            on_status("Generando EPUB traducido")
        raw_chapters = load_all_from_disk(slug_dir / "raw")
        translated = build_epub_chapters(
            raw_chapters, slug_dir / "translated", translated_placeholder(target)
        )
        metadata = NovelMetadata(
            title=manifest.title,
            author=manifest.author,
            cover_url=manifest.cover_path,
            source_url=manifest.source_url,
        )
        es_names = generate_epubs(
            slug_dir=slug_dir,
            manifest=manifest,
            metadata=metadata,
            chapters=translated,
            volume_size=volume_size,
            language=target,
            translated=True,
            resume=True,
            force=False,
            rebuild=True,
            on_progress=on_epub_progress,
        )
        manifest.epub_translated = es_names
        manifest.translated = True
        manifest.translated_language = target

    cleanup_orphan_epubs(
        slug_dir,
        keep=manifest.epub_original + manifest.epub_translated,
    )
    manifest.save(slug_dir)
    return manifest