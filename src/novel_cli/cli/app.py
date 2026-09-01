"""CLI de novel_cli (typer). Orquesta core; no contiene logica de dominio."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Annotated, NoReturn
from urllib.parse import urlsplit

import typer
from rich.console import Console
from rich.traceback import install as install_traceback

from novel_cli.cli.progress import ProgressUI
from novel_cli.core import config
from novel_cli.core.scraper.fetcher import (
    CooldownGate,
    FetchError,
    HttpFetcher,
    Pacer,
    PlaywrightFetcher,
    get_fetcher,
)
from novel_cli.core.services.download import DownloadError
from novel_cli.core.services.pipeline import PipelineError, run_pipeline
from novel_cli.core.services.translate import TranslateError, build_default_translator

EXIT_OK = 0
EXIT_VALIDATION = 1
EXIT_NETWORK = 2
EXIT_TRANSLATION = 3
EXIT_EPUB = 4


def _make_run_app() -> typer.Typer:
    """App para `novel-cli <url>`: la descarga es el comando por defecto."""
    app = typer.Typer(
        name="novel-cli",
        help="Descarga web novels y las convierte a EPUB, con traduccion "
        "opcional a espanol.",
        no_args_is_help=True,
        add_completion=False,
    )

    @app.command()
    def run(
        url: Annotated[str, typer.Argument(help="URL de la web novel")],
        output: Annotated[
            str | None,
            typer.Option(
                "--output", "-o",
                help="Directorio de salida (default: core/config.default_output)",
            ),
        ] = None,
        volume_size: Annotated[
            int,
            typer.Option(
                "--volume-size", "-v",
                help="Capitulos por volumen: 50 o 100 (default: 50)",
            ),
        ] = config.DEFAULT_VOLUME_SIZE,
        translate: Annotated[
            bool,
            typer.Option(
                "--translate", "-t",
                help="Traducir a espanol y generar EPUB traducido ademas del original",
            ),
        ] = False,
        resume: Annotated[
            bool,
            typer.Option(
                "--resume/--no-resume",
                help="Reanudar desde el manifest si existe (default: si)",
            ),
        ] = True,
        force: Annotated[
            bool,
            typer.Option(
                "--force", "-f",
                help="Ignorar manifest y re-descargar todo",
            ),
        ] = False,
        all_chapters: Annotated[
            bool,
            typer.Option(
                "--all",
                help="Descargar todos los capitulos de golpe (en vez de un tomo por ejecucion)",
            ),
        ] = False,
        translate_pending: Annotated[
            bool,
            typer.Option(
                "--translate-pending",
                help="Traducir solo los capitulos pendientes (ya descargados) sin "
                "descargar nuevos; retoma el trabajo colgado desde el manifest previo",
            ),
        ] = False,
        playwright: Annotated[
            bool,
            typer.Option(
                "--playwright", "-p",
                help="Forzar uso de Playwright para todo (sin intentar HTTP primero)",
            ),
        ] = False,
        concurrency: Annotated[
            int,
            typer.Option(
                "--concurrency", "-c",
                help="Workers del pool de descarga (default: 4)",
            ),
        ] = config.DEFAULT_CONCURRENCY,
        translate_concurrency: Annotated[
            int,
            typer.Option(
                "--translate-concurrency", "-tc",
                help="Workers de traduccion en paralelo (default: segun backend; "
                "1 para google, 4 para LibreTranslate local)",
            ),
        ] = config.translate_concurrency_default(),
        verbose: Annotated[
            bool,
            typer.Option("--verbose", "-V", help="Logs detallados"),
        ] = False,
    ) -> None:
        """Descarga una web novel, la convierte a EPUB y opcionalmente la traduce."""
        if not _valid_url(url):
            _fail("URL invalida: debe ser http(s)", EXIT_VALIDATION)
        if volume_size not in (50, 100):
            _fail("--volume-size solo acepta 50 o 100", EXIT_VALIDATION)
        if concurrency < 1:
            _fail("--concurrency debe ser >= 1", EXIT_VALIDATION)
        if translate_concurrency < 1:
            _fail("--translate-concurrency debe ser >= 1", EXIT_VALIDATION)

        error_console = Console(stderr=True)
        if verbose:
            install_traceback(console=error_console)

        output_dir = Path(output).expanduser() if output else config.default_output()
        ui = ProgressUI(verbose=verbose)
        try:
            with ui:
                ui.status(f"Salida: {output_dir.resolve()}")
                http = HttpFetcher(pacer=Pacer(), cooldown=CooldownGate())
                playwright_fetcher = PlaywrightFetcher()
                fetcher = get_fetcher(
                    http, playwright_fetcher, force_playwright=playwright
                )
                translator = (
                    build_default_translator()
                    if (translate or translate_pending)
                    else None
                )

                async def _pipeline() -> object:
                    try:
                        return await run_pipeline(
                            url=url,
                            output_dir=output_dir,
                            volume_size=volume_size,
                            translate=translate,
                            resume=resume,
                            force=force,
                            concurrency=concurrency,
                            download_all=all_chapters,
                            translate_pending=translate_pending,
                            translate_concurrency=translate_concurrency,
                            fetcher=fetcher,
                            translator=translator,
                            on_status=ui.status,
                            on_download_progress=ui.callback(
                                "download", "Descargando capitulos"
                            ),
                            on_translate_progress=ui.callback(
                                "translate", "Traduciendo a espanol"
                            ),
                            on_epub_progress=ui.callback(
                                "epub", "Generando EPUBs"
                            ),
                        )
                    finally:
                        await fetcher.aclose()
                        if translator is not None:
                            await translator.aclose()

                manifest = asyncio.run(_pipeline())
        except (FetchError, DownloadError) as exc:
            _fail(f"Error de red/descarga: {exc}", EXIT_NETWORK)
        except TranslateError as exc:
            _fail(f"Error de traduccion: {exc}", EXIT_TRANSLATION)
        except PipelineError as exc:
            _fail(f"Error de EPUB/manifest: {exc}", EXIT_EPUB)
        except typer.Exit:
            raise
        except Exception as exc:  # noqa: BLE001 - fallback a codigo 4
            _fail(f"Error inesperado: {exc}", EXIT_EPUB)

        typer.echo(f"Listo: {manifest.title} -> {output_dir / manifest.slug}")
        if manifest.chapters_empty:
            nums = ", ".join(str(n) for n in manifest.chapters_empty_nums[:20])
            extra = "..." if len(manifest.chapters_empty_nums) > 20 else ""
            Console(stderr=True).print(
                f"[yellow]AVISO:[/yellow] {manifest.chapters_empty} capitulo(s) "
                f"vacio(s) pendientes de reintento: {nums}{extra}"
            )
        raise typer.Exit(EXIT_OK)

    return app


def _make_web_app() -> typer.Typer:
    """App para `novel-cli web`: lanza el servidor web."""
    app = typer.Typer(
        name="web",
        help="Lanza la interfaz web (FastAPI + UI) para usar novel_cli desde el "
        "navegador.",
        no_args_is_help=True,
        add_completion=False,
    )

    @app.command()
    def serve(
        host: Annotated[
            str,
            typer.Option(
                "--host",
                help="Interfaz a la que escuchar (default: 0.0.0.0 para LAN)",
            ),
        ] = "0.0.0.0",
        port: Annotated[
            int,
            typer.Option(
                "--port",
                help="Puerto del servidor (default: 8000)",
            ),
        ] = 8000,
        no_browser: Annotated[
            bool,
            typer.Option("--no-browser", help="No abrir el navegador al arrancar"),
        ] = False,
    ) -> None:
        """Arranca el servidor FastAPI con la UI."""
        import threading
        import webbrowser

        from novel_cli.web.app import create_app

        if not no_browser:
            url = f"http://127.0.0.1:{port}"
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()

        import uvicorn

        uvicorn.run(create_app(), host=host, port=port, log_level="info")

    return app


run_app = _make_run_app()
web_app = _make_web_app()

app = run_app  # alias de compatibilidad: la descarga es el comando por defecto


def _valid_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _fail(message: str, code: int) -> NoReturn:
    Console(stderr=True).print(f"[red]Error:[/red] {message}")
    raise typer.Exit(code)


def main() -> None:
    """Entry point del script `novel-cli`: despacha `web` o el run por defecto."""
    args = sys.argv[1:]
    if args and args[0] == "web":
        web_app(args[1:])
    else:
        run_app(args)


if __name__ == "__main__":
    main()
