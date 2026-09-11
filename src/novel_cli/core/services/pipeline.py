"""Orquesta el flujo completo: scrape → download → epub → translate → pack."""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from pathlib import Path

from novel_cli.core import config
from novel_cli.core.models.novel import Chapter, NovelMetadata
from novel_cli.core.models.state import Manifest
from novel_cli.core.notifications import NotificationEvent, Notifier
from novel_cli.core.scraper.base import Fetcher, SiteAdapter
from novel_cli.core.scraper.fetcher import FetchError, Pacer
from novel_cli.core.scraper.registry import get_adapter
from novel_cli.core.services.download import (
    DownloadError,
    download_chapters,
    download_cover,
    is_chapter_empty,
    load_chapter,
    refresh_empty_counts,
)
from novel_cli.core.services.epub import build_epub, generate_volumes, stable_identifier
from novel_cli.core.services.toc import fetch_site_metadata
from novel_cli.core.services.translate import (
    TranslateError,
    Translator,
    translate_chapters,
)
from novel_cli.core.utils.names import (
    chapter_filename,
    epub_name,
    slugify,
    title_to_filename,
    volume_name,
)

StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]

EMPTY_PLACEHOLDER_EN = "(Chapter content not available - retry later.)"
EMPTY_PLACEHOLDER_ES = "(Capitulo sin contenido disponible - reintenta mas tarde.)"


def _translated_placeholder(target: str) -> str:
    """Placeholder para EPUBs traducidos: ES en espanol, neutro (EN) en el resto."""
    return EMPTY_PLACEHOLDER_ES if target == "es" else EMPTY_PLACEHOLDER_EN


class PipelineError(Exception):
    """Fallo al generar EPUB/manifest o estado inconsistente."""


logger = logging.getLogger(__name__)


async def _emit(notifier: Notifier | None, event: NotificationEvent) -> None:
    """Emite un evento sin dejar que un fallo del notifier rompa el pipeline."""
    if notifier is None:
        return
    try:
        await notifier.notify(event)
    except Exception:  # noqa: BLE001 - notificar nunca debe romper el pipeline
        logger.exception("el notificador fallo al emitir %s", event.kind)


def _phase_from_error(exc: Exception) -> str:
    if isinstance(exc, (DownloadError, FetchError)):
        return "descarga"
    if isinstance(exc, TranslateError):
        return "traduccion"
    if isinstance(exc, PipelineError):
        return "epub/manifest"
    return "el pipeline"


async def _emit_error(
    notifier: Notifier | None, exc: Exception, operation: str | None
) -> None:
    await _emit(
        notifier,
        NotificationEvent(
            kind="job_error",
            phase=_phase_from_error(exc),
            detail=str(exc),
            ok=False,
            operation=operation,
        ),
    )


def _notify_run(func: Callable[..., object]) -> Callable[..., object]:
    """Envia `job_error` si el pipeline falla y `job_done` al terminar."""

    @functools.wraps(func)
    async def wrapper(**kwargs: object) -> Manifest:
        notifier = kwargs.get("notifier")
        operation = str(kwargs.get("operation") or "download")
        await _emit(
            notifier,
            NotificationEvent(
                kind="job_started", phase="start", operation=operation
            ),
        )
        try:
            manifest = await func(**kwargs)
        except Exception as exc:  # noqa: BLE001 - re-lanzamos tras notificar
            await _emit_error(notifier, exc, operation)
            raise
        await _emit(
            notifier,
            NotificationEvent(
                kind="job_done",
                phase="done",
                title=manifest.title,
                operation=operation,
            ),
        )
        return manifest

    return wrapper


@_notify_run
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
    translate_pending: bool = False,
    translate_concurrency: int = 1,
    target: str | None = None,
    fetcher: Fetcher,
    adapter: SiteAdapter | None = None,
    translator: Translator | None = None,
    pacer: Pacer | None = None,
    on_status: StatusCallback | None = None,
    on_download_progress: ProgressCallback | None = None,
    on_translate_progress: ProgressCallback | None = None,
    on_epub_progress: ProgressCallback | None = None,
    notifier: Notifier | None = None,
    operation: str = "download",
) -> Manifest:
    """Ejecuta el pipeline completo y devuelve el manifest final."""
    if translate_pending:
        return await _run_translate_pending(
            url=url,
            output_dir=output_dir,
            resume=resume,
            force=force,
            translate_concurrency=translate_concurrency,
            target=target,
            translator=translator,
            on_status=on_status,
            on_translate_progress=on_translate_progress,
            on_epub_progress=on_epub_progress,
            notifier=notifier,
        )
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
    await _emit(
        notifier,
        NotificationEvent(
            kind="scrape_done",
            phase="scrape",
            title=metadata.title,
            data={"chapters_total": len(site.chapters)},
        ),
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
    if manifest.chapters_empty and on_status:
        nums = ", ".join(str(n) for n in manifest.chapters_empty_nums[:20])
        extra = "..." if len(manifest.chapters_empty_nums) > 20 else ""
        on_status(
            f"AVISO: {manifest.chapters_empty} capitulo(s) vacio(s) pendientes "
            f"de reintento: {nums}{extra}"
        )
    manifest.chapters_total = manifest.chapters_downloaded
    loaded = _load_all_chapters(site.chapters, slug_dir / "raw")
    manifest.save(slug_dir)
    await _emit(
        notifier,
        NotificationEvent(
            kind="download_done",
            phase="descarga",
            title=metadata.title,
            data={
                "chapters_downloaded": manifest.chapters_downloaded,
                "chapters_empty": manifest.chapters_empty,
            },
        ),
    )

    if on_status:
        on_status("Generando EPUB original")
    original_names = _generate_epubs(
        slug_dir=slug_dir,
        manifest=manifest,
        metadata=metadata,
        chapters=_build_epub_chapters(
            loaded, slug_dir / "raw", EMPTY_PLACEHOLDER_EN
        ),
        volume_size=volume_size,
        language=_epub_language(metadata.language_code),
        translated=False,
        resume=resume,
        force=force,
        on_progress=on_epub_progress,
    )
    manifest.epub_original = original_names
    manifest.save(slug_dir)
    await _emit(
        notifier,
        NotificationEvent(
            kind="epub_original_done",
            phase="epub",
            title=metadata.title,
            data={"volumes": len(original_names)},
        ),
    )

    if translate:
        if translator is None:
            raise PipelineError("se pidio traduccion sin un Translator")
        target = target or manifest.translated_language or config.translate_target_default()
        if on_status:
            on_status(f"Traduciendo a {target}")
        translated_now = await translate_chapters(
            translator=translator,
            chapters=loaded,
            slug_dir=slug_dir,
            manifest=manifest,
            target=target,
            force=force,
            concurrency=config.effective_translate_concurrency(translate_concurrency),
            on_progress=on_translate_progress,
        )
        await _emit(
            notifier,
            NotificationEvent(
                kind="translate_done",
                phase="traduccion",
                title=metadata.title,
                data={
                    "target": target,
                    "translated_new": len(translated_now),
                    "translated_total": manifest.chapters_translated,
                },
            ),
        )
        translated = _build_epub_chapters(
            loaded, slug_dir / "translated", _translated_placeholder(target)
        )
        if on_status:
            on_status("Generando EPUB traducido")
        es_names = _generate_epubs(
            slug_dir=slug_dir,
            manifest=manifest,
            metadata=metadata,
            chapters=translated,
            volume_size=volume_size,
            language=target,
            translated=True,
            resume=resume,
            force=force,
            rebuild=True,
            on_progress=on_epub_progress,
        )
        manifest.epub_translated = es_names
        manifest.translated = True
        manifest.translated_language = target
        refresh_empty_counts(slug_dir / "raw", manifest)
        manifest.save(slug_dir)
        await _emit(
            notifier,
            NotificationEvent(
                kind="epub_translated_done",
                phase="epub",
                title=metadata.title,
                data={"target": target, "volumes": len(es_names)},
            ),
        )

    _cleanup_orphan_epubs(
        slug_dir,
        keep=manifest.epub_original + manifest.epub_translated,
    )
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
    rebuild: bool = False,
    on_progress: ProgressCallback | None,
) -> list[str]:
    base = title_to_filename(metadata.title) or manifest.slug
    volumes = generate_volumes(chapters, volume_size)
    suffix = f" ({language.upper()})" if translated else ""
    names: list[str] = []
    for index, volume in enumerate(volumes, start=1):
        if volume_size is None:
            title = metadata.title
            name = epub_name(base, suffix)
        else:
            title = f"{metadata.title} {volume.start}-{volume.end}"
            name = volume_name(base, volume.start, volume.end, suffix)
        out_path = slug_dir / name
        if rebuild or force or not resume or not out_path.exists():
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
    existing = {
        int(path.stem)
        for path in raw_dir.glob("*.md")
        if not is_chapter_empty(load_chapter(path, int(path.stem), "").paragraphs)
    }
    pending = [chapter for chapter in chapters if chapter.num not in existing]
    return pending[:volume_size]


def _cleanup_orphan_epubs(slug_dir: Path, keep: list[str]) -> None:
    """Borra EPUBs del disco que ya no estan referenciados en el manifest."""
    if not keep:
        return
    keep_set = set(keep)
    for path in slug_dir.glob("*.epub"):
        if path.name not in keep_set:
            path.unlink()


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


def _load_all_from_disk(chapter_dir: Path) -> list[Chapter]:
    """Carga todos los capitulos del disco (raw/ o translated/) ordenados por num."""
    loaded: list[Chapter] = []
    for path in sorted(chapter_dir.glob("*.md")):
        try:
            num = int(path.stem)
        except ValueError:
            continue
        loaded.append(load_chapter(path, num, url=""))
    return loaded


def _build_epub_chapters(
    reference: list[Chapter],
    chapter_dir: Path,
    placeholder: str,
) -> list[Chapter]:
    """Lista EPUB del mismo tamano/orden que ``reference``.

    Por cada capitulo: si existe su archivo se carga y, si quedo vacio, se
    sustituye por el placeholder; si no existe (capitulo sin traducir), se
    crea un Chapter con el placeholder. Mantiene los tomos alineados con la
    lista raw completa y evita paginas en blanco.
    """
    out: list[Chapter] = []
    for chapter in reference:
        path = chapter_dir / chapter_filename(chapter.num)
        if path.exists():
            loaded = load_chapter(path, chapter.num, chapter.url)
            if is_chapter_empty(loaded.paragraphs):
                loaded = Chapter(
                    num=loaded.num,
                    title=loaded.title,
                    url=loaded.url,
                    paragraphs=[placeholder],
                )
            out.append(loaded)
        else:
            out.append(
                Chapter(
                    num=chapter.num,
                    title=chapter.title,
                    url=chapter.url,
                    paragraphs=[placeholder],
                )
            )
    return out


def _find_manifest_by_url(output_dir: Path, url: str) -> tuple[Path, Manifest]:
    """Busca el slug_dir cuyo manifest.source_url coincide con la URL."""
    if not output_dir.exists():
        raise PipelineError(
            f"no existe el directorio de salida {output_dir}; ejecuta primero novel-cli <url>"
        )
    for slug_dir in sorted(output_dir.iterdir()):
        if not slug_dir.is_dir():
            continue
        manifest = Manifest.load(slug_dir)
        if manifest is not None and manifest.source_url == url:
            return slug_dir, manifest
    raise PipelineError(
        f"no hay descarga previa para {url}; ejecuta primero novel-cli <url>"
    )


async def _run_translate_pending(
    *,
    url: str,
    output_dir: Path,
    resume: bool,
    force: bool,
    translate_concurrency: int = 1,
    target: str | None = None,
    translator: Translator | None,
    on_status: StatusCallback | None,
    on_translate_progress: ProgressCallback | None,
    on_epub_progress: ProgressCallback | None,
    notifier: Notifier | None = None,
) -> Manifest:
    """Traduce solo los capitulos pendientes sin descargar ni tocar el TOC."""
    if translator is None:
        raise PipelineError("se pidio traducir pendientes sin un Translator")
    slug_dir, manifest = _find_manifest_by_url(Path(output_dir), url)
    raw_chapters = _load_all_from_disk(slug_dir / "raw")
    if not raw_chapters:
        raise PipelineError("no hay capitulos descargados en disco")

    target = target or manifest.translated_language or config.translate_target_default()
    if on_status:
        on_status(f"Traduciendo capitulos pendientes a {target} (sin descargar)")
    translated_now = await translate_chapters(
        translator=translator,
        chapters=raw_chapters,
        slug_dir=slug_dir,
        manifest=manifest,
        target=target,
        force=force,
        concurrency=config.effective_translate_concurrency(translate_concurrency),
        on_progress=on_translate_progress,
    )
    await _emit(
        notifier,
        NotificationEvent(
            kind="translate_done",
            phase="traduccion",
            title=manifest.title,
            data={
                "target": target,
                "translated_new": len(translated_now),
                "translated_total": manifest.chapters_translated,
            },
        ),
    )
    translated = _build_epub_chapters(
        raw_chapters, slug_dir / "translated", _translated_placeholder(target)
    )
    metadata = NovelMetadata(
        title=manifest.title,
        author=manifest.author,
        cover_url=manifest.cover_path,
        source_url=manifest.source_url,
    )
    es_names = _generate_epubs(
        slug_dir=slug_dir,
        manifest=manifest,
        metadata=metadata,
        chapters=translated,
        volume_size=manifest.volume_size,
        language=target,
        translated=True,
        resume=resume,
        force=force,
        rebuild=True,
        on_progress=on_epub_progress,
    )
    manifest.epub_translated = es_names
    manifest.translated = True
    manifest.translated_language = target
    refresh_empty_counts(slug_dir / "raw", manifest)
    _cleanup_orphan_epubs(
        slug_dir,
        keep=manifest.epub_original + manifest.epub_translated,
    )
    manifest.save(slug_dir)
    await _emit(
        notifier,
        NotificationEvent(
            kind="epub_translated_done",
            phase="epub",
            title=manifest.title,
            data={"target": target, "volumes": len(es_names)},
        ),
    )
    return manifest


def _epub_language(code: str) -> str:
    return code if code and code != "auto" else "en"


def rebuild_volumes(slug_dir: Path, volume_size: int | None) -> Manifest:
    """Reconstruye los EPUBs con un nuevo tamano de tomo desde el disco (sin red).

    ``volume_size=None`` genera un unico EPUB ("ALL"). Valida el tamaño y
    actualiza ``manifest.volume_size``. Regenera original y traducido, limpia
    EPUBs huerfanos y refresca ``chapters_empty``.
    """
    manifest = Manifest.load(slug_dir)
    if manifest is None:
        raise PipelineError(f"no hay manifest en {slug_dir}")
    raw_dir = slug_dir / "raw"
    raw_chapters = _load_all_from_disk(raw_dir)
    if not raw_chapters:
        raise PipelineError("no hay capitulos descargados en disco")
    if volume_size is not None and volume_size < 1:
        raise PipelineError("volume_size debe ser >= 1")

    manifest.volume_size = volume_size
    metadata = NovelMetadata(
        title=manifest.title,
        author=manifest.author,
        cover_url=manifest.cover_path,
        source_url=manifest.source_url,
    )
    original_names = _generate_epubs(
        slug_dir=slug_dir,
        manifest=manifest,
        metadata=metadata,
        chapters=_build_epub_chapters(raw_chapters, raw_dir, EMPTY_PLACEHOLDER_EN),
        volume_size=volume_size,
        language=_epub_language(manifest.language_code),
        translated=False,
        resume=True,
        force=False,
        rebuild=True,
        on_progress=None,
    )
    manifest.epub_original = original_names

    translated_dir = slug_dir / "translated"
    if manifest.translated or any(translated_dir.glob("*.md")):
        lang = manifest.translated_language or config.translate_target_default()
        es_names = _generate_epubs(
            slug_dir=slug_dir,
            manifest=manifest,
            metadata=metadata,
            chapters=_build_epub_chapters(
                raw_chapters, translated_dir, _translated_placeholder(lang)
            ),
            volume_size=volume_size,
            language=lang,
            translated=True,
            resume=True,
            force=False,
            rebuild=True,
            on_progress=None,
        )
        manifest.epub_translated = es_names

    refresh_empty_counts(raw_dir, manifest)
    _cleanup_orphan_epubs(
        slug_dir,
        keep=manifest.epub_original + manifest.epub_translated,
    )
    manifest.save(slug_dir)
    return manifest