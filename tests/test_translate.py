"""Unit tests de traduccion (respx al endpoint gtx): segmentos, chunking, cache."""

from __future__ import annotations

import time

import httpx
import pytest
import respx

from novel_cli.core.config import DEFAULT_MAX_WORDS_PER_CHUNK
from novel_cli.core.models.novel import Chapter
from novel_cli.core.models.state import Manifest
from novel_cli.core.scraper.fetcher import CooldownGate, Pacer
from novel_cli.core.services.translate import (
    GTX_ENDPOINT,
    GoogleFreeTranslator,
    TranslateError,
    translate_chapter,
    translate_chapters,
    translate_paragraphs,
)
from novel_cli.core.utils.names import chapter_filename


def echo_handler(request: httpx.Request) -> httpx.Response:
    q = request.url.params.get("q", "")
    return httpx.Response(200, json=[[[q, q, None, None]], "en", None, None])


def make_translator(**kw) -> GoogleFreeTranslator:
    kw.setdefault("pacer", Pacer(0))
    kw.setdefault("max_retries", 3)
    kw.setdefault("backoff_base", 0.0)
    return GoogleFreeTranslator(**kw)


def make_manifest(slug_dir) -> Manifest:
    return Manifest(slug="novela", title="Novela")


@pytest.mark.asyncio
async def test_translate_text_concat_segments():
    with respx.mock() as router:
        route = router.get(GTX_ENDPOINT)
        route.mock(
            return_value=httpx.Response(
                200,
                json=[
                    [
                        ["Hola mundo", "Hello world", None, None],
                    ],
                    "en",
                    None,
                    None,
                ],
            )
        )
        translator = make_translator()
        try:
            result = await translator.translate_text("Hello world", target="es")
            assert result == "Hola mundo"
            assert route.call_count == 1
        finally:
            await translator.aclose()


@pytest.mark.asyncio
async def test_translate_text_empty_returns_as_is():
    translator = make_translator()
    try:
        assert await translator.translate_text("   ", target="es") == "   "
    finally:
        await translator.aclose()


@pytest.mark.asyncio
async def test_chunking_respects_max_words():
    paragraphs = ["word " * 200 for _ in range(3)]
    received: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params.get("q", "")
        received.append(q)
        return echo_handler(request)

    with respx.mock() as router:
        router.get(GTX_ENDPOINT).mock(side_effect=handler)
        translator = make_translator()
        try:
            result = await translate_paragraphs(
                paragraphs, translator, max_words_per_chunk=300
            )
            assert len(result) == 3
            assert len(received) >= 2
            assert all(len(q.split()) <= 300 for q in received)
        finally:
            await translator.aclose()


@pytest.mark.asyncio
async def test_reassembly_1to1_paragraphs():
    paragraphs = ["Hello there.", "How are you?", "Goodbye!"]
    with respx.mock() as router:
        router.get(GTX_ENDPOINT).mock(side_effect=echo_handler)
        translator = make_translator()
        try:
            result = await translate_paragraphs(paragraphs, translator)
            assert result == paragraphs
        finally:
            await translator.aclose()


@pytest.mark.asyncio
async def test_empty_paragraphs_preserved_and_not_sent():
    paragraphs = ["First.", "", "   ", "Last."]
    received: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request.url.params.get("q", ""))
        return echo_handler(request)

    with respx.mock() as router:
        router.get(GTX_ENDPOINT).mock(side_effect=handler)
        translator = make_translator()
        try:
            result = await translate_paragraphs(paragraphs, translator)
            assert result[1] == ""
            assert result[2] == "   "
            assert all(q.strip() for q in received)  # ningun q vacio fue enviado
        finally:
            await translator.aclose()


@pytest.mark.asyncio
async def test_translate_chapter_keeps_identity():
    chapter = Chapter(num=7, title="Chapter 7", url="https://example.com/7", paragraphs=["A", "B"])
    with respx.mock() as router:
        router.get(GTX_ENDPOINT).mock(side_effect=echo_handler)
        translator = make_translator()
        try:
            translated = await translate_chapter(chapter, translator)
            assert translated.num == 7
            assert translated.title == "Chapter 7"
            assert translated.url == chapter.url
            assert translated.paragraphs == ["A", "B"]
        finally:
            await translator.aclose()


@pytest.mark.asyncio
async def test_retry_429_then_ok():
    with respx.mock() as router:
        route = router.get(GTX_ENDPOINT)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(200, json=[[["ok", "ok", None, None]], "en", None, None]),
        ]
        translator = make_translator()
        try:
            result = await translator.translate_text("hola", target="es")
            assert result == "ok"
            assert route.call_count == 2
        finally:
            await translator.aclose()


@pytest.mark.asyncio
async def test_persistent_429_raises():
    with respx.mock() as router:
        route = router.get(GTX_ENDPOINT)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(429, headers={"retry-after": "0"}),
        ]
        translator = make_translator(max_retries=3)
        try:
            with pytest.raises(TranslateError) as exc:
                await translator.translate_text("hola", target="es")
            assert exc.value.status_code == 429
            assert route.call_count == 4
        finally:
            await translator.aclose()


def test_rate_delay_caps_retry_after():
    translator = GoogleFreeTranslator()
    capped = translator._rate_delay(
        httpx.Response(429, headers={"retry-after": "120"}), 0
    )
    assert capped == 60.0
    # sin Retry-After: backoff base 5 * 2^attempt, cap 60
    plain = httpx.Response(429)
    assert translator._rate_delay(plain, 0) == 5.0
    assert translator._rate_delay(plain, 2) == 20.0
    assert translator._rate_delay(plain, 5) == 60.0


@pytest.mark.asyncio
async def test_translate_text_honors_pre_set_cooldown():
    cooldown = CooldownGate()
    await cooldown.trigger(0.10)
    with respx.mock() as router:
        router.get(GTX_ENDPOINT).mock(
            return_value=httpx.Response(200, json=[[["ok", "ok", None, None]], "en", None, None])
        )
        translator = make_translator(cooldown=cooldown)
        try:
            start = time.monotonic()
            result = await translator.translate_text("hola", target="es")
            elapsed = time.monotonic() - start
            assert result == "ok"
            assert elapsed >= 0.08
        finally:
            await translator.aclose()


@pytest.mark.asyncio
async def test_429_triggers_cooldown_for_next_request():
    cooldown = CooldownGate()
    with respx.mock() as router:
        route = router.get(GTX_ENDPOINT)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "0.05"}),
            httpx.Response(429, headers={"retry-after": "0.05"}),
            httpx.Response(200, json=[[["ok", "ok", None, None]], "en", None, None]),
        ]
        first = make_translator(cooldown=cooldown, max_retries=1, backoff_base=0.0)
        second = make_translator(cooldown=cooldown, max_retries=1, backoff_base=0.0)
        try:
            with pytest.raises(TranslateError):
                await first.translate_text("hola", target="es")
            start = time.monotonic()
            result = await second.translate_text("mundo", target="es")
            elapsed = time.monotonic() - start
            assert result == "ok"
            assert elapsed >= 0.03
        finally:
            await first.aclose()
            await second.aclose()


@pytest.mark.asyncio
async def test_cache_skips_existing_translated(tmp_path):
    chapters = [Chapter(num=i, title=f"Ch {i}", url=f"u{i}", paragraphs=["X"]) for i in (1, 2)]
    translated_dir = tmp_path / "translated"
    translated_dir.mkdir()
    translated_dir.joinpath(chapter_filename(2)).write_text(
        "# Ch 2\n\ncached\n", encoding="utf-8"
    )
    received: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request.url.params.get("q", ""))
        return echo_handler(request)

    with respx.mock() as router:
        router.get(GTX_ENDPOINT).mock(side_effect=handler)
        translator = make_translator()
        manifest = make_manifest(tmp_path)
        try:
            await translate_chapters(
                translator=translator,
                chapters=chapters,
                slug_dir=tmp_path,
                manifest=manifest,
                max_words_per_chunk=DEFAULT_MAX_WORDS_PER_CHUNK,
            )
        finally:
            await translator.aclose()
    # solo se tradujo el capitulo 1
    assert len(received) == 1
    assert manifest.chapters_translated == 2
    assert manifest.translated is True


@pytest.mark.asyncio
async def test_force_retranslates_all(tmp_path):
    chapters = [Chapter(num=1, title="Ch 1", url="u1", paragraphs=["X"])]
    translated_dir = tmp_path / "translated"
    translated_dir.mkdir()
    translated_dir.joinpath(chapter_filename(1)).write_text(
        "# Ch 1\n\nold\n", encoding="utf-8"
    )
    received: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request.url.params.get("q", ""))
        return echo_handler(request)

    with respx.mock() as router:
        router.get(GTX_ENDPOINT).mock(side_effect=handler)
        translator = make_translator()
        manifest = make_manifest(tmp_path)
        try:
            await translate_chapters(
                translator=translator,
                chapters=chapters,
                slug_dir=tmp_path,
                manifest=manifest,
                force=True,
            )
        finally:
            await translator.aclose()
    assert len(received) == 1
    content = (translated_dir / chapter_filename(1)).read_text(encoding="utf-8")
    assert content.startswith("# Ch 1")