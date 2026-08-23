"""Fetch con retry/backoff/pacer/cool-down (lecciones de Readest novelImport.ts).

HTTP primero (httpx async); Playwright solo como fallback JS con navegador
persistente (nada de launch() por llamada).
"""

from __future__ import annotations

import asyncio
import email.utils
from datetime import UTC, datetime

import httpx

from novel_cli.core import config

CHROME_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Upgrade-Insecure-Requests": "1",
}


class FetchError(Exception):
    """Error de red/HTTP tras agotar reintentos."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class FetchRateLimitedError(FetchError):
    """Rate-limit persistente (429/503) tras agotar el presupuesto."""


def is_transient(status: int) -> bool:
    """502/504/52x: fallos transitorios que merecen retry lineal."""
    return status in (502, 504) or 520 <= status < 530


def is_rate_limit(status: int) -> bool:
    return status in (429, 503)


def parse_retry_after(value: str | None) -> float | None:
    """Parsea Retry-After (segundos o fecha HTTP). None si no es valido."""
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt is None or dt.tzinfo is None:
        return None
    return max(0.0, (dt - datetime.now(UTC)).total_seconds())


class Pacer:
    """Garantiza un minimo entre inicios de requests (pacing agregado del pool)."""

    def __init__(self, min_interval_ms: int = config.CHAPTER_REQUEST_MIN_INTERVAL_MS):
        self.min_interval = min_interval_ms / 1000.0
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = asyncio.get_running_loop().time()
            wait = self.min_interval - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = asyncio.get_running_loop().time()


class CooldownGate:
    """Gate compartido del pool: un 429 de un worker frena a los demas."""

    def __init__(self, max_seconds: float = config.MAX_COOLDOWN_SECONDS):
        self.max_seconds = max_seconds
        self._until = 0.0
        self._lock = asyncio.Lock()

    async def trigger(self, seconds: float) -> None:
        capped = min(seconds, self.max_seconds)
        if capped <= 0:
            return
        async with self._lock:
            now = asyncio.get_running_loop().time()
            self._until = max(self._until, now + capped)

    async def wait(self) -> None:
        async with self._lock:
            remaining = self._until - asyncio.get_running_loop().time()
        if remaining > 0:
            await asyncio.sleep(remaining)


class HttpFetcher:
    """Fetcher HTTP con httpx async: headers Chrome, retry, pacer y cool-down."""

    def __init__(
        self,
        *,
        timeout: float = config.DEFAULT_HTTP_TIMEOUT_SECONDS,
        client: httpx.AsyncClient | None = None,
        pacer: Pacer | None = None,
        cooldown: CooldownGate | None = None,
        transient_retries: int = config.RETRY_TRANSIENT,
        transient_backoff: tuple[float, ...] = config.RETRY_TRANSIENT_BACKOFF,
        rate_limit_retries: int = config.RETRY_RATE_LIMIT,
        rate_backoff_base: float = config.RETRY_BACKOFF_BASE_SECONDS,
    ):
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers=dict(CHROME_HEADERS),
        )
        self.pacer = pacer or Pacer()
        self.cooldown = cooldown or CooldownGate()
        self.transient_retries = transient_retries
        self.transient_backoff = transient_backoff
        self.rate_limit_retries = rate_limit_retries
        self.rate_backoff_base = rate_backoff_base

    async def fetch_html(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        return (await self._request(url, headers=headers)).text

    async def fetch_bytes(self, url: str, *, headers: dict[str, str] | None = None) -> bytes:
        return (await self._request(url, headers=headers)).content

    async def _request(
        self, url: str, *, headers: dict[str, str] | None = None
    ) -> httpx.Response:
        for attempt in range(self.rate_limit_retries + 1):
            await self.cooldown.wait()
            await self.pacer.acquire()
            try:
                response = await self._client.get(url, headers=headers)
            except httpx.HTTPError as exc:
                if attempt < self.transient_retries:
                    await asyncio.sleep(self._backoff(attempt))
                    continue
                raise FetchError(f"network error fetching {url}: {exc}") from exc

            if response.status_code == 200:
                return response

            if is_rate_limit(response.status_code):
                delay = self._rate_delay(response, attempt)
                await self.cooldown.trigger(delay)
                if attempt < self.rate_limit_retries:
                    await asyncio.sleep(delay)
                    continue
                raise FetchRateLimitedError(
                    f"rate limited ({response.status_code}) fetching {url}",
                    status_code=response.status_code,
                )

            if is_transient(response.status_code):
                if attempt < self.transient_retries:
                    await asyncio.sleep(self._backoff(attempt))
                    continue
                raise FetchError(
                    f"transient HTTP {response.status_code} fetching {url}",
                    status_code=response.status_code,
                )

            raise FetchError(
                f"HTTP {response.status_code} fetching {url}",
                status_code=response.status_code,
            )

        raise FetchError(f"unreachable for {url}")

    def _backoff(self, attempt: int) -> float:
        if attempt < len(self.transient_backoff):
            return self.transient_backoff[attempt]
        return self.transient_backoff[-1]

    def _rate_delay(self, response: httpx.Response, attempt: int) -> float:
        retry_after = parse_retry_after(response.headers.get("retry-after"))
        if retry_after is not None:
            return min(retry_after, config.RETRY_AFTER_MAX_SECONDS)
        return min(
            self.rate_backoff_base * (2**attempt),
            config.RETRY_AFTER_MAX_SECONDS,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


class PlaywrightFetcher:
    """Fallback JS: un unico navegador persistente para toda la sesion."""

    def __init__(self, *, headless: bool = True):
        self.headless = headless
        self._playwright = None
        self._browser = None

    async def _ensure(self) -> None:
        if self._browser is None:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless
            )

    async def fetch_html(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        await self._ensure()
        page = await self._browser.new_page()
        try:
            await page.goto(url, wait_until="networkidle")
            return await page.content()
        finally:
            await page.close()

    async def fetch_bytes(self, url: str, *, headers: dict[str, str] | None = None) -> bytes:
        await self._ensure()
        page = await self._browser.new_page()
        try:
            response = await page.goto(url, wait_until="networkidle")
            body = await response.body()
            return bytes(body)
        finally:
            await page.close()

    async def aclose(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None


class FallbackFetcher:
    """HTTP primero; si falla, reenvia por Playwright. Con --playwright fuerza PW."""

    def __init__(
        self,
        http: HttpFetcher,
        playwright: PlaywrightFetcher | None,
        *,
        force_playwright: bool = False,
    ):
        self.http = http
        self.playwright = playwright
        self.force_playwright = force_playwright

    async def fetch_html(self, url: str, *, headers: dict[str, str] | None = None) -> str:
        if self.force_playwright:
            return await self._pw_fetch("fetch_html", url, headers=headers)
        try:
            return await self.http.fetch_html(url, headers=headers)
        except FetchError:
            return await self._pw_fetch("fetch_html", url, headers=headers)

    async def fetch_bytes(self, url: str, *, headers: dict[str, str] | None = None) -> bytes:
        if self.force_playwright:
            return await self._pw_fetch("fetch_bytes", url, headers=headers)
        try:
            return await self.http.fetch_bytes(url, headers=headers)
        except FetchError:
            return await self._pw_fetch("fetch_bytes", url, headers=headers)

    async def _pw_fetch(
        self, method: str, url: str, *, headers: dict[str, str] | None
    ) -> str | bytes:
        if self.playwright is None:
            raise FetchError(f"playwright fallback unavailable for {url}")
        result = await getattr(self.playwright, method)(url, headers=headers)
        assert isinstance(result, (str, bytes))
        return result

    async def aclose(self) -> None:
        await self.http.aclose()
        if self.playwright is not None:
            await self.playwright.aclose()


def get_fetcher(
    http: HttpFetcher,
    playwright: PlaywrightFetcher | None,
    *,
    force_playwright: bool = False,
) -> FallbackFetcher:
    """Ensambla el fetcher por defecto (HTTP-first con fallback Playwright)."""
    return FallbackFetcher(http, playwright, force_playwright=force_playwright)