"""Registry: mapea dominio → SiteAdapter, con GenericAdapter como fallback."""

from __future__ import annotations

from urllib.parse import urlparse

from novel_cli.core.scraper.base import SiteAdapter
from novel_cli.core.scraper.sites.generic import GenericAdapter
from novel_cli.core.scraper.sites.novelfire import NovelfireAdapter

_ADAPTER_CLASSES: dict[str, type[SiteAdapter]] = {
    "novelfire.net": NovelfireAdapter,
    "novelphoenix.com": NovelfireAdapter,  # mismo engine que NovelFire
}


def get_adapter(url: str) -> SiteAdapter:
    """Resuelve el adaptador por dominio; GenericAdapter si no hay match."""
    host = urlparse(url).hostname or ""
    adapter_cls = None
    if host in _ADAPTER_CLASSES:
        adapter_cls = _ADAPTER_CLASSES[host]
    else:
        for domain, cls in _ADAPTER_CLASSES.items():
            if host.endswith(domain):
                adapter_cls = cls
                break
    return adapter_cls() if adapter_cls is not None else GenericAdapter()