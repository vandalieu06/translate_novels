"""Gestion de jobs en background para la web (un pipeline por ejecucion).

Cada job ejecuta ``run_pipeline`` como una coroutine dentro del event loop de
Uvicorn. Los callbacks del pipeline publican eventos que se reenvian a los
clientes WebSocket suscritos.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from novel_cli.core import config
from novel_cli.core.scraper.fetcher import (
    CooldownGate,
    HttpFetcher,
    Pacer,
    PlaywrightFetcher,
    get_fetcher,
)
from novel_cli.core.services.pipeline import run_pipeline
from novel_cli.core.services.translate import build_default_translator

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

    async def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None or job.task is None or job.task.done():
            return False
        job.task.cancel()
        return True

    async def _run(self, job: Job, options: dict[str, Any]) -> None:
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
                fetcher=fetcher,
                translator=translator,
                on_status=lambda msg: job.status("status", msg),
                on_download_progress=lambda d, t: job.progress("download", d, t),
                on_translate_progress=lambda d, t: job.progress("translate", d, t),
                on_epub_progress=lambda d, t: job.progress("epub", d, t),
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
        except asyncio.CancelledError:
            job.state = JOB_CANCELLED
            job.status("cancelled", "Job cancelado")
            raise
        except Exception as exc:  # noqa: BLE001 - capturamos el fallo del job
            job.state = JOB_ERROR
            job.error = str(exc)
            job.status("error", f"Error: {exc}")
        finally:
            await fetcher.aclose()
            if translator is not None:
                await translator.aclose()
