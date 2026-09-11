"""Cache en disco del TOC de una novela (``output/<slug>/.toc.json``)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from novel_cli.core.models.novel import Chapter


class CachedChapter(BaseModel):
    """Capitulo serializado en la cache del TOC."""

    model_config = ConfigDict(extra="ignore")

    num: int
    title: str = ""
    url: str


class TocCache(BaseModel):
    """Indice de capitulos cacheado para no re-scrapear el listado en cada run."""

    model_config = ConfigDict(extra="ignore")

    version: int = 1
    source_url: str
    fetched_at: str
    listing_pages: list[str] = []
    chapters: list[CachedChapter] = []

    def age_seconds(self) -> float:
        """Segundos desde ``fetched_at`` (inf si el timestamp no es valido)."""
        try:
            fetched = datetime.fromisoformat(self.fetched_at)
        except ValueError:
            return float("inf")
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=UTC)
        return max(0.0, (datetime.now(UTC) - fetched).total_seconds())

    def max_num(self) -> int:
        return max((chapter.num for chapter in self.chapters), default=0)

    def touch(self) -> None:
        self.fetched_at = datetime.now(UTC).isoformat()

    def save(self, slug_dir: str | Path) -> None:
        path = Path(slug_dir) / ".toc.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, slug_dir: str | Path) -> TocCache | None:
        path = Path(slug_dir) / ".toc.json"
        if not path.exists():
            return None
        try:
            return cls.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValueError):
            return None


def make_cache(
    source_url: str, chapters: list[Chapter], listing_pages: list[str]
) -> TocCache:
    """Construye una ``TocCache`` nueva con timestamp actual."""
    return TocCache(
        source_url=source_url,
        fetched_at=datetime.now(UTC).isoformat(),
        listing_pages=listing_pages,
        chapters=[
            CachedChapter(num=chapter.num, title=chapter.title, url=chapter.url)
            for chapter in chapters
        ],
    )
