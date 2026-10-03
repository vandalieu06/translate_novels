"""WebSocket de progreso: suscripcion a los eventos de un job."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from novel_cli.web.jobs import JobManager


def build_ws(manager: JobManager) -> APIRouter:
    router = APIRouter()

    @router.websocket("/api/jobs/{job_id}/ws")
    async def job_ws(websocket: WebSocket, job_id: str) -> None:
        await websocket.accept()
        job = manager.get(job_id)
        if job is None:
            await websocket.send_json({"type": "error", "message": "job no encontrado"})
            await websocket.close()
            return

        for event in job.events:
            await websocket.send_json(event)

        loop = asyncio.get_running_loop()

        def forward(event: dict[str, object]) -> None:
            # Los eventos pueden llegar desde un hilo de trabajo (p. ej. la
            # conversion de un PDF en asyncio.to_thread), donde no hay event
            # loop: se programa el envio sobre el loop principal.
            asyncio.run_coroutine_threadsafe(websocket.send_json(event), loop)

        unsubscribe = job.subscribe(forward)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            unsubscribe()

    return router
