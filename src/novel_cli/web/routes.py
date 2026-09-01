"""Endpoints REST de la web: jobs, novelas y descarga de EPUBs."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from novel_cli.core import config
from novel_cli.core.models.state import Manifest
from novel_cli.web.jobs import JobManager


class JobRequest(BaseModel):
    url: str
    output: str | None = None
    volume_size: int | None = 50
    translate: bool = False
    resume: bool = True
    force: bool = False
    all: bool = False
    translate_pending: bool = False
    translate_concurrency: int | None = None
    playwright: bool = False
    concurrency: int = config.DEFAULT_CONCURRENCY


def _valid_url(url: str) -> bool:
    from urllib.parse import urlsplit

    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def build_router(manager: JobManager) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/jobs")
    async def list_jobs() -> list[dict[str, object]]:
        return [
            {
                "id": job.id,
                "url": job.url,
                "state": job.state,
                "slug": job.slug,
                "error": job.error,
            }
            for job in manager.list()
        ]

    @router.post("/jobs")
    async def create_job(req: JobRequest) -> dict[str, str]:
        if not _valid_url(req.url):
            raise HTTPException(status_code=400, detail="URL invalida: debe ser http(s)")
        if req.volume_size is not None and req.volume_size not in (50, 100):
            raise HTTPException(status_code=400, detail="volume_size solo acepta 50 o 100")
        if req.concurrency < 1:
            raise HTTPException(status_code=400, detail="concurrency debe ser >= 1")
        if req.translate_concurrency is not None and req.translate_concurrency < 1:
            raise HTTPException(
                status_code=400, detail="translate_concurrency debe ser >= 1"
            )
        output_dir = (
            Path(req.output).expanduser() if req.output else None
        )
        job = manager.create(
            url=req.url,
            output_dir=output_dir,
            options=req.model_dump(),
        )
        return {"job_id": job.id}

    @router.get("/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, object]:
        job = manager.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job no encontrado")
        return {
            "id": job.id,
            "url": job.url,
            "state": job.state,
            "error": job.error,
            "slug": job.slug,
            "result": job.result,
            "events": job.events,
        }

    @router.post("/jobs/{job_id}/cancel")
    async def cancel_job(job_id: str) -> dict[str, bool]:
        cancelled = await manager.cancel(job_id)
        if not cancelled:
            raise HTTPException(status_code=404, detail="job no cancelable/no encontrado")
        return {"cancelled": True}

    @router.get("/novels")
    async def list_novels() -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
        output_dir = manager.default_output_dir
        if not output_dir.exists():
            return out
        for slug_dir in sorted(output_dir.iterdir()):
            if not slug_dir.is_dir():
                continue
            manifest = Manifest.load(slug_dir)
            if manifest is None:
                continue
            out.append(_novel_payload(slug_dir, manifest))
        return out

    @router.get("/novels/{slug}")
    async def get_novel(slug: str) -> dict[str, object]:
        output_dir = manager.default_output_dir
        slug_dir = output_dir / slug
        manifest = Manifest.load(slug_dir)
        if manifest is None:
            raise HTTPException(status_code=404, detail="novela no encontrada")
        return _novel_payload(slug_dir, manifest)

    @router.get("/novels/{slug}/epub/{filename}")
    async def download_epub(slug: str, filename: str) -> FileResponse:
        output_dir = manager.default_output_dir
        path = output_dir / slug / filename
        if not path.is_file() or not filename.endswith(".epub"):
            raise HTTPException(status_code=404, detail="EPUB no encontrado")
        return FileResponse(
            path, media_type="application/epub+zip", filename=filename
        )

    @router.get("/novels/{slug}/cover")
    async def get_cover(slug: str) -> FileResponse:
        output_dir = manager.default_output_dir
        slug_dir = output_dir / slug
        manifest = Manifest.load(slug_dir)
        if manifest is None or not manifest.cover_path:
            raise HTTPException(status_code=404, detail="portada no encontrada")
        path = slug_dir / manifest.cover_path
        if not path.is_file():
            raise HTTPException(status_code=404, detail="portada no encontrada")
        return FileResponse(path)

    @router.post("/novels/{slug}/sync")
    async def sync_novel(slug: str) -> dict[str, str]:
        output_dir = manager.default_output_dir
        slug_dir = output_dir / slug
        manifest = Manifest.load(slug_dir)
        if manifest is None:
            raise HTTPException(status_code=404, detail="novela no encontrada")
        if not manifest.source_url or not _valid_url(manifest.source_url):
            raise HTTPException(
                status_code=400, detail="la novela no tiene una source_url valida"
            )
        job = manager.create(
            url=manifest.source_url,
            output_dir=output_dir,
            options={
                "url": manifest.source_url,
                "volume_size": manifest.volume_size,
                "translate": manifest.translated,
                "resume": True,
                "force": False,
                "all": False,
                "translate_pending": False,
                "playwright": False,
                "concurrency": config.DEFAULT_CONCURRENCY,
            },
        )
        return {"job_id": job.id}

    return router


def _novel_payload(slug_dir: Path, manifest: Manifest) -> dict[str, object]:
    cover = None
    if manifest.cover_path:
        cover_path = slug_dir / manifest.cover_path
        if cover_path.is_file():
            cover = f"/api/novels/{manifest.slug}/cover"
    return {
        "slug": manifest.slug,
        "title": manifest.title,
        "author": manifest.author,
        "source_url": manifest.source_url,
        "chapters_total": manifest.chapters_total,
        "chapters_downloaded": manifest.chapters_downloaded,
        "chapters_translated": manifest.chapters_translated,
        "chapters_empty": manifest.chapters_empty,
        "chapters_empty_nums": manifest.chapters_empty_nums,
        "translated": manifest.translated,
        "volume_size": manifest.volume_size,
        "cover": cover,
        "epub_original": manifest.epub_original,
        "epub_translated": manifest.epub_translated,
        "created_at": manifest.created_at,
        "updated_at": manifest.updated_at,
    }
