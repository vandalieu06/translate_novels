"""Endpoints REST de la web: jobs, novelas y descarga de EPUBs."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from novel_cli.core import config
from novel_cli.core.models.state import Manifest
from novel_cli.core.services.pipeline import PipelineError, rebuild_volumes
from novel_cli.web.jobs import JobManager


class JobRequest(BaseModel):
    url: str
    output: str | None = None
    volume_size: int | None = 50
    translate: bool = False
    target_language: str | None = None
    resume: bool = True
    force: bool = False
    all: bool = False
    translate_pending: bool = False
    translate_concurrency: int | None = None
    playwright: bool = False
    concurrency: int = config.DEFAULT_CONCURRENCY
    refresh_toc: bool = False


class RetranslateRequest(BaseModel):
    target_language: str | None = None


class VolumeSizeRequest(BaseModel):
    volume_size: int | None = None


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
        if req.volume_size is not None and req.volume_size not in (50, 100, 150, 200):
            raise HTTPException(
                status_code=400, detail="volume_size solo acepta 50, 100, 150 o 200"
            )
        if req.concurrency < 1:
            raise HTTPException(status_code=400, detail="concurrency debe ser >= 1")
        if req.translate_concurrency is not None and req.translate_concurrency < 1:
            raise HTTPException(
                status_code=400, detail="translate_concurrency debe ser >= 1"
            )
        if (
            req.translate
            and req.target_language is not None
            and not config.is_valid_translate_target(req.target_language)
        ):
            raise HTTPException(
                status_code=400, detail="target_language no soportado"
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

    @router.post("/upload")
    async def upload_pdf(
        file: UploadFile = File(...),
        source_language: str = Form("es"),
        translate: bool = Form(False),
        target_language: str | None = Form(None),
        volume_size: int | None = Form(None),
    ) -> dict[str, str]:
        """Sube un PDF y lo convierte a EPUB (con traduccion opcional)."""
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(
                status_code=400, detail="el archivo debe tener extension .pdf"
            )
        if source_language not in config.SOURCE_LANGUAGES:
            raise HTTPException(status_code=400, detail="source_language no soportado")
        if (
            translate
            and target_language is not None
            and not config.is_valid_translate_target(target_language)
        ):
            raise HTTPException(
                status_code=400, detail="target_language no soportado"
            )
        if volume_size is not None and volume_size not in (50, 100, 150, 200):
            raise HTTPException(
                status_code=400, detail="volume_size solo acepta 50, 100, 150 o 200"
            )
        data = await file.read()
        if len(data) > config.upload_max_bytes():
            raise HTTPException(
                status_code=400,
                detail=f"el PDF supera el maximo de {config.UPLOAD_MAX_MB} MB",
            )
        job = manager.create_pdf(
            filename=file.filename,
            data=data,
            output_dir=None,
            options={
                "operation": "pdf",
                "source_language": source_language,
                "translate": translate,
                "target_language": target_language,
                "volume_size": volume_size,
            },
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

    @router.post("/novels/{slug}/retranslate")
    async def retranslate_novel(
        slug: str, req: RetranslateRequest | None = None
    ) -> dict[str, str]:
        output_dir = manager.default_output_dir
        slug_dir = output_dir / slug
        manifest = Manifest.load(slug_dir)
        if manifest is None:
            raise HTTPException(status_code=404, detail="novela no encontrada")
        requested = req.target_language if req else None
        current = manifest.translated_language or config.translate_target_default()
        target = requested or current
        if not config.is_valid_translate_target(target):
            raise HTTPException(status_code=400, detail="target_language no soportado")
        if manifest.source_pdf:
            job = manager.create(
                url=manifest.title,
                output_dir=output_dir,
                options={
                    "operation": "pdf-retranslate",
                    "slug": manifest.slug,
                    "target_language": target,
                },
            )
            return {"job_id": job.id}
        if not manifest.source_url or not _valid_url(manifest.source_url):
            raise HTTPException(
                status_code=400, detail="la novela no tiene una source_url valida"
            )
        force = requested is not None and target != current
        job = manager.create(
            url=manifest.source_url,
            output_dir=output_dir,
            options={
                "url": manifest.source_url,
                "volume_size": manifest.volume_size,
                "translate": True,
                "resume": True,
                "force": force,
                "all": False,
                "translate_pending": True,
                "playwright": False,
                "concurrency": config.DEFAULT_CONCURRENCY,
                "target_language": target,
                "operation": "retranslate",
            },
        )
        return {"job_id": job.id}

    @router.post("/novels/{slug}/volume-size")
    async def change_volume_size(
        slug: str, req: VolumeSizeRequest
    ) -> dict[str, object]:
        output_dir = manager.default_output_dir
        slug_dir = output_dir / slug
        if req.volume_size is not None and req.volume_size < 1:
            raise HTTPException(
                status_code=400, detail="volume_size debe ser >= 1"
            )
        try:
            manifest = rebuild_volumes(slug_dir, req.volume_size)
        except PipelineError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "ok": True,
            "volume_size": manifest.volume_size,
            "epub_original": manifest.epub_original,
            "epub_translated": manifest.epub_translated,
        }

    @router.post("/novels/{slug}/rebuild")
    async def rebuild_novel(slug: str) -> dict[str, object]:
        output_dir = manager.default_output_dir
        slug_dir = output_dir / slug
        manifest = Manifest.load(slug_dir)
        if manifest is None:
            raise HTTPException(status_code=404, detail="novela no encontrada")
        try:
            manifest = rebuild_volumes(slug_dir, manifest.volume_size)
        except PipelineError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "ok": True,
            "volume_size": manifest.volume_size,
            "epub_original": manifest.epub_original,
            "epub_translated": manifest.epub_translated,
        }

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
                "target_language": manifest.translated_language,
                "operation": "sync",
                "peek_toc": True,
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
        "source_pdf": manifest.source_pdf,
        "chapters_total": manifest.chapters_total,
        "chapters_downloaded": manifest.chapters_downloaded,
        "chapters_translated": manifest.chapters_translated,
        "chapters_empty": manifest.chapters_empty,
        "chapters_empty_nums": manifest.chapters_empty_nums,
        "translated": manifest.translated,
        "translated_language": manifest.translated_language,
        "volume_size": manifest.volume_size,
        "cover": cover,
        "epub_original": manifest.epub_original,
        "epub_translated": manifest.epub_translated,
        "created_at": manifest.created_at,
        "updated_at": manifest.updated_at,
    }
