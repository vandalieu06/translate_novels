"""CLI de novel_cli (typer). Orquesta core; no contiene logica de dominio."""

from __future__ import annotations

import asyncio
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

app = typer.Typer(
    name="novel-cli",
    help="Descarga web novels y las convierte a EPUB, con traduccion opcional a espanol.",
    no_args_is_help=True,
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
            help="Traducir solo los capitulos pendientes (ya descargados) sin descargar "
            "nuevos; retoma el trabajo colgado desde el manifest previo",
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
            fetcher = get_fetcher(http, playwright_fetcher, force_playwright=playwright)
            translator = (
                build_default_translator() if (translate or translate_pending) else None
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
                        fetcher=fetcher,
                        translator=translator,
                        on_status=ui.status,
                        on_download_progress=ui.callback(
                            "download", "Descargando capitulos"
                        ),
                        on_translate_progress=ui.callback(
                            "translate", "Traduciendo a espanol"
                        ),
                        on_epub_progress=ui.callback("epub", "Generando EPUBs"),
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
    raise typer.Exit(EXIT_OK)


def _valid_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _fail(message: str, code: int) -> NoReturn:
    Console(stderr=True).print(f"[red]Error:[/red] {message}")
    raise typer.Exit(code)


def main() -> None:
    """Entry point del script `novel-cli`."""
    app()


if __name__ == "__main__":
    main()