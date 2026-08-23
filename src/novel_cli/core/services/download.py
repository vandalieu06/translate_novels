"""Descarga de capitulos: pool async httpx con pacing, manifest y raw/NNNN.md."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

from novel_cli.core.config import DEFAULT_CONCURRENCY
from novel_cli.core.models.novel import Chapter, NovelMetadata
from novel_cli.core.models.state import Manifest
from novel_cli.core.scraper.base import Fetcher, SiteAdapter
from novel_cli.core.scraper.fetcher import FetchError, Pacer
from novel_cli.core.utils.names import chapter_filename

ProgressCallback = Callable[[int, int], None]


class DownloadError(Exception):
    """Algun capitulo fallo tras agotar reintentos."""


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
    on_progress: ProgressCallback | None = None,
) -> list[Chapter]:
    """Descarga los capitulos que faltan (o todos con force) a raw/<NNNN>.md."""
    raw_dir = slug_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest.chapters_total = len(chapters)

    existing_nums = {int(path.stem) for path in raw_dir.glob("*.md")}
    missing = [
        chapter
        for chapter in chapters
        if force or chapter.num not in existing_nums
    ]

    if not missing:
        manifest.chapters_downloaded = len(existing_nums)
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

    async def work(chapter: Chapter) -> None:
        nonlocal done
        async with semaphore:
            await pacer.acquire()
            try:
                html = await fetcher.fetch_html(chapter.url)
            except Exception as exc:  # noqa: BLE001 - recopilamos el fallo
                failed.append((chapter, exc))
                return
            paragraphs = adapter.parse_chapter(html, chapter.url)
            raw_dir.joinpath(chapter_filename(chapter.num)).write_text(
                format_chapter(chapter, paragraphs), encoding="utf-8"
            )
            completed.append(chapter)
        done += 1
        if on_progress:
            on_progress(done, total)

    await asyncio.gather(*(work(chapter) for chapter in missing))

    if failed:
        raise DownloadError(f"{len(failed)} capitulos fallaron al descargarse")

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