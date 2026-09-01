"""Descarga de capitulos: pool async httpx con pacing, manifest y raw/NNNN.md."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from novel_cli.core.config import DEFAULT_CONCURRENCY, EMPTY_RETRIES, EMPTY_RETRY_BACKOFF
from novel_cli.core.models.novel import Chapter, NovelMetadata
from novel_cli.core.models.state import Manifest
from novel_cli.core.scraper.base import Fetcher, SiteAdapter
from novel_cli.core.scraper.fetcher import FetchError, Pacer
from novel_cli.core.utils.names import chapter_filename

ProgressCallback = Callable[[int, int], None]


class DownloadError(Exception):
    """Algun capitulo fallo tras agotar reintentos."""


def is_chapter_empty(paragraphs: list[str]) -> bool:
    """Un capitulo se considera vacio si no tiene ningun parrafo con contenido."""
    return not [p for p in paragraphs if p.strip()]


def _refresh_empty_counts(raw_dir: Path, manifest: Manifest) -> None:
    """Recalcula chapters_empty/_nums desde los archivos raw del disco."""
    nums: list[int] = []
    for path in raw_dir.glob("*.md"):
        try:
            num = int(path.stem)
        except ValueError:
            continue
        if is_chapter_empty(load_chapter(path, num, "").paragraphs):
            nums.append(num)
    manifest.chapters_empty = len(nums)
    manifest.chapters_empty_nums = sorted(nums)


async def download_chapters(
    *,
    fetcher: Fetcher,
    adapter: SiteAdapter,
    metadata: NovelMetadata,
    chapters: list[Chapter],
    slug_dir: Path,
    manifest: Manifest,
    force: bool = False,
    concurrency: int = DEFAULT_CONCURRENCY,
    pacer: Pacer | None = None,
    empty_retries: int = EMPTY_RETRIES,
    on_progress: ProgressCallback | None = None,
) -> list[Chapter]:
    """Descarga los capitulos que faltan (o todos con force) a raw/<NNNN>.md.

    Un capitulo con 0 parrafos tras el parse se considera vacio: se reintenta
    al final del lote con backoff y, si persiste, se deja pendiente (se reporta
    y no cuenta como descargado). El job no falla por capitulos vacios.
    """
    raw_dir = slug_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest.chapters_total = len(chapters)

    existing_nums = {
        int(path.stem)
        for path in raw_dir.glob("*.md")
        if not is_chapter_empty(load_chapter(path, int(path.stem), "").paragraphs)
    }
    missing = [
        chapter
        for chapter in chapters
        if force or chapter.num not in existing_nums
    ]

    if not missing:
        manifest.chapters_downloaded = len(existing_nums)
        _refresh_empty_counts(raw_dir, manifest)
        manifest.save(slug_dir)
        if on_progress:
            on_progress(len(chapters), len(chapters))
        return []

    pacer = pacer or Pacer()
    semaphore = asyncio.Semaphore(max(1, concurrency))
    completed: list[Chapter] = []
    failed: list[tuple[Chapter, Exception]] = []
    done = 0
    total = len(missing)

    async def fetch_one(chapter: Chapter) -> tuple[Chapter, list[str]] | None:
        nonlocal done
        async with semaphore:
            await pacer.acquire()
            try:
                html = await fetcher.fetch_html(chapter.url)
            except Exception as exc:  # noqa: BLE001 - recopilamos el fallo
                failed.append((chapter, exc))
                return None
            paragraphs = adapter.parse_chapter(html, chapter.url)
        done += 1
        if on_progress:
            on_progress(done, total)
        return chapter, paragraphs

    async def save(chapter: Chapter, paragraphs: list[str]) -> None:
        raw_dir.joinpath(chapter_filename(chapter.num)).write_text(
            format_chapter(chapter, paragraphs), encoding="utf-8"
        )
        completed.append(chapter)

    results = await asyncio.gather(*(fetch_one(ch) for ch in missing))
    empty: list[tuple[Chapter, list[str]]] = []
    for result in results:
        if result is None:
            continue
        chapter, paragraphs = result
        if is_chapter_empty(paragraphs):
            empty.append((chapter, paragraphs))
        else:
            await save(chapter, paragraphs)

    # Reintenta los vacios al final, secuencial, con backoff.
    still_empty: list[tuple[Chapter, list[str]]] = []
    for chapter, first_paragraphs in empty:
        resolved = False
        paragraphs = first_paragraphs
        for attempt in range(empty_retries):
            await pacer.acquire()
            try:
                html = await fetcher.fetch_html(chapter.url)
            except Exception as exc:  # noqa: BLE001 - recopilamos el fallo
                failed.append((chapter, exc))
                break
            paragraphs = adapter.parse_chapter(html, chapter.url)
            if not is_chapter_empty(paragraphs):
                await save(chapter, paragraphs)
                resolved = True
                break
            if attempt < len(EMPTY_RETRY_BACKOFF):
                await asyncio.sleep(EMPTY_RETRY_BACKOFF[attempt])
        if not resolved:
            still_empty.append((chapter, paragraphs))

    if failed:
        raise DownloadError(f"{len(failed)} capitulos fallaron al descargarse")

    manifest.chapters_empty = len(still_empty)
    manifest.chapters_empty_nums = sorted(
        {chapter.num for chapter, _ in still_empty}
    )
    downloaded = {chapter.num for chapter in completed} | existing_nums
    manifest.chapters_downloaded = len(downloaded)
    manifest.save(slug_dir)
    return completed


async def download_cover(
    fetcher: Fetcher, metadata: NovelMetadata, slug_dir: Path
) -> str | None:
    """Descarga la portada a cover.<ext>; devuelve el nombre relativo o None."""
    if not metadata.cover_url:
        return None
    try:
        data = await fetcher.fetch_bytes(metadata.cover_url)
    except FetchError:
        return None
    ext = _guess_image_ext(metadata.cover_url)
    name = f"cover.{ext}"
    (slug_dir / name).write_bytes(data)
    return name


def load_chapter(path: Path, num: int, url: str) -> Chapter:
    """Reconstruye un Chapter desde un archivo raw/<NNNN>.md o translated/."""
    text = path.read_text(encoding="utf-8").strip("\n")
    title = ""
    if text.startswith("# "):
        first, _, rest = text.partition("\n\n")
        title = first[2:].strip()
        text = rest
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    return Chapter(num=num, title=title, url=url, paragraphs=paragraphs)


def format_chapter(chapter: Chapter, paragraphs: list[str]) -> str:
    body = "\n\n".join(paragraphs)
    return f"# {chapter.title}\n\n{body}\n"


def _guess_image_ext(url: str) -> str:
    suffix = Path(url.split("?")[0]).suffix.lower().lstrip(".")
    return suffix if suffix in {"jpg", "jpeg", "png", "webp", "gif"} else "jpg"