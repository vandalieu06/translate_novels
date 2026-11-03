"""Importacion de novelas desde PDF: convierte con pdf-to-epub y opcionalmente traduce.

El EPUB original lo genera pdf-to-epub (conserva imagenes, tablas y formato del
PDF). El texto plano extraido del DOCX intermedio se guarda como `raw/<NNNN>.md`
para traducirlo con el pipeline existente y generar el EPUB traducido con el
builder de novel_cli (texto plano, tomos).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import statistics
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pymupdf
from pdf_to_epub.core.config import ConversionOptions
from pdf_to_epub.core.epub.split import chapter_title
from pdf_to_epub.core.export import extract_docx_chapters
from pdf_to_epub.core.pdf.inspect import read_metadata
from pdf_to_epub.core.pipeline import run as pdf_to_epub_run
from pdf_to_epub.core.text import is_page_number

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
from novel_cli.core.utils.names import epub_name, slugify, title_to_filename, unique_slug

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]

_INVALID_METADATA = {
    "",
    "<unknown>",
    "unknown",
    "desconocido",
    "desconocida",
    "anonymous",
    "anónimo",
    "anonimo",
    "untitled",
    "sin título",
    "sin titulo",
    "n/a",
    "na",
    "none",
    "null",
}
_INVALID_METADATA_PREFIXES = ("microsoft word", "microsoft® word")
_INVALID_AUTHOR_PREFIXES = (
    "python-docx",
    "pymupdf",
    "pdf2docx",
    "calibre",
    "adobe",
)
_INVALID_METADATA_SUFFIXES = (".pdf", ".docx", ".doc")
_VALID_SPLIT_MODES = ("auto", "book", "webnovel")

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_QUOTED_TITLE_RE = re.compile(
    r"(?:novela\s+ligera|light\s+novel|novela|obra|volumen)"
    r"[^“\"'«]{0,80}[“\"'«]([^”\"'»]{3,140})[”\"'»]",
    re.IGNORECASE,
)
_AUTHOR_RE = re.compile(
    r"(?:escrita|escrito|escrit[oa]s?)\s+por\s+"
    r"([A-ZÁÉÍÓÚÜÑ][^.;]{2,80}?)(?=\s+e\s+ilustrad|\s*[,.;]|$)",
    re.IGNORECASE,
)
_AUTHOR_LABEL_RE = re.compile(
    r"(?:autor|author)\s*[:：]\s*([^\n]{2,80})", re.IGNORECASE
)
_GENERIC_HEADER_RE = re.compile(
    r"(?:p[áa]gina|page|traducci[óo]n sin fines|todos los derechos|"
    r"copyright|pertenecen a sus respectivos)",
    re.IGNORECASE,
)
_INFER_PAGES = 12
_TITLE_PAGE_MIN_SIZE = 16.0
_TITLE_PAGE_RATIO = 1.6
_RUNNING_HEADER_MIN_RATIO = 0.25


class PdfImportError(Exception):
    """Fallo al importar o convertir un PDF."""


@dataclass
class ResolvedPdfMetadata:
    """Metadatos de PDF ya saneados y con fallback al nombre de archivo."""

    title: str
    author: str | None


@dataclass
class InferredPdfMetadata:
    """Titulo/autor inferidos del contenido del PDF (best effort)."""

    title: str | None = None
    author: str | None = None


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
    split_mode: str = "auto"


def _is_uuid_like(value: str) -> bool:
    """Return True for UUID-shaped strings (upload cache names)."""
    return bool(_UUID_RE.match(value.strip()))


def _clean_metadata_value(value: str | None, *, kind: str = "title") -> str | None:
    """Return a usable metadata value, or None for empty/placeholder values."""
    if value is None:
        return None
    text = " ".join(value.split()).strip()
    if not text or _is_uuid_like(text):
        return None
    lowered = text.casefold()
    if lowered in _INVALID_METADATA:
        return None
    if lowered.startswith(_INVALID_METADATA_PREFIXES):
        return None
    if kind == "author" and lowered.startswith(_INVALID_AUTHOR_PREFIXES):
        return None
    if lowered.endswith(_INVALID_METADATA_SUFFIXES):
        return None
    return text


def _normalized_page_text(doc: pymupdf.Document, pages: int = _INFER_PAGES) -> str:
    parts: list[str] = []
    for index in range(min(pages, doc.page_count)):
        parts.append(" ".join(doc[index].get_text().split()))
    return " ".join(parts)


def _infer_quoted_title(text: str) -> str | None:
    match = _QUOTED_TITLE_RE.search(text)
    if match is None:
        return None
    return _clean_metadata_value(match.group(1))


def _infer_title_page(doc: pymupdf.Document) -> str | None:
    """Use the largest text on the first pages when it stands out from the body."""
    candidates: list[tuple[float, str]] = []
    for page_index in range(min(_INFER_PAGES, doc.page_count)):
        page = doc[page_index]
        height = page.rect.height
        lines: list[tuple[float, str, float]] = []
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                text = " ".join(
                    span["text"] for span in line["spans"]
                ).strip()
                text = " ".join(text.split())
                if not text:
                    continue
                y0 = line["bbox"][1]
                if y0 < height * 0.08 or y0 > height * 0.92:
                    continue
                if is_page_number(text) or chapter_title(text) is not None:
                    continue
                size = max(span["size"] for span in line["spans"])
                lines.append((size, text, y0))
        if not lines or len(lines) > 12:
            continue
        sizes = [size for size, _text, _y0 in lines]
        median = statistics.median(sizes)
        max_size = max(sizes)
        if max_size < _TITLE_PAGE_MIN_SIZE or max_size < median * _TITLE_PAGE_RATIO:
            continue
        top_lines = sorted(
            (line for line in lines if abs(line[0] - max_size) < 0.5),
            key=lambda line: line[2],
        )
        parts: list[str] = []
        for _size, text, _y0 in top_lines[:3]:
            if re.match(r"(?i)^(por|by|autor|author)\b", text):
                break
            parts.append(text)
        title = _clean_metadata_value(" ".join(parts))
        if title is not None and 3 <= len(title) <= 140:
            candidates.append((max_size, title))
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate[0])[1]


def _infer_running_header(doc: pymupdf.Document) -> str | None:
    """Use a line repeated in the top band across the first pages."""
    counts: Counter[str] = Counter()
    sampled = 0
    for page_index in range(min(_INFER_PAGES, doc.page_count)):
        page = doc[page_index]
        height = page.rect.height
        sampled += 1
        seen: set[str] = set()
        for block in page.get_text("blocks"):
            _x0, y0, _x1, _y1, raw_text, _block_no, block_type = block
            if block_type != 0 or y0 > height * 0.12:
                continue
            text = " ".join(raw_text.split())
            if not text or len(text) < 3 or len(text) > 140:
                continue
            if is_page_number(text) or _GENERIC_HEADER_RE.search(text):
                continue
            if chapter_title(text) is not None or text in seen:
                continue
            seen.add(text)
            counts[text] += 1
    if not counts:
        return None
    text, count = counts.most_common(1)[0]
    if count < max(2, int(sampled * _RUNNING_HEADER_MIN_RATIO)):
        return None
    return _clean_metadata_value(text)


def _infer_author(text: str) -> str | None:
    for pattern in (_AUTHOR_RE, _AUTHOR_LABEL_RE):
        match = pattern.search(text)
        if match is None:
            continue
        author = _clean_metadata_value(match.group(1), kind="author")
        if author is not None:
            return author
    return None


def infer_pdf_metadata(pdf_path: Path) -> InferredPdfMetadata:
    """Infer title/author from the PDF content; never raise."""
    try:
        with pymupdf.open(str(pdf_path)) as doc:
            text = _normalized_page_text(doc)
            title = _infer_quoted_title(text)
            if title is None:
                title = _infer_title_page(doc)
            if title is None:
                title = _infer_running_header(doc)
            return InferredPdfMetadata(title=title, author=_infer_author(text))
    except Exception:  # noqa: BLE001 - best effort; conversion can continue
        return InferredPdfMetadata()


def resolve_pdf_metadata(
    pdf_path: Path,
    *,
    title: str | None = None,
    author: str | None = None,
    metadata_title: str | None = None,
    metadata_author: str | None = None,
    inferred_title: str | None = None,
    inferred_author: str | None = None,
) -> ResolvedPdfMetadata:
    """Resolve title/author: user > metadata > inferred > readable filename."""
    resolved_title = _clean_metadata_value(title)
    if resolved_title is None:
        resolved_title = _clean_metadata_value(metadata_title)
    if resolved_title is None:
        resolved_title = _clean_metadata_value(inferred_title)
    if resolved_title is None:
        resolved_title = _clean_metadata_value(pdf_path.stem)
    if resolved_title is None:
        resolved_title = "Novela sin título"

    resolved_author = _clean_metadata_value(author, kind="author")
    if resolved_author is None:
        resolved_author = _clean_metadata_value(metadata_author, kind="author")
    if resolved_author is None:
        resolved_author = _clean_metadata_value(inferred_author, kind="author")
    return ResolvedPdfMetadata(title=resolved_title, author=resolved_author)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def convert_pdf(
    pdf_path: Path,
    workdir: Path,
    *,
    title: str | None = None,
    author: str | None = None,
    language: str = "es",
    split_mode: str = "auto",
    original_filename: str | None = None,
    output_epub: Path | None = None,
    on_status: StatusCallback | None = None,
) -> PdfImport:
    """Convierte un PDF con pdf-to-epub y extrae capitulos de texto plano.

    ``pdf_to_epub_run`` es CPU/IO intensivo (pdf2docx): llamalo dentro de un
    thread/executor desde un contexto async. Requiere ``keep_intermediate=True``
    para conservar el DOCX del que se extrae el texto.
    """
    if split_mode not in _VALID_SPLIT_MODES:
        raise PdfImportError(
            f"modo de capitulos no soportado: {split_mode} "
            f"(disponibles: {', '.join(_VALID_SPLIT_MODES)})"
        )

    try:
        metadata = read_metadata(pdf_path)
        metadata_title = metadata.title
        metadata_author = metadata.authors[0] if metadata.authors else None
    except Exception:  # noqa: BLE001 - pdf-to-epub volvera a leerlo
        metadata_title = None
        metadata_author = None

    needs_title = (
        _clean_metadata_value(title) is None
        and _clean_metadata_value(metadata_title) is None
    )
    needs_author = (
        _clean_metadata_value(author, kind="author") is None
        and _clean_metadata_value(metadata_author, kind="author") is None
    )
    inferred = (
        infer_pdf_metadata(pdf_path)
        if (needs_title or needs_author)
        else InferredPdfMetadata()
    )
    resolved = resolve_pdf_metadata(
        Path(original_filename) if original_filename else pdf_path,
        title=title,
        author=author,
        metadata_title=metadata_title,
        metadata_author=metadata_author,
        inferred_title=inferred.title,
        inferred_author=inferred.author,
    )

    workdir.mkdir(parents=True, exist_ok=True)
    if output_epub is None:
        output_epub = workdir / f"{pdf_path.stem}.epub"

    options = ConversionOptions(
        input_pdf=pdf_path,
        output_epub=output_epub,
        workdir=workdir,
        keep_intermediate=True,
        clean_headers_footers=True,
        reflow_paragraphs=True,
        force=True,
        title=resolved.title,
        author=resolved.author,
        language=language,
        split_mode=split_mode,
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

    resolved_mode = getattr(report, "split_mode", split_mode) or split_mode
    text_chapters = extract_docx_chapters(
        report.docx_path,
        fallback_title=resolved.title,
        mode=resolved_mode,
    )
    chapters = [
        Chapter(num=i + 1, title=chapter.title, url="", paragraphs=chapter.paragraphs)
        for i, chapter in enumerate(text_chapters)
    ]
    return PdfImport(
        title=resolved.title,
        author=resolved.author,
        language=report.language or language,
        chapters=chapters,
        epub_path=report.output_epub,
        cover_path=report.cover_path,
        docx_path=report.docx_path,
        split_mode=resolved_mode,
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
    title: str | None = None,
    author: str | None = None,
    original_filename: str | None = None,
    split_mode: str = "auto",
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
    if split_mode not in _VALID_SPLIT_MODES:
        raise PdfImportError(
            f"modo de capitulos no soportado: {split_mode} "
            f"(disponibles: {', '.join(_VALID_SPLIT_MODES)})"
        )

    source_sha256 = _sha256(pdf_path)
    workdir = pdf_path.parent / "work"
    if on_status:
        on_status("Convirtiendo PDF a EPUB y DOCX")
    converted = await asyncio.to_thread(
        convert_pdf,
        pdf_path,
        workdir,
        title=title,
        author=author,
        language=source_language,
        split_mode=split_mode,
        original_filename=original_filename or pdf_path.name,
        on_status=on_status,
    )
    if not converted.chapters:
        raise PdfImportError("no se extrajeron capitulos del PDF")

    slug = unique_slug(slugify(converted.title), output_dir, sha256=source_sha256)
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
        source_filename=original_filename or pdf_path.name,
        source_pdf_sha256=source_sha256,
        pdf_kind=converted.split_mode,
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


async def retranslate_pdf(
    *,
    slug_dir: Path,
    target_language: str | None,
    translator: Translator,
    on_status: StatusCallback | None = None,
    on_translate_progress: ProgressCallback | None = None,
    on_epub_progress: ProgressCallback | None = None,
) -> Manifest:
    """Re-traduce los capitulos pendientes de una novela importada de PDF.

    No reconvierte el PDF: trabaja desde el `raw/` ya en disco y regenera los
    EPUBs traducidos (el original rico de pdf-to-epub se conserva intacto).
    """
    manifest = Manifest.load(slug_dir)
    if manifest is None:
        raise PdfImportError(f"no hay manifest en {slug_dir}")
    raw_chapters = load_all_from_disk(slug_dir / "raw")
    if not raw_chapters:
        raise PdfImportError("no hay capitulos descargados en disco")

    source = manifest.language_code or "auto"
    target = (
        target_language
        or manifest.translated_language
        or config.translate_target_default()
    )
    if on_status:
        on_status(f"Traduciendo capitulos pendientes a {target}")
    await translate_chapters(
        translator=translator,
        chapters=raw_chapters,
        slug_dir=slug_dir,
        manifest=manifest,
        target=target,
        source=source,
        on_progress=on_translate_progress,
    )
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
        volume_size=manifest.volume_size,
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