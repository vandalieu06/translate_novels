"""Traduccion: cliente al endpoint gratuito de Google Translate + chunking + cache."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Protocol

import httpx

from novel_cli.core import config
from novel_cli.core.models.novel import Chapter
from novel_cli.core.models.state import Manifest
from novel_cli.core.scraper.fetcher import Pacer, parse_retry_after
from novel_cli.core.services.download import format_chapter
from novel_cli.core.utils.names import chapter_filename
from novel_cli.core.utils.text import split_text_by_words

GTX_ENDPOINT = "https://translate.googleapis.com/translate_a/single"


class TranslateError(Exception):
    """Fallo de traduccion tras agotar reintentos."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class Translator(Protocol):
    async def translate_text(
        self, text: str, *, source: str = "auto", target: str = "es"
    ) -> str: ...


class GoogleFreeTranslator:
    """Cliente del endpoint translate_a/single (client=gtx) con retry/pacing."""

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        pacer: Pacer | None = None,
        max_retries: int = config.RETRY_RATE_LIMIT,
        backoff_base: float = config.RETRY_BACKOFF_BASE_SECONDS,
    ):
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=config.DEFAULT_HTTP_TIMEOUT_SECONDS,
            headers={"User-Agent": "novel-cli/0.2"},
        )
        self.pacer = pacer or Pacer(config.TRANSLATE_REQUEST_MIN_INTERVAL_MS)
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    async def translate_text(
        self, text: str, *, source: str = "auto", target: str = "es"
    ) -> str:
        if not text.strip():
            return text
        params = {"client": "gtx", "dt": "t", "sl": source, "tl": target, "q": text}
        for attempt in range(self.max_retries + 1):
            await self.pacer.acquire()
            try:
                response = await self._client.get(GTX_ENDPOINT, params=params)
            except httpx.HTTPError as exc:
                if attempt < self.max_retries:
                    await asyncio.sleep(self._backoff(attempt))
                    continue
                raise TranslateError(f"network error: {exc}") from exc

            if response.status_code == 200:
                return _parse_response(response.json())

            if response.status_code in (429, 503):
                delay = self._rate_delay(response, attempt)
                if attempt < self.max_retries:
                    await asyncio.sleep(delay)
                    continue
                raise TranslateError(
                    f"rate limited ({response.status_code})", status_code=response.status_code
                )

            if attempt < self.max_retries:
                await asyncio.sleep(self._backoff(attempt))
                continue
            raise TranslateError(
                f"HTTP {response.status_code}", status_code=response.status_code
            )

        raise TranslateError("unreachable")

    def _backoff(self, attempt: int) -> float:
        return min(self.backoff_base * (2**attempt), config.RETRY_AFTER_MAX_SECONDS)

    def _rate_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = parse_retry_after(response.headers.get("retry-after"))
        if retry_after is not None:
            return min(retry_after, config.RETRY_AFTER_MAX_SECONDS)
        return self._backoff(attempt)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class OllamaTranslator:
    """Backend opcional con LLM local (fuera de alcance v1)."""

    async def translate_text(
        self, text: str, *, source: str = "auto", target: str = "es"
    ) -> str:
        raise NotImplementedError("OllamaTranslator no esta implementado en v1")


async def translate_paragraphs(
    paragraphs: list[str],
    translator: Translator,
    *,
    target: str = "es",
    max_words_per_chunk: int = config.DEFAULT_MAX_WORDS_PER_CHUNK,
) -> list[str]:
    """Traduce parrafos por chunks y reensambla 1:1 (los vacios se conservan)."""
    non_empty = [i for i, paragraph in enumerate(paragraphs) if paragraph.strip()]
    if not non_empty:
        return list(paragraphs)

    source_texts = [paragraphs[i] for i in non_empty]
    chunks = split_text_by_words(source_texts, max_words_per_chunk)
    translated_chunks = [
        await translator.translate_text(chunk, target=target) for chunk in chunks
    ]

    lines: list[str] = []
    for chunk in translated_chunks:
        lines.extend(chunk.split("\n"))
    if len(lines) < len(source_texts):
        lines.extend([""] * (len(source_texts) - len(lines)))

    result = list(paragraphs)
    for index, text in zip(non_empty, lines[: len(source_texts)], strict=False):
        result[index] = text
    return result


async def translate_chapter(
    chapter: Chapter,
    translator: Translator,
    *,
    target: str = "es",
    max_words_per_chunk: int = config.DEFAULT_MAX_WORDS_PER_CHUNK,
) -> Chapter:
    """Devuelve un Chapter con paragraphs traducidos (num/title/url intactos)."""
    translated = await translate_paragraphs(
        chapter.paragraphs,
        translator,
        target=target,
        max_words_per_chunk=max_words_per_chunk,
    )
    return Chapter(
        num=chapter.num,
        title=chapter.title,
        url=chapter.url,
        paragraphs=translated,
    )


async def translate_chapters(
    *,
    translator: Translator,
    chapters: list[Chapter],
    slug_dir: Path,
    manifest: Manifest,
    target: str = "es",
    max_words_per_chunk: int = config.DEFAULT_MAX_WORDS_PER_CHUNK,
    force: bool = False,
    on_progress=None,
) -> list[Chapter]:
    """Traduce capitulos no cacheados a translated/<NNNN>.md y actualiza manifest."""
    translated_dir = slug_dir / "translated"
    translated_dir.mkdir(parents=True, exist_ok=True)
    existing_nums = {int(path.stem) for path in translated_dir.glob("*.md")}
    todo = [chapter for chapter in chapters if force or chapter.num not in existing_nums]

    completed: list[Chapter] = []
    total = len(todo)
    done = 0
    for chapter in todo:
        translated = await translate_chapter(
            chapter, translator, target=target, max_words_per_chunk=max_words_per_chunk
        )
        translated_dir.joinpath(chapter_filename(chapter.num)).write_text(
            format_chapter(translated, translated.paragraphs), encoding="utf-8"
        )
        completed.append(translated)
        done += 1
        if on_progress:
            on_progress(done, total)

    translated_nums = {chapter.num for chapter in completed} | existing_nums
    manifest.chapters_translated = len(translated_nums)
    manifest.translated = True
    manifest.save(slug_dir)
    return completed


def _parse_response(data: object) -> str:
    segments = data[0]
    parts: list[str] = []
    for segment in segments:
        if segment and segment[0]:
            parts.append(str(segment[0]))
    return "".join(parts)