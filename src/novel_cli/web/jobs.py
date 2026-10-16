"""Gestion de jobs en background para la web (un pipeline por ejecucion).

Cada job ejecuta ``run_pipeline`` como una coroutine dentro del event loop de
Uvicorn. Los callbacks del pipeline publican eventos que se reenvian a los
clientes WebSocket suscritos.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from novel_cli.core import config
from novel_cli.core.models.state import Manifest
from novel_cli.core.scraper.fetcher import (
    CooldownGate,
    HttpFetcher,
    Pacer,
    PlaywrightFetcher,
    get_fetcher,
)
from novel_cli.core.services.pdf_import import retranslate_pdf, run_pdf_pipeline
from novel_cli.core.services.pipeline import run_pipeline
from novel_cli.core.services.translate import build_default_translator
from novel_cli.logging_setup import JOB_ID
from novel_cli.notifications import build_default_notifier
from novel_cli.run_history import RunRecord, append_run, record_from_manifest

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]
EventCallback = Callable[[dict[str, Any]], None]

JOB_PENDING = "pending"
JOB_RUNNING = "running"
JOB_DONE = "done"
JOB_ERROR = "error"
JOB_CANCELLED = "cancelled"


@dataclass
class Job:
    """Un job en ejecucion/ejecutado con su buffer de eventos."""

    id: str
    url: str
    output_dir: Path
    state: str = JOB_PENDING
    error: str | None = None
    slug: str | None = None
    result: dict[str, Any] | None = None
    task: asyncio.Task[Any] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    _listeners: set[EventCallback] = field(default_factory=set, repr=False)

    def subscribe(self, cb: EventCallback) -> Callable[[], None]:
        self._listeners.add(cb)

        def unsubscribe() -> None:
            self._listeners.discard(cb)

        return unsubscribe

    def emit(self, event: dict[str, Any]) -> None:
        self.events.append(event)
        for listener in list(self._listeners):
            listener(event)

    def status(self, phase: str, message: str) -> None:
        self.emit({"type": "status", "phase": phase, "message": message})

    def progress(self, phase: str, done: int, total: int) -> None:
        self.emit(
            {"type": "progress", "phase": phase, "done": done, "total": total}
        )


class JobManager:
    """Registro en memoria de jobs (un job activo a la vez)."""

    def __init__(self, default_output_dir: Path):
        self.default_output_dir = default_output_dir
        self._jobs: dict[str, Job] = {}

    def list(self) -> list[Job]:
        return [self._jobs[key] for key in sorted(self._jobs, reverse=True)]

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def create(self, *, url: str, output_dir: Path | None, options: dict[str, Any]) -> Job:
        job = Job(
            id=uuid.uuid4().hex[:12],
            url=url,
            output_dir=output_dir or self.default_output_dir,
        )
        self._jobs[job.id] = job
        task = asyncio.create_task(self._run(job, options))
        job.task = task
        return job

    def create_pdf(
        self,
        *,
        filename: str,
        data: bytes,
        output_dir: Path | None,
        options: dict[str, Any],
    ) -> Job:
        """Crea un job de PDF: guarda el archivo en staging y lo procesa."""
        job_id = uuid.uuid4().hex[:12]
        staging = (output_dir or self.default_output_dir) / ".uploads" / job_id
        staging.mkdir(parents=True, exist_ok=True)
        pdf_path = staging / "source.pdf"
        pdf_path.write_bytes(data)
        job = Job(
            id=job_id,
            url=filename,
            output_dir=output_dir or self.default_output_dir,
        )
        self._jobs[job.id] = job
        task = asyncio.create_task(
            self._run(job, {**options, "pdf_path": str(pdf_path)})
        )
        job.task = task
        return job

    async def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.task is None or job.task.done():
            return False
        job.task.cancel()
        return True

    def _record(
        self,
        job: Job,
        operation: str,
        status: str,
        started: float,
        *,
        manifest: Manifest | None = None,
        error: str | None = None,
    ) -> None:
        """Anexa el resultado del job al historial (no debe romper el job)."""
        elapsed = time.monotonic() - started
        try:
            if manifest is not None:
                record = record_from_manifest(
                    manifest,
                    operation=operation,
                    status=status,
                    duration=elapsed,
                    job_id=job.id,
                    url=job.url,
                    error=error,
                )
            else:
                record = RunRecord(
                    operation=operation,
                    status=status,
                    job_id=job.id,
                    url=job.url,
                    duration_s=round(elapsed, 2),
                    error=error,
                )
            append_run(job.output_dir, record)
        except Exception:  # noqa: BLE001 - el historial no debe romper el job
            logger.exception("no se pudo escribir el historial del job %s", job.id)

    async def _run(self, job: Job, options: dict[str, Any]) -> None:
        operation = str(options.get("operation", "download"))
        if operation == "pdf":
            await self._run_pdf_import(job, options)
            return
        if operation == "pdf-retranslate":
            await self._run_pdf_retranslate(job, options)
            return
        await self._run_web(job, options, operation)

    async def _run_web(self, job: Job, options: dict[str, Any], operation: str) -> None:
        token = JOB_ID.set(job.id)
        started = time.monotonic()
        logger.info("job %s (%s) iniciado: %s", job.id, operation, job.url)
        job.state = JOB_RUNNING
        job.status("init", "Preparando descarga")
        http = HttpFetcher(pacer=Pacer(), cooldown=CooldownGate())
        playwright = PlaywrightFetcher()
        fetcher = get_fetcher(
            http, playwright, force_playwright=bool(options.get("playwright"))
        )
        translator = (
            build_default_translator()
            if (options.get("translate") or options.get("translate_pending"))
            else None
        )
        notifier = build_default_notifier()
        translate_concurrency = options.get("translate_concurrency")
        if translate_concurrency is None:
            translate_concurrency = config.translate_concurrency_default()
        try:
            manifest = await run_pipeline(
                url=job.url,
                output_dir=job.output_dir,
                volume_size=options.get("volume_size"),
                translate=bool(options.get("translate")),
                resume=bool(options.get("resume", True)),
                force=bool(options.get("force")),
                concurrency=int(options.get("concurrency", 4)),
                download_all=bool(options.get("all")),
                translate_pending=bool(options.get("translate_pending")),
                translate_concurrency=translate_concurrency,
                target=options.get("target_language"),
                fetcher=fetcher,
                translator=translator,
                on_status=lambda msg: job.status("status", msg),
                on_download_progress=lambda d, t: job.progress("download", d, t),
                on_translate_progress=lambda d, t: job.progress("translate", d, t),
                on_epub_progress=lambda d, t: job.progress("epub", d, t),
                notifier=notifier,
                operation=operation,
                refresh_toc=bool(options.get("refresh_toc")),
                peek_toc=bool(options.get("peek_toc")),
            )
            job.slug = manifest.slug
            job.result = {
                "title": manifest.title,
                "slug": manifest.slug,
                "chapters_downloaded": manifest.chapters_downloaded,
                "chapters_translated": manifest.chapters_translated,
                "chapters_empty": manifest.chapters_empty,
                "chapters_empty_nums": manifest.chapters_empty_nums,
                "epub_original": manifest.epub_original,
                "epub_translated": manifest.epub_translated,
            }
            job.state = JOB_DONE
            job.status("done", f"Listo: {manifest.title}")
            logger.info("job %s completado: %s", job.id, manifest.slug)
            self._record(job, operation, "done", started, manifest=manifest)
        except asyncio.CancelledError:
            job.state = JOB_CANCELLED
            job.status("cancelled", "Job cancelado")
            logger.warning("job %s cancelado", job.id)
            self._record(job, operation, "cancelled", started, error="cancelado")
            raise
        except Exception as exc:  # noqa: BLE001 - capturamos el fallo del job
            job.state = JOB_ERROR
            job.error = str(exc)
            job.status("error", f"Error: {exc}")
            logger.exception("job %s fallo", job.id)
            self._record(job, operation, "error", started, error=str(exc))
        finally:
            await fetcher.aclose()
            if translator is not None:
                await translator.aclose()
            await notifier.aclose()
            JOB_ID.reset(token)

    async def _run_pdf_import(self, job: Job, options: dict[str, Any]) -> None:
        token = JOB_ID.set(job.id)
        started = time.monotonic()
        operation = "pdf"
        logger.info("job %s (pdf) iniciado: %s", job.id, job.url)
        job.state = JOB_RUNNING
        job.status("init", "Preparando PDF")
        translator = (
            build_default_translator() if options.get("translate") else None
        )
        notifier = build_default_notifier()
        try:
            manifest = await run_pdf_pipeline(
                pdf_path=Path(options["pdf_path"]),
                output_dir=job.output_dir,
                source_language=str(options.get("source_language") or "es"),
                translate=bool(options.get("translate")),
                target_language=options.get("target_language"),
                volume_size=options.get("volume_size"),
                translator=translator,
                on_status=lambda msg: job.status("status", msg),
                on_epub_progress=lambda d, t: job.progress("epub", d, t),
                on_translate_progress=lambda d, t: job.progress("translate", d, t),
            )
            job.slug = manifest.slug
            job.result = {
                "title": manifest.title,
                "slug": manifest.slug,
                "chapters_downloaded": manifest.chapters_downloaded,
                "chapters_translated": manifest.chapters_translated,
                "chapters_empty": manifest.chapters_empty,
                "chapters_empty_nums": manifest.chapters_empty_nums,
                "epub_original": manifest.epub_original,
                "epub_translated": manifest.epub_translated,
            }
            job.state = JOB_DONE
            job.status("done", f"Listo: {manifest.title}")
            logger.info("job %s (pdf) completado: %s", job.id, manifest.slug)
            self._record(job, operation, "done", started, manifest=manifest)
        except asyncio.CancelledError:
            job.state = JOB_CANCELLED
            job.status("cancelled", "Job cancelado")
            logger.warning("job %s cancelado", job.id)
            self._record(job, operation, "cancelled", started, error="cancelado")
            raise
        except Exception as exc:  # noqa: BLE001 - capturamos el fallo del job
            job.state = JOB_ERROR
            job.error = str(exc)
            job.status("error", f"Error: {exc}")
            logger.exception("job %s (pdf) fallo", job.id)
            self._record(job, operation, "error", started, error=str(exc))
        finally:
            if translator is not None:
                await translator.aclose()
            await notifier.aclose()
            shutil.rmtree(Path(options["pdf_path"]).parent, ignore_errors=True)
            JOB_ID.reset(token)

    async def _run_pdf_retranslate(self, job: Job, options: dict[str, Any]) -> None:
        token = JOB_ID.set(job.id)
        started = time.monotonic()
        operation = "pdf-retranslate"
        logger.info("job %s (pdf-retranslate) iniciado: %s", job.id, job.url)
        job.state = JOB_RUNNING
        job.status("init", "Preparando re-traducción PDF")
        translator = build_default_translator()
        notifier = build_default_notifier()
        try:
            slug_dir = job.output_dir / str(options["slug"])
            manifest = await retranslate_pdf(
                slug_dir=slug_dir,
                target_language=options.get("target_language"),
                translator=translator,
                on_status=lambda msg: job.status("status", msg),
                on_translate_progress=lambda d, t: job.progress("translate", d, t),
                on_epub_progress=lambda d, t: job.progress("epub", d, t),
            )
            job.slug = manifest.slug
            job.result = {
                "title": manifest.title,
                "slug": manifest.slug,
                "chapters_translated": manifest.chapters_translated,
                "epub_original": manifest.epub_original,
                "epub_translated": manifest.epub_translated,
            }
            job.state = JOB_DONE
            job.status("done", f"Listo: {manifest.title}")
            self._record(job, operation, "done", started, manifest=manifest)
        except asyncio.CancelledError:
            job.state = JOB_CANCELLED
            job.status("cancelled", "Job cancelado")
            logger.warning("job %s cancelado", job.id)
            self._record(job, operation, "cancelled", started, error="cancelado")
            raise
        except Exception as exc:  # noqa: BLE001 - capturamos el fallo del job
            job.state = JOB_ERROR
            job.error = str(exc)
            job.status("error", f"Error: {exc}")
            logger.exception("job %s (pdf-retranslate) fallo", job.id)
            self._record(job, operation, "error", started, error=str(exc))
        finally:
            if translator is not None:
                await translator.aclose()
            await notifier.aclose()
            JOB_ID.reset(token)
