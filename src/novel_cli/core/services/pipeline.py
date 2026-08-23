"""Orquesta el flujo completo: scrape → download → epub → translate → pack."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from novel_cli.core.models.novel import Chapter, NovelMetadata
from novel_cli.core.models.state import Manifest
from novel_cli.core.scraper.base import Fetcher, SiteAdapter
from novel_cli.core.scraper.fetcher import Pacer
from novel_cli.core.scraper.registry import get_adapter
from novel_cli.core.services.download import (
    download_chapters,
    download_cover,
    load_chapter,
)
from novel_cli.core.services.epub import build_epub, generate_volumes, stable_identifier
from novel_cli.core.services.toc import fetch_site_metadata
from novel_cli.core.services.translate import Translator, translate_chapters
from novel_cli.core.utils.names import (
    chapter_filename,
    epub_name,
    slugify,
    title_to_filename,
    volume_name,
)

StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]


class PipelineError(Exception):
    """Fallo al generar EPUB/manifest o estado inconsistente."""


async def run_pipeline(
    *,
    url: str,
    output_dir: Path,
    volume_size: int | None,
    translate: bool,
    resume: bool,
    force: bool,
    concurrency: int,
    download_all: bool = False,
    fetcher: Fetcher,
    adapter: SiteAdapter | None = None,
    translator: Translator | None = None,
    pacer: Pacer | None = None,
    on_status: StatusCallback | None = None,
    on_download_progress: ProgressCallback | None = None,
    on_translate_progress: ProgressCallback | None = None,
    on_epub_progress: ProgressCallback | None = None,
) -> Manifest:
    """Ejecuta el pipeline completo y devuelve el manifest final."""
    if on_status:
        on_status("Resolviendo adaptador de sitio")
    adapter = adapter or get_adapter(url)
    site = await fetch_site_metadata(fetcher, adapter, url)
    metadata = site.metadata
    if not site.chapters:
        raise PipelineError(
            "no se encontraron capitulos en el TOC. "
            "Puede requerir JS: prueba -p/--playwright, o el sitio bloquea el acceso."
        )

    slug = slugify(metadata.title)
    slug_dir = output_dir / slug
    slug_dir.mkdir(parents=True, exist_ok=True)

    manifest = _load_or_create_manifest(
        slug_dir, metadata, slug, volume_size, translate, resume, force
    )

    cover_path = slug_dir / manifest.cover_path if manifest.cover_path else None
    if cover_path is None or not cover_path.exists():
        cover_name = await download_cover(fetcher, metadata, slug_dir)
        if cover_name:
            manifest.cover_path = cover_name
            manifest.save(slug_dir)

    if on_status:
        on_status("Descargando capitulos")
    batch = _download_batch(
        site.chapters,
        volume_size,
        slug_dir / "raw",
        download_all=download_all,
        force=force,
    )
    await download_chapters(
        fetcher=fetcher,
        adapter=adapter,
        metadata=metadata,
        chapters=batch,
        slug_dir=slug_dir,
        manifest=manifest,
        force=force,
        concurrency=concurrency,
        pacer=pacer,
        on_progress=on_download_progress,
    )
    manifest.chapters_total = manifest.chapters_downloaded
    loaded = _load_all_chapters(site.chapters, slug_dir / "raw")
    manifest.save(slug_dir)

    if on_status:
        on_status("Generando EPUB original")
    original_names = _generate_epubs(
        slug_dir=slug_dir,
        manifest=manifest,
        metadata=metadata,
        chapters=loaded,
        volume_size=volume_size,
        language=_epub_language(metadata.language_code),
        translated=False,
        resume=resume,
        force=force,
        on_progress=on_epub_progress,
    )
    manifest.epub_original = original_names
    manifest.save(slug_dir)

    if translate:
        if translator is None:
            raise PipelineError("se pidio traduccion sin un Translator")
        if on_status:
            on_status("Traduciendo a espanol")
        await translate_chapters(
            translator=translator,
            chapters=loaded,
            slug_dir=slug_dir,
            manifest=manifest,
            force=force,
            on_progress=on_translate_progress,
        )
        translated = _load_all_chapters(loaded, slug_dir / "translated")
        if on_status:
            on_status("Generando EPUB traducido")
        es_names = _generate_epubs(
            slug_dir=slug_dir,
            manifest=manifest,
            metadata=metadata,
            chapters=translated,
            volume_size=volume_size,
            language="es",
            translated=True,
            resume=resume,
            force=force,
            on_progress=on_epub_progress,
        )
        manifest.epub_translated = es_names
        manifest.translated = True
        manifest.save(slug_dir)

    return manifest


def _generate_epubs(
    *,
    slug_dir: Path,
    manifest: Manifest,
    metadata: NovelMetadata,
    chapters: list[Chapter],
    volume_size: int | None,
    language: str,
    translated: bool,
    resume: bool,
    force: bool,
    on_progress: ProgressCallback | None,
) -> list[str]:
    base = title_to_filename(metadata.title) or manifest.slug
    volumes = generate_volumes(chapters, volume_size)
    suffix = " (ES)" if translated else ""
    names: list[str] = []
    for index, volume in enumerate(volumes, start=1):
        if volume_size is None:
            title = metadata.title
            name = epub_name(base, suffix)
        else:
            title = f"{metadata.title} {volume.start}-{volume.end}"
            name = volume_name(base, volume.start, volume.end, suffix)
        out_path = slug_dir / name
        if not (resume and not force) or not out_path.exists():
            cover_path = (
                str(slug_dir / manifest.cover_path) if manifest.cover_path else None
            )
            data = build_epub(
                title=title,
                author=metadata.author,
                language=language,
                identifier=stable_identifier(metadata.source_url),
                chapters=volume.chapters,
                cover_path=cover_path,
                translated=translated,
            )
            out_path.write_bytes(data)
        names.append(name)
        if on_progress:
            on_progress(index, len(volumes))
    return names


def _download_batch(
    chapters: list[Chapter],
    volume_size: int | None,
    raw_dir: Path,
    *,
    download_all: bool,
    force: bool,
) -> list[Chapter]:
    """Selecciona el lote a descargar: todo, o el proximo tomo pendiente."""
    if download_all or volume_size is None:
        return chapters
    if force:
        return chapters[:volume_size]
    existing = {int(path.stem) for path in raw_dir.glob("*.md")}
    pending = [chapter for chapter in chapters if chapter.num not in existing]
    return pending[:volume_size]


def _load_or_create_manifest(
    slug_dir: Path,
    metadata: NovelMetadata,
    slug: str,
    volume_size: int | None,
    translate: bool,
    resume: bool,
    force: bool,
) -> Manifest:
    if resume and not force:
        existing = Manifest.load(slug_dir)
        if existing is not None:
            existing.title = metadata.title
            existing.author = metadata.author or existing.author
            existing.source_url = metadata.source_url
            existing.language_code = metadata.language_code
            existing.volume_size = volume_size
            existing.translated = existing.translated or translate
            return existing
    return Manifest(
        slug=slug,
        title=metadata.title,
        author=metadata.author,
        source_url=metadata.source_url,
        language_code=metadata.language_code,
        volume_size=volume_size,
        translated=translate,
    )


def _load_all_chapters(chapters: list[Chapter], chapter_dir: Path) -> list[Chapter]:
    """Carga de disco solo los capitulos que tienen archivo (en orden TOC)."""
    loaded: list[Chapter] = []
    for chapter in chapters:
        path = chapter_dir / chapter_filename(chapter.num)
        if path.exists():
            loaded.append(load_chapter(path, chapter.num, chapter.url))
    return loaded


def _epub_language(code: str) -> str:
    return code if code and code != "auto" else "en"