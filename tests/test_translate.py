"""Unit tests de traduccion (respx al endpoint gtx): segmentos, chunking, cache."""

from __future__ import annotations

import json
import logging
import time

import httpx
import pytest
import respx

from novel_cli.core import config
from novel_cli.core.config import DEFAULT_MAX_WORDS_PER_CHUNK
from novel_cli.core.models.novel import Chapter
from novel_cli.core.models.state import Manifest
from novel_cli.core.scraper.fetcher import CooldownGate, Pacer
from novel_cli.core.services.translate import (
    GTX_ENDPOINT,
    GoogleFreeTranslator,
    LibreTranslateTranslator,
    OllamaTranslator,
    TranslateError,
    build_default_translator,
    translate_chapter,
    translate_chapters,
    translate_paragraphs,
)
from novel_cli.core.utils.names import chapter_filename

LIBRE_ENDPOINT = "http://localhost:5000/translate"
OLLAMA_CHAT = "http://localhost:11434/api/chat"


def echo_handler(request: httpx.Request) -> httpx.Response:
    q = request.url.params.get("q", "")
    return httpx.Response(200, json=[[[q, q, None, None]], "en", None, None])


def make_translator(**kw) -> GoogleFreeTranslator:
    kw.setdefault("pacer", Pacer(0))
    kw.setdefault("max_retries", 3)
    kw.setdefault("backoff_base", 0.0)
    return GoogleFreeTranslator(**kw)


def make_libre(**kw) -> LibreTranslateTranslator:
    kw.setdefault("pacer", Pacer(0))
    kw.setdefault("max_retries", 3)
    kw.setdefault("backoff_base", 0.0)
    kw.setdefault("base_url", "http://localhost:5000")
    return LibreTranslateTranslator(**kw)


def make_ollama(**kw) -> OllamaTranslator:
    kw.setdefault("pacer", Pacer(0))
    kw.setdefault("max_retries", 3)
    kw.setdefault("backoff_base", 0.0)
    kw.setdefault("base_url", "http://localhost:11434")
    return OllamaTranslator(**kw)


def ollama_response(content: str) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})


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
async def test_empty_chapters_skipped_by_translation(tmp_path):
    """Los capitulos vacios no se traducen ni se marcan como traducidos."""
    chapters = [
        Chapter(num=1, title="Ch 1", url="u1", paragraphs=["Real content"]),
        Chapter(num=2, title="Ch 2", url="u2", paragraphs=[]),
    ]
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
            )
        finally:
            await translator.aclose()
    # solo se tradujo el capitulo 1 (con contenido)
    assert len(received) == 1
    translated_dir = tmp_path / "translated"
    assert translated_dir.joinpath(chapter_filename(1)).exists()
    assert not translated_dir.joinpath(chapter_filename(2)).exists()
    assert manifest.chapters_translated == 1


@pytest.mark.asyncio
async def test_stale_empty_translated_retranslated(tmp_path):
    """Un translated/<NNNN>.md vacio (stale) se re-traduce si el raw tiene contenido."""
    chapters = [Chapter(num=1, title="Ch 1", url="u1", paragraphs=["Real content"])]
    translated_dir = tmp_path / "translated"
    translated_dir.mkdir()
    translated_dir.joinpath(chapter_filename(1)).write_text("# Ch 1\n\n", encoding="utf-8")
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
            )
        finally:
            await translator.aclose()
    assert len(received) == 1
    content = (translated_dir / chapter_filename(1)).read_text(encoding="utf-8")
    assert "Real content" in content
    assert manifest.chapters_translated == 1


@pytest.mark.asyncio
async def test_stale_empty_translated_cleaned_when_raw_empty(tmp_path):
    """Un translated/<NNNN>.md vacio cuyo raw sigue vacio se limpia (no se traduce)."""
    chapters = [Chapter(num=2, title="Ch 2", url="u2", paragraphs=[])]
    translated_dir = tmp_path / "translated"
    translated_dir.mkdir()
    translated_dir.joinpath(chapter_filename(2)).write_text("# Ch 2\n\n", encoding="utf-8")
    received: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request.url.params.get("q", ""))
        return echo_handler(request)

    with respx.mock(assert_all_called=False) as router:
        router.get(GTX_ENDPOINT).mock(side_effect=handler)
        translator = make_translator()
        manifest = make_manifest(tmp_path)
        try:
            await translate_chapters(
                translator=translator,
                chapters=chapters,
                slug_dir=tmp_path,
                manifest=manifest,
            )
        finally:
            await translator.aclose()
    assert received == []
    assert not translated_dir.joinpath(chapter_filename(2)).exists()
    assert manifest.chapters_translated == 0


@pytest.mark.asyncio
async def test_stale_empty_translated_mixed_cleanup_and_retranslate(tmp_path):
    """Mezcla: translated vacio con raw corregido se re-traduce; con raw vacio se limpia."""
    chapters = [
        Chapter(num=1, title="Ch 1", url="u1", paragraphs=["Real content"]),
        Chapter(num=2, title="Ch 2", url="u2", paragraphs=[]),
    ]
    translated_dir = tmp_path / "translated"
    translated_dir.mkdir()
    translated_dir.joinpath(chapter_filename(1)).write_text("# Ch 1\n\n", encoding="utf-8")
    translated_dir.joinpath(chapter_filename(2)).write_text("# Ch 2\n\n", encoding="utf-8")
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
            )
        finally:
            await translator.aclose()
    assert len(received) == 1
    content1 = (translated_dir / chapter_filename(1)).read_text(encoding="utf-8")
    assert "Real content" in content1
    assert not translated_dir.joinpath(chapter_filename(2)).exists()
    assert manifest.chapters_translated == 1


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


@pytest.mark.asyncio
async def test_libre_sends_payload_and_parses():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = request.content
        captured["headers"] = request.headers
        return httpx.Response(200, json={"translatedText": "Hola mundo"})

    with respx.mock() as router:
        router.post(LIBRE_ENDPOINT).mock(side_effect=handler)
        translator = make_libre()
        try:
            result = await translator.translate_text("Hello world", target="es")
            assert result == "Hola mundo"
        finally:
            await translator.aclose()
    import json

    body = json.loads(captured["json"])
    assert body == {
        "q": "Hello world",
        "source": "auto",
        "target": "es",
        "format": "text",
    }
    assert captured["headers"]["content-type"] == "application/json"


@pytest.mark.asyncio
async def test_libre_sends_api_key_header():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("authorization") == "Bearer secret-key"
        return httpx.Response(200, json={"translatedText": "ok"})

    with respx.mock() as router:
        router.post(LIBRE_ENDPOINT).mock(side_effect=handler)
        translator = make_libre(api_key="secret-key")
        try:
            assert await translator.translate_text("hola") == "ok"
        finally:
            await translator.aclose()


@pytest.mark.asyncio
async def test_libre_retry_429_then_ok():
    with respx.mock() as router:
        route = router.post(LIBRE_ENDPOINT)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(200, json={"translatedText": "ok"}),
        ]
        translator = make_libre()
        try:
            assert await translator.translate_text("hola") == "ok"
            assert route.call_count == 2
        finally:
            await translator.aclose()


@pytest.mark.asyncio
async def test_libre_reassembly_1to1():
    def echo_handler_libre(request: httpx.Request) -> httpx.Response:
        import json

        q = json.loads(request.content)["q"]
        return httpx.Response(200, json={"translatedText": q})

    paragraphs = ["Hello there.", "How are you?", "Goodbye!"]
    with respx.mock() as router:
        router.post(LIBRE_ENDPOINT).mock(side_effect=echo_handler_libre)
        translator = make_libre()
        try:
            result = await translate_paragraphs(paragraphs, translator)
            assert result == paragraphs
        finally:
            await translator.aclose()


def test_build_default_translator_default_google(monkeypatch):
    monkeypatch.setattr(config, "TRANSLATE_BACKEND", "google")
    assert isinstance(build_default_translator(), GoogleFreeTranslator)


def test_build_default_translator_libre(monkeypatch):
    monkeypatch.setattr(config, "TRANSLATE_BACKEND", "libre")
    monkeypatch.setattr(config, "TRANSLATE_URL", "http://127.0.0.1:5000")
    translator = build_default_translator()
    assert isinstance(translator, LibreTranslateTranslator)
    assert translator.base_url == "http://127.0.0.1:5000"


def test_translate_concurrency_default_smart(monkeypatch):
    monkeypatch.setattr(config, "TRANSLATE_BACKEND", "libre")
    monkeypatch.setattr(config, "TRANSLATE_CONCURRENCY", 0)
    assert config.translate_concurrency_default() == config.LIBRE_TRANSLATE_CONCURRENCY

    monkeypatch.setattr(config, "TRANSLATE_BACKEND", "google")
    monkeypatch.setattr(config, "TRANSLATE_CONCURRENCY", 0)
    assert config.translate_concurrency_default() == config.DEFAULT_TRANSLATE_CONCURRENCY

    # env explicito gana al auto
    monkeypatch.setattr(config, "TRANSLATE_CONCURRENCY", 8)
    assert config.translate_concurrency_default() == 8


def test_effective_translate_concurrency_protection(monkeypatch):
    monkeypatch.setattr(config, "TRANSLATE_BACKEND", "google")
    # google siempre fuerza a 1, ignore el pedido
    assert config.effective_translate_concurrency(8) == 1
    assert config.effective_translate_concurrency(None) == 1

    monkeypatch.setattr(config, "TRANSLATE_BACKEND", "libre")
    monkeypatch.setattr(config, "TRANSLATE_MAX_CONCURRENCY", 16)
    assert config.effective_translate_concurrency(None) == config.LIBRE_TRANSLATE_CONCURRENCY
    assert config.effective_translate_concurrency(8) == 8
    # tope maximo
    assert config.effective_translate_concurrency(99) == 16
    assert config.effective_translate_concurrency(0) == config.LIBRE_TRANSLATE_CONCURRENCY


@pytest.mark.asyncio
async def test_translate_chapters_parallel(tmp_path):
    """Con concurrency>1 todos los capitulos se traducen y el progreso es correcto."""
    chapters = [
        Chapter(num=i, title=f"Ch {i}", url=f"u{i}", paragraphs=["Hello world"])
        for i in range(1, 11)
    ]
    translated_dir = tmp_path / "translated"
    received: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request.url.params.get("q", ""))
        return echo_handler(request)

    progress: list[tuple[int, int]] = []

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
                concurrency=4,
                on_progress=lambda d, t: progress.append((d, t)),
            )
        finally:
            await translator.aclose()

    assert len(received) == 10
    assert manifest.chapters_translated == 10
    assert manifest.translated is True
    # cada capitulo quedo en disco
    assert translated_dir.joinpath(chapter_filename(5)).exists()
    # progreso llego a 10/10
    assert progress[-1] == (10, 10)
    assert len(progress) == 10


@pytest.mark.asyncio
async def test_translate_chapters_concurrency_1_sequential(tmp_path):
    """concurrency=1 mantiene el comportamiento secuencial (retrocompatible)."""
    chapters = [
        Chapter(num=i, title=f"Ch {i}", url=f"u{i}", paragraphs=["Hello world"])
        for i in range(1, 4)
    ]
    with respx.mock() as router:
        router.get(GTX_ENDPOINT).mock(side_effect=echo_handler)
        translator = make_translator()
        manifest = make_manifest(tmp_path)
        try:
            await translate_chapters(
                translator=translator,
                chapters=chapters,
                slug_dir=tmp_path,
                manifest=manifest,
                concurrency=1,
            )
        finally:
            await translator.aclose()
    assert manifest.chapters_translated == 3


@pytest.mark.asyncio
async def test_ollama_sends_official_prompt_and_parses():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["json"] = json.loads(request.content)
        return ollama_response("Hola mundo")

    with respx.mock() as router:
        router.post(OLLAMA_CHAT).mock(side_effect=handler)
        translator = make_ollama()
        try:
            assert await translator.translate_text("Hello world", target="es") == "Hola mundo"
        finally:
            await translator.aclose()

    body = captured["json"]
    assert body["model"] == config.OLLAMA_MODEL
    assert body["stream"] is False
    assert body["keep_alive"] == config.OLLAMA_KEEP_ALIVE
    assert body["options"] == {"temperature": 0}
    prompt = body["messages"][0]["content"]
    assert body["messages"][0]["role"] == "user"
    assert prompt.startswith("You are a professional English (en) to Spanish (es) translator.")
    assert "Produce only the Spanish translation, without any additional" in prompt
    # dos lineas en blanco antes del texto a traducir
    assert prompt.endswith("into Spanish:\n\n\nHello world")


@pytest.mark.asyncio
async def test_ollama_empty_text_does_not_call():
    with respx.mock(assert_all_called=False) as router:
        route = router.post(OLLAMA_CHAT).mock(return_value=ollama_response("x"))
        translator = make_ollama()
        try:
            assert await translator.translate_text("   ", target="es") == "   "
        finally:
            await translator.aclose()
        assert route.call_count == 0


@pytest.mark.asyncio
async def test_ollama_auto_source_uses_configured_lang():
    captured: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(json.loads(request.content)["messages"][0]["content"])
        return ollama_response("ok")

    with respx.mock() as router:
        router.post(OLLAMA_CHAT).mock(side_effect=handler)
        translator = make_ollama(source_lang="en")
        try:
            await translator.translate_text("Hello", source="auto", target="es")
            await translator.translate_text("Bonjour", source="fr", target="es")
        finally:
            await translator.aclose()

    assert "English (en) to Spanish (es)" in captured[0]
    assert "French (fr) to Spanish (es)" in captured[1]


@pytest.mark.asyncio
async def test_ollama_retries_network_error():
    with respx.mock() as router:
        route = router.post(OLLAMA_CHAT)
        route.side_effect = [
            httpx.ConnectError("boom"),
            ollama_response("ok"),
        ]
        translator = make_ollama()
        try:
            assert await translator.translate_text("Hello", target="es") == "ok"
            assert route.call_count == 2
        finally:
            await translator.aclose()


@pytest.mark.asyncio
async def test_ollama_reintenta_con_preserve_breaks_si_no_cuadra():
    payloads: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content)["messages"][0]["content"])
        if len(payloads) == 1:
            # 3 parrafos de entrada pero 1 sola linea de salida
            return ollama_response("Una sola linea")
        return ollama_response("Uno\nDos\nTres")

    with respx.mock() as router:
        router.post(OLLAMA_CHAT).mock(side_effect=handler)
        translator = make_ollama()
        try:
            result = await translator.translate_text("One\nTwo\nThree", target="es")
        finally:
            await translator.aclose()

    assert result == "Uno\nDos\nTres"
    assert len(payloads) == 2
    assert "Preserve the paragraph breaks" not in payloads[0]
    assert "Preserve the paragraph breaks" in payloads[1]


@pytest.mark.asyncio
async def test_ollama_fallback_linea_a_linea_evita_vacios(caplog):
    def handler(request: httpx.Request) -> httpx.Response:
        content = json.loads(request.content)["messages"][0]["content"]
        source_text = content.split("\n\n\n", 1)[1]
        if "\n" in source_text:
            # chunk multilinea desalineado: una sola linea en la respuesta
            return ollama_response("Una sola linea")
        return ollama_response(f"ES:{source_text.strip()}")

    with respx.mock() as router:
        route = router.post(OLLAMA_CHAT).mock(side_effect=handler)
        translator = make_ollama()
        with caplog.at_level(logging.WARNING):
            try:
                result = await translator.translate_text("One\nTwo\nThree", target="es")
            finally:
                await translator.aclose()

    assert result == "ES:One\nES:Two\nES:Three"
    # 2 intentos del chunk completo + 3 lineas individuales
    assert route.call_count == 5
    assert "fallback linea a linea" in caplog.text


@pytest.mark.asyncio
async def test_ollama_http_404_falla_rapido():
    with respx.mock() as router:
        route = router.post(OLLAMA_CHAT).mock(
            return_value=httpx.Response(404, text="model not found")
        )
        translator = make_ollama()
        try:
            with pytest.raises(TranslateError) as excinfo:
                await translator.translate_text("Hello", target="es")
        finally:
            await translator.aclose()
    assert excinfo.value.status_code == 404
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_ollama_translate_chapters_pasa_source_del_manifest(tmp_path):
    prompts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        prompts.append(json.loads(request.content)["messages"][0]["content"])
        return ollama_response("Hola")

    chapters = [Chapter(num=1, title="Ch 1", url="u1", paragraphs=["Hello"])]
    with respx.mock() as router:
        router.post(OLLAMA_CHAT).mock(side_effect=handler)
        translator = make_ollama()
        manifest = make_manifest(tmp_path)
        try:
            await translate_chapters(
                translator=translator,
                chapters=chapters,
                slug_dir=tmp_path,
                manifest=manifest,
                target="es",
                source="fr",
            )
        finally:
            await translator.aclose()

    assert "French (fr) to Spanish (es)" in prompts[0]


def test_build_default_translator_ollama(monkeypatch):
    monkeypatch.setattr(config, "TRANSLATE_BACKEND", "ollama")
    monkeypatch.setattr(config, "OLLAMA_MODEL", "translategemma:4b")
    translator = build_default_translator()
    assert isinstance(translator, OllamaTranslator)
    assert translator.model == "translategemma:4b"


def test_effective_translate_concurrency_ollama_forces_one(monkeypatch):
    monkeypatch.setattr(config, "TRANSLATE_BACKEND", "ollama")
    assert config.effective_translate_concurrency(8) == 1
    assert config.translate_concurrency_default() == 1


def test_translate_max_words_per_chunk_by_backend(monkeypatch):
    monkeypatch.setattr(config, "TRANSLATE_BACKEND", "ollama")
    monkeypatch.setattr(config, "OLLAMA_MAX_WORDS_PER_CHUNK", 222)
    assert config.translate_max_words_per_chunk() == 222

    monkeypatch.setattr(config, "TRANSLATE_BACKEND", "google")
    assert config.translate_max_words_per_chunk() == DEFAULT_MAX_WORDS_PER_CHUNK


@pytest.mark.asyncio
async def test_reassembly_ignora_lineas_en_blanco_del_llm():
    """Un LLM puede intercalar lineas en blanco; no deben desplazar el mapeo 1:1."""

    class BlankLinesTranslator:
        async def translate_text(self, text, *, source="auto", target="es"):
            return "\n\n".join("X" + line for line in text.split("\n"))

    paragraphs = ["One", "Two", "Three"]
    result = await translate_paragraphs(paragraphs, BlankLinesTranslator())
    assert result == ["XOne", "XTwo", "XThree"]

