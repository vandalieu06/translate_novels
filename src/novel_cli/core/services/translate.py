"""Traduccion: backends (Google, LibreTranslate, Ollama) + chunking + cache."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Protocol

import httpx

from novel_cli.core import config
from novel_cli.core.models.novel import Chapter
from novel_cli.core.models.state import Manifest
from novel_cli.core.scraper.fetcher import (
    CHROME_HEADERS,
    CooldownGate,
    Pacer,
    parse_retry_after,
)
from novel_cli.core.services.download import (
    format_chapter,
    is_chapter_empty,
    load_chapter,
)
from novel_cli.core.utils.names import chapter_filename
from novel_cli.core.utils.text import split_text_by_words

GTX_ENDPOINT = "https://translate.googleapis.com/translate_a/single"

logger = logging.getLogger(__name__)


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
        cooldown: CooldownGate | None = None,
        max_retries: int = config.TRANSLATE_RETRY_RATE_LIMIT,
        backoff_base: float = config.TRANSLATE_BACKOFF_BASE_SECONDS,
    ):
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=config.DEFAULT_HTTP_TIMEOUT_SECONDS,
            headers={
                "User-Agent": CHROME_HEADERS["User-Agent"],
                "Accept": CHROME_HEADERS["Accept"],
                "Accept-Language": CHROME_HEADERS["Accept-Language"],
                "Referer": "https://translate.google.com/",
            },
        )
        self.pacer = pacer or Pacer(config.TRANSLATE_REQUEST_MIN_INTERVAL_MS)
        self.cooldown = cooldown or CooldownGate()
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    async def translate_text(
        self, text: str, *, source: str = "auto", target: str = "es"
    ) -> str:
        if not text.strip():
            return text
        params = {"client": "gtx", "dt": "t", "sl": source, "tl": target, "q": text}
        for attempt in range(self.max_retries + 1):
            await self.cooldown.wait()
            await self.pacer.acquire()
            try:
                response = await self._client.get(GTX_ENDPOINT, params=params)
            except httpx.HTTPError as exc:
                if attempt < self.max_retries:
                    delay = self._backoff(attempt)
                    logger.debug(
                        "traduccion: reintento de red (intento %d/%d, espera %.1fs): %s",
                        attempt + 1,
                        self.max_retries,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise TranslateError(f"network error: {exc}") from exc

            if response.status_code == 200:
                return _parse_response(response.json())

            if response.status_code in (429, 503):
                delay = self._rate_delay(response, attempt)
                await self.cooldown.trigger(delay)
                logger.warning(
                    "traduccion: rate-limit %s; cool-down %.1fs (intento %d/%d)",
                    response.status_code,
                    delay,
                    attempt + 1,
                    self.max_retries,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(delay)
                    continue
                raise TranslateError(
                    f"rate limited ({response.status_code}); "
                    "espera un poco y re-ejecuta (la cache conserva lo traducido)",
                    status_code=response.status_code,
                )

            if attempt < self.max_retries:
                await asyncio.sleep(self._backoff(attempt))
                continue
            raise TranslateError(
                f"HTTP {response.status_code}", status_code=response.status_code
            )

        raise TranslateError("unreachable")

    def _backoff(self, attempt: int) -> float:
        return min(
            self.backoff_base * (2**attempt),
            config.TRANSLATE_RETRY_AFTER_MAX_SECONDS,
        )

    def _rate_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = parse_retry_after(response.headers.get("retry-after"))
        if retry_after is not None:
            return min(retry_after, config.TRANSLATE_RETRY_AFTER_MAX_SECONDS)
        return self._backoff(attempt)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class LibreTranslateTranslator:
    """Cliente de LibreTranslate local (POST /translate), sin rate-limit propio."""

    def __init__(
        self,
        *,
        base_url: str = config.TRANSLATE_URL,
        api_key: str | None = None,
        client: httpx.AsyncClient | None = None,
        pacer: Pacer | None = None,
        cooldown: CooldownGate | None = None,
        max_retries: int = config.TRANSLATE_RETRY_RATE_LIMIT,
        backoff_base: float = config.TRANSLATE_BACKOFF_BASE_SECONDS,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=config.DEFAULT_HTTP_TIMEOUT_SECONDS
        )
        self.pacer = pacer or Pacer(200)
        self.cooldown = cooldown or CooldownGate()
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    async def translate_text(
        self, text: str, *, source: str = "auto", target: str = "es"
    ) -> str:
        if not text.strip():
            return text
        payload = {"q": text, "source": source, "target": target, "format": "text"}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        for attempt in range(self.max_retries + 1):
            await self.cooldown.wait()
            await self.pacer.acquire()
            try:
                response = await self._client.post(
                    f"{self.base_url}/translate", json=payload, headers=headers
                )
            except httpx.HTTPError as exc:
                if attempt < self.max_retries:
                    delay = self._backoff(attempt)
                    logger.debug(
                        "traduccion libre: reintento de red (intento %d/%d, espera %.1fs): %s",
                        attempt + 1,
                        self.max_retries,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise TranslateError(f"network error: {exc}") from exc

            if response.status_code == 200:
                return response.json()["translatedText"]

            if response.status_code in (429, 503):
                delay = self._rate_delay(response, attempt)
                await self.cooldown.trigger(delay)
                logger.warning(
                    "traduccion libre: rate-limit %s; cool-down %.1fs (intento %d/%d)",
                    response.status_code,
                    delay,
                    attempt + 1,
                    self.max_retries,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(delay)
                    continue
                raise TranslateError(
                    f"rate limited ({response.status_code}); espera y re-ejecuta",
                    status_code=response.status_code,
                )

            if attempt < self.max_retries:
                await asyncio.sleep(self._backoff(attempt))
                continue
            raise TranslateError(
                f"HTTP {response.status_code}", status_code=response.status_code
            )

        raise TranslateError("unreachable")

    def _backoff(self, attempt: int) -> float:
        return min(
            self.backoff_base * (2**attempt),
            config.TRANSLATE_RETRY_AFTER_MAX_SECONDS,
        )

    def _rate_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = parse_retry_after(response.headers.get("retry-after"))
        if retry_after is not None:
            return min(retry_after, config.TRANSLATE_RETRY_AFTER_MAX_SECONDS)
        return self._backoff(attempt)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class OllamaTranslator:
    """Backend de traduccion con un LLM local via Ollama (POST /api/chat).

    Usa el prompt oficial de TranslateGemma (una sola user message, con dos
    lineas en blanco antes del texto). El modelo devuelve una linea por parrafo
    (validado en el spike), por lo que el reensamblado 1:1 de
    ``translate_paragraphs`` funciona sin cambios. Si la salida no respeta la
    estructura, se reintenta con una instruccion extra y, si persiste, se
    traduce **linea a linea** (una por parrafo) para no dejar parrafos vacios;
    nunca falla el job.
    """

    _PRESERVE_BREAKS = (
        "Preserve the paragraph breaks (one line per paragraph) of the original text. "
    )

    def __init__(
        self,
        *,
        base_url: str = config.OLLAMA_URL,
        model: str = config.OLLAMA_MODEL,
        source_lang: str = config.OLLAMA_SOURCE_LANG,
        client: httpx.AsyncClient | None = None,
        timeout: float = config.OLLAMA_TIMEOUT_SECONDS,
        keep_alive: str = config.OLLAMA_KEEP_ALIVE,
        pacer: Pacer | None = None,
        cooldown: CooldownGate | None = None,
        max_retries: int = config.TRANSLATE_RETRY_RATE_LIMIT,
        backoff_base: float = config.TRANSLATE_BACKOFF_BASE_SECONDS,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.source_lang = source_lang
        self.timeout = timeout
        self.keep_alive = keep_alive
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self.pacer = pacer or Pacer(config.TRANSLATE_REQUEST_MIN_INTERVAL_MS)
        self.cooldown = cooldown or CooldownGate()
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    async def translate_text(
        self, text: str, *, source: str = "auto", target: str = "es"
    ) -> str:
        if not text.strip():
            return text
        source = source if source and source != "auto" else self.source_lang
        source_name = config.language_name_en(source)
        target_name = config.language_name_en(target)

        result = await self._chat(self._prompt(source, source_name, target, target_name, text))
        if self._line_count(result) == self._line_count(text):
            return result

        logger.warning(
            "traduccion ollama: la salida no respeto los parrafos (%d lineas vs %d); reintentando",
            self._line_count(result),
            self._line_count(text),
        )
        retry = await self._chat(
            self._prompt(
                source, source_name, target, target_name, text, preserve_breaks=True
            )
        )
        if self._line_count(retry) == self._line_count(text):
            return retry

        logger.warning(
            "traduccion ollama: fallback linea a linea (parrafos %d/%d); "
            "se traduce cada parrafo por separado",
            self._line_count(retry),
            self._line_count(text),
        )
        return await self._translate_line_by_line(
            source, source_name, target, target_name, text
        )

    async def _translate_line_by_line(
        self,
        source: str,
        source_name: str,
        target: str,
        target_name: str,
        text: str,
    ) -> str:
        """Traduce cada parrafo por separado para garantizar 1 linea por parrafo.

        Si una linea no produce traduccion, se conserva el texto original (mejor
        que un parrafo vacio en el EPUB).
        """
        lines = [line for line in text.split("\n") if line.strip()]
        out_lines: list[str] = []
        for line in lines:
            result = await self._chat(
                self._prompt(source, source_name, target, target_name, line)
            )
            candidate = next((item for item in result.splitlines() if item.strip()), "")
            out_lines.append(candidate or line)
        return "\n".join(out_lines)

    def _prompt(
        self,
        source: str,
        source_name: str,
        target: str,
        target_name: str,
        text: str,
        *,
        preserve_breaks: bool = False,
    ) -> str:
        preserve = self._PRESERVE_BREAKS if preserve_breaks else ""
        return (
            f"You are a professional {source_name} ({source}) to {target_name} "
            f"({target}) translator. Your goal is to accurately convey the meaning "
            f"and nuances of the original {source_name} text while adhering to "
            f"{target_name} grammar, vocabulary, and cultural sensitivities.\n"
            f"{preserve}Produce only the {target_name} translation, without any "
            f"additional explanations or commentary. Please translate the following "
            f"{source_name} text into {target_name}:\n\n\n{text}"
        )

    async def _chat(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {"temperature": 0},
        }
        for attempt in range(self.max_retries + 1):
            await self.cooldown.wait()
            await self.pacer.acquire()
            try:
                response = await self._client.post(
                    f"{self.base_url}/api/chat", json=payload, timeout=self.timeout
                )
            except httpx.HTTPError as exc:
                if attempt < self.max_retries:
                    delay = self._backoff(attempt)
                    logger.debug(
                        "traduccion ollama: reintento de red (intento %d/%d, espera %.1fs): %s",
                        attempt + 1,
                        self.max_retries,
                        delay,
                        exc,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise TranslateError(f"network error: {exc}") from exc

            if response.status_code == 200:
                return response.json()["message"]["content"]

            if response.status_code in (400, 404):
                detail = response.text[:200]
                raise TranslateError(
                    f"HTTP {response.status_code} ({self.model}): {detail}",
                    status_code=response.status_code,
                )

            if response.status_code in (429, 503):
                delay = self._rate_delay(response, attempt)
                await self.cooldown.trigger(delay)
                logger.warning(
                    "traduccion ollama: rate-limit %s; cool-down %.1fs (intento %d/%d)",
                    response.status_code,
                    delay,
                    attempt + 1,
                    self.max_retries,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(delay)
                    continue
                raise TranslateError(
                    f"rate limited ({response.status_code}); espera y re-ejecuta",
                    status_code=response.status_code,
                )

            if attempt < self.max_retries:
                await asyncio.sleep(self._backoff(attempt))
                continue
            raise TranslateError(
                f"HTTP {response.status_code}", status_code=response.status_code
            )

        raise TranslateError("unreachable")

    def _backoff(self, attempt: int) -> float:
        return min(
            self.backoff_base * (2**attempt),
            config.TRANSLATE_RETRY_AFTER_MAX_SECONDS,
        )

    def _rate_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = parse_retry_after(response.headers.get("retry-after"))
        if retry_after is not None:
            return min(retry_after, config.TRANSLATE_RETRY_AFTER_MAX_SECONDS)
        return self._backoff(attempt)

    @staticmethod
    def _line_count(value: str) -> int:
        return sum(1 for line in value.splitlines() if line.strip())

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


def build_default_translator() -> Translator:
    """Selecciona el backend por env NOVEL_TRANSLATE_BACKEND (google | libre | ollama)."""
    if config.TRANSLATE_BACKEND == "libre":
        return LibreTranslateTranslator(
            base_url=config.TRANSLATE_URL,
            api_key=config.TRANSLATE_API_KEY,
        )
    if config.TRANSLATE_BACKEND == "ollama":
        return OllamaTranslator()
    return GoogleFreeTranslator()


async def translate_paragraphs(
    paragraphs: list[str],
    translator: Translator,
    *,
    target: str = "es",
    source: str = "auto",
    max_words_per_chunk: int = config.DEFAULT_MAX_WORDS_PER_CHUNK,
) -> list[str]:
    """Traduce parrafos por chunks y reensambla 1:1 (los vacios se conservan)."""
    non_empty = [i for i, paragraph in enumerate(paragraphs) if paragraph.strip()]
    if not non_empty:
        return list(paragraphs)

    source_texts = [paragraphs[i] for i in non_empty]
    chunks = split_text_by_words(source_texts, max_words_per_chunk)
    translated_chunks = [
        await translator.translate_text(chunk, source=source, target=target)
        for chunk in chunks
    ]

    lines: list[str] = []
    for chunk in translated_chunks:
        # Solo lineas con contenido: los backends NMT devuelven una linea por
        # parrafo, pero un LLM puede intercalar lineas en blanco (que
        # desplazarian el mapeo 1:1) o un salto final.
        lines.extend(line for line in chunk.split("\n") if line.strip())
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
    source: str = "auto",
    max_words_per_chunk: int = config.DEFAULT_MAX_WORDS_PER_CHUNK,
) -> Chapter:
    """Devuelve un Chapter con paragraphs traducidos (num/title/url intactos)."""
    translated = await translate_paragraphs(
        chapter.paragraphs,
        translator,
        target=target,
        source=source,
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
    source: str = "auto",
    max_words_per_chunk: int | None = None,
    force: bool = False,
    concurrency: int = 1,
    on_progress=None,
) -> list[Chapter]:
    """Traduce capitulos no cacheados a translated/<NNNN>.md y actualiza manifest.

    ``concurrency`` paraleliza la traduccion de capitulos con un pool async
    (patron identico a ``download_chapters``). El Pacer/CooldownGate compartidos
    del translator siguen limitando el ritmo global de peticiones.
    """
    if max_words_per_chunk is None:
        max_words_per_chunk = config.translate_max_words_per_chunk()
    translated_dir = slug_dir / "translated"
    translated_dir.mkdir(parents=True, exist_ok=True)
    # Un translated/<NNNN>.md vacio (heredado de cuando el raw estaba vacio) no
    # cuenta como "ya traducido": si el raw tiene contenido se re-traduce.
    existing_nums = {
        int(path.stem)
        for path in translated_dir.glob("*.md")
        if not is_chapter_empty(load_chapter(path, int(path.stem), "").paragraphs)
    }
    todo = [chapter for chapter in chapters if force or chapter.num not in existing_nums]
    # Los capitulos vacios (sin contenido en raw) no se traducen ni se marcan.
    # Se limpia ademas el translated/<NNNN>.md vacio stale para que el EPUB
    # traducido no incluya capitulos en blanco.
    skipped_empty: list[Chapter] = []
    filtered: list[Chapter] = []
    for chapter in todo:
        if is_chapter_empty(chapter.paragraphs):
            skipped_empty.append(chapter)
        else:
            filtered.append(chapter)
    todo = filtered
    for chapter in skipped_empty:
        stale = translated_dir / chapter_filename(chapter.num)
        if stale.exists() and is_chapter_empty(
            load_chapter(stale, chapter.num, "").paragraphs
        ):
            stale.unlink()

    if not todo:
        logger.info(
            "traduccion (%s): sin pendientes (%d ya traducidos)", target, len(existing_nums)
        )
        manifest.chapters_translated = len(existing_nums)
        manifest.translated = True
        manifest.save(slug_dir)
        return []

    semaphore = asyncio.Semaphore(max(1, concurrency))
    completed: list[Chapter] = []
    done = 0
    total = len(todo)
    logger.info(
        "traduccion (%s): %d pendientes de %d capitulos (concurrencia %d, cache %d)",
        target,
        total,
        len(chapters),
        concurrency,
        len(existing_nums),
    )

    async def work(chapter: Chapter) -> None:
        nonlocal done
        async with semaphore:
            translated = await translate_chapter(
                chapter,
                translator,
                target=target,
                source=source,
                max_words_per_chunk=max_words_per_chunk,
            )
            translated_dir.joinpath(chapter_filename(chapter.num)).write_text(
                format_chapter(translated, translated.paragraphs), encoding="utf-8"
            )
        completed.append(translated)
        done += 1
        logger.debug("capitulo %d traducido (%d/%d)", chapter.num, done, total)
        if on_progress:
            on_progress(done, total)

    await asyncio.gather(*(work(chapter) for chapter in todo))

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