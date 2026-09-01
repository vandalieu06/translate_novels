"""Aplicacion FastAPI de la web de novel_cli.

Solo capa de presentacion (como ``cli/``): no contiene logica de dominio.
"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from novel_cli.core import config
from novel_cli.web.jobs import JobManager
from novel_cli.web.routes import build_router
from novel_cli.web.ws import build_ws

TOKEN_HEADER = "x-auth-token"


def _token() -> str | None:
    return os.environ.get("NOVEL_WEB_TOKEN") or None


def create_app(*, output_dir: Path | None = None) -> FastAPI:
    out = output_dir or config.default_output()
    manager = JobManager(default_output_dir=out)

    app = FastAPI(title="novel-cli web", version="0.2.0")
    app.state.manager = manager

    web_dir = Path(__file__).parent
    app.mount(
        "/static", StaticFiles(directory=web_dir / "static"), name="static"
    )

    router = build_router(manager)
    ws = build_ws(manager)

    async def check_token(
        x_auth_token: str | None = Header(default=None, alias="X-Auth-Token"),
    ) -> None:
        token = _token()
        if token and x_auth_token != token:
            raise HTTPException(status_code=401, detail="token invalido")

    app.include_router(router, dependencies=[Depends(check_token)])
    app.include_router(ws)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    async def index() -> str:
        return (web_dir / "templates" / "index.html").read_text(encoding="utf-8")

    @app.get("/api/config", include_in_schema=False)
    async def config_info() -> dict[str, object]:
        return {
            "auth_required": _token() is not None,
            "default_volume_size": config.DEFAULT_VOLUME_SIZE,
            "default_concurrency": config.DEFAULT_CONCURRENCY,
        }

    return app


def main() -> None:
    """Entry point de `novel-cli web`."""
    import argparse

    parser = argparse.ArgumentParser(prog="novel-cli web")
    parser.add_argument("--host", default=os.environ.get("NOVEL_WEB_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("NOVEL_WEB_PORT", "8000")))
    parser.add_argument(
        "--no-browser", action="store_true", help="No abrir el navegador al arrancar"
    )
    args = parser.parse_args()

    if not args.no_browser and not os.environ.get("NOVEL_WEB_NO_BROWSER"):
        import threading
        import webbrowser

        url = f"http://127.0.0.1:{args.port}"
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()

    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
