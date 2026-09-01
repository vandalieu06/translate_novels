"""Estado en disco: Manifest (pydantic) con load/save JSON."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class Manifest(BaseModel):
    """Indice/cache del estado de una novela (output/<slug>/.manifest.json)."""

    model_config = ConfigDict(extra="ignore")

    schema_version: int = 1
    slug: str
    title: str
    author: str | None = None
    source_url: str = ""
    language_code: str = "auto"
    cover_path: str | None = None
    chapters_total: int = 0
    chapters_downloaded: int = 0
    chapters_translated: int = 0
    chapters_empty: int = 0
    chapters_empty_nums: list[int] = []
    volume_size: int | None = None
    translated: bool = False
    epub_original: list[str] = []
    epub_translated: list[str] = []
    created_at: str | None = None
    updated_at: str | None = None

    def touch(self) -> None:
        """Actualiza timestamps (created_at solo la primera vez)."""
        now = datetime.now(UTC).isoformat()
        if self.created_at is None:
            self.created_at = now
        self.updated_at = now

    def save(self, slug_dir: str | Path) -> None:
        """Escribe .manifest.json en el directorio de la novela."""
        path = Path(slug_dir) / ".manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.touch()
        path.write_text(self.model_dump_json(indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, slug_dir: str | Path) -> Manifest | None:
        """Lee .manifest.json; None si no existe o es invalido."""
        path = Path(slug_dir) / ".manifest.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return cls.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            return None