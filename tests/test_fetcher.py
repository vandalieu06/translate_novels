"""Unit tests del fetcher con respx: retry/backoff/Retry-After/cool-down/fallback."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
import respx

from novel_cli.core.scraper.fetcher import (
    CooldownGate,
    FetchError,
    FetchRateLimitedError,
    HttpFetcher,
    Pacer,
    get_fetcher,
    is_rate_limit,
    is_transient,
    parse_retry_after,
)

URL = "https://example.com/chapter/1"


def make_fetcher(**kw) -> HttpFetcher:
    kw.setdefault("transient_backoff", (0.0, 0.0))
    kw.setdefault("rate_backoff_base", 0.0)
    kw.setdefault("pacer", Pacer(0))
    kw.setdefault("cooldown", CooldownGate())
    return HttpFetcher(**kw)


@pytest.mark.asyncio
async def test_fetch_html_ok():
    with respx.mock() as router:
        route = router.get(URL)
        route.mock(return_value=httpx.Response(200, text="<html>ok</html>"))
        fetcher = make_fetcher()
        try:
            assert await fetcher.fetch_html(URL) == "<html>ok</html>"
            assert route.call_count == 1
        finally:
            await fetcher.aclose()


@pytest.mark.asyncio
async def test_fetch_bytes_ok():
    with respx.mock() as router:
        router.get(URL).mock(
            return_value=httpx.Response(200, content=b"\x89PNG\x0d\x0a")
        )
        fetcher = make_fetcher()
        try:
            assert await fetcher.fetch_bytes(URL) == b"\x89PNG\x0d\x0a"
        finally:
            await fetcher.aclose()


@pytest.mark.asyncio
async def test_retry_429_then_ok_honors_retry_after():
    with respx.mock() as router:
        route = router.get(URL)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "0.05"}),
            httpx.Response(200, text="ok"),
        ]
        fetcher = make_fetcher()
        try:
            start = time.monotonic()
            html = await fetcher.fetch_html(URL)
            elapsed = time.monotonic() - start
            assert html == "ok"
            assert elapsed >= 0.05
            assert route.call_count == 2
        finally:
            await fetcher.aclose()


@pytest.mark.asyncio
async def test_retry_429_persistent_raises():
    with respx.mock() as router:
        route = router.get(URL)
        route.side_effect = [
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(429, headers={"retry-after": "0"}),
            httpx.Response(429, headers={"retry-after": "0"}),
        ]
        fetcher = make_fetcher(rate_limit_retries=3)
        try:
            with pytest.raises(FetchRateLimitedError) as exc:
                await fetcher.fetch_html(URL)
            assert exc.value.status_code == 429
            assert route.call_count == 4
        finally:
            await fetcher.aclose()


@pytest.mark.asyncio
async def test_retry_transient_502_then_ok():
    with respx.mock() as router:
        route = router.get(URL)
        route.side_effect = [httpx.Response(502), httpx.Response(200, text="ok")]
        fetcher = make_fetcher(transient_retries=2)
        try:
            assert await fetcher.fetch_html(URL) == "ok"
            assert route.call_count == 2
        finally:
            await fetcher.aclose()


@pytest.mark.asyncio
async def test_retry_transient_504_persistent_raises():
    with respx.mock() as router:
        route = router.get(URL)
        route.side_effect = [httpx.Response(504)] * 3
        fetcher = make_fetcher(transient_retries=2)
        try:
            with pytest.raises(FetchError) as exc:
                await fetcher.fetch_html(URL)
            assert exc.value.status_code == 504
            assert route.call_count == 3
        finally:
            await fetcher.aclose()


@pytest.mark.asyncio
async def test_retry_transient_timeout_then_ok():
    with respx.mock() as router:
        route = router.get(URL)
        route.side_effect = [httpx.ConnectTimeout("boom"), httpx.Response(200, text="ok")]
        fetcher = make_fetcher(transient_retries=2)
        try:
            assert await fetcher.fetch_html(URL) == "ok"
            assert route.call_count == 2
        finally:
            await fetcher.aclose()


@pytest.mark.asyncio
async def test_no_retry_on_404():
    with respx.mock() as router:
        route = router.get(URL)
        route.mock(return_value=httpx.Response(404))
        fetcher = make_fetcher()
        try:
            with pytest.raises(FetchError) as exc:
                await fetcher.fetch_html(URL)
            assert exc.value.status_code == 404
            assert route.call_count == 1
        finally:
            await fetcher.aclose()


@pytest.mark.asyncio
async def test_cooldown_delays_other_worker():
    url_a = "https://example.com/a"
    url_b = "https://example.com/b"
    with respx.mock() as router:
        router.get(url_a).side_effect = [
            httpx.Response(429, headers={"retry-after": "0.10"}),
            httpx.Response(200, text="a"),
        ]
        router.get(url_b).mock(return_value=httpx.Response(200, text="b"))

        cooldown = CooldownGate()
        fetcher_a = make_fetcher(cooldown=cooldown)
        fetcher_b = make_fetcher(cooldown=cooldown)
        try:
            start = time.monotonic()

            async def worker_a():
                return await fetcher_a.fetch_html(url_a)

            async def worker_b():
                await asyncio.sleep(0.01)
                return await fetcher_b.fetch_html(url_b)

            result_a, result_b = await asyncio.gather(worker_a(), worker_b())
            elapsed = time.monotonic() - start
            assert (result_a, result_b) == ("a", "b")
            assert elapsed >= 0.10
        finally:
            await fetcher_a.aclose()
            await fetcher_b.aclose()


class FakePlaywright:
    def __init__(self):
        self.html_calls: list[str] = []
        self.byte_calls: list[str] = []

    async def fetch_html(self, url: str, *, headers: dict | None = None) -> str:
        self.html_calls.append(url)
        return "<html>pw</html>"

    async def fetch_bytes(self, url: str, *, headers: dict | None = None) -> bytes:
        self.byte_calls.append(url)
        return b"pw"

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_fallback_to_playwright_on_http_error():
    with respx.mock() as router:
        router.get(URL).mock(return_value=httpx.Response(500))
        pw = FakePlaywright()
        http = make_fetcher()
        fetcher = get_fetcher(http, pw)
        try:
            assert await fetcher.fetch_html(URL) == "<html>pw</html>"
            assert pw.html_calls == [URL]
        finally:
            await fetcher.aclose()


@pytest.mark.asyncio
async def test_fallback_bytes():
    with respx.mock() as router:
        router.get(URL).mock(return_value=httpx.Response(503))
        pw = FakePlaywright()
        http = make_fetcher()
        fetcher = get_fetcher(http, pw)
        try:
            assert await fetcher.fetch_bytes(URL) == b"pw"
            assert pw.byte_calls == [URL]
        finally:
            await fetcher.aclose()


@pytest.mark.asyncio
async def test_force_playwright_skips_http():
    pw = FakePlaywright()
    http = make_fetcher()
    fetcher = get_fetcher(http, pw, force_playwright=True)
    try:
        assert await fetcher.fetch_html(URL) == "<html>pw</html>"
        assert pw.html_calls == [URL]
    finally:
        await fetcher.aclose()


@pytest.mark.asyncio
async def test_playwright_required_error_when_none():
    with respx.mock() as router:
        router.get(URL).mock(return_value=httpx.Response(500))
        http = make_fetcher()
        fetcher = get_fetcher(http, None)
        try:
            with pytest.raises(FetchError):
                await fetcher.fetch_html(URL)
        finally:
            await fetcher.aclose()


@pytest.mark.asyncio
async def test_fetch_html_decodes_brotli():
    import brotli

    body = b"<html><body><h1>hola</h1><p>mundo</p></body></html>"
    with respx.mock() as router:
        router.get(URL).mock(
            return_value=httpx.Response(
                200,
                content=brotli.compress(body),
                headers={"content-encoding": "br"},
            )
        )
        fetcher = make_fetcher()
        try:
            html = await fetcher.fetch_html(URL)
            assert "<h1>hola</h1>" in html
            assert "<p>mundo</p>" in html
        finally:
            await fetcher.aclose()


def test_parse_retry_after():
    assert parse_retry_after("5") == 5.0
    assert parse_retry_after("0.5") == 0.5
    assert parse_retry_after(None) is None
    assert parse_retry_after("bogus") is None
    assert parse_retry_after("") is None


def test_status_classification():
    assert is_rate_limit(429)
    assert is_rate_limit(503)
    assert not is_rate_limit(200)
    assert is_transient(502)
    assert is_transient(504)
    assert is_transient(522)
    assert not is_transient(200)