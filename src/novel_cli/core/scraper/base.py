"""Protocolos de Fetcher y SiteAdapter (core puro, sin dependencias de red concretas)."""

from __future__ import annotations

from typing import Protocol

from novel_cli.core.models.novel import SiteMetadata


class Fetcher(Protocol):
    """Abstraccion de fetch: httpx-first con Playwright como fallback."""

    async def fetch_html(self, url: str, *, headers: dict[str, str] | None = None) -> str: ...

    async def fetch_bytes(self, url: str, *, headers: dict[str, str] | None = None) -> bytes: ...

    async def aclose(self) -> None: ...


class SiteAdapter(Protocol):
    """Adaptador de sitio: descubre listados, parsea TOC y capitulos."""

    name: str

    def tocs(self, novel_url: str) -> list[str]: ...

    def parse_toc(self, html: str, base_url: str) -> SiteMetadata: ...

    def parse_chapter(self, html: str, chapter_url: str) -> list[str]: ...

    def next_page(self, html: str, base_url: str) -> str | None: ...