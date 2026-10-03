"""CLI de novel_cli (typer). Orquesta core; no contiene logica de dominio."""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Annotated, NoReturn
from urllib.parse import urlsplit

import typer
from rich.console import Console
from rich.traceback import install as install_traceback

from novel_cli.cli.progress import ProgressUI
from novel_cli.core import config
from novel_cli.core.models.state import Manifest
from novel_cli.core.models.toc import make_cache
from novel_cli.core.scraper.fetcher import (
    CooldownGate,
    FetchError,
    HttpFetcher,
    Pacer,
    PlaywrightFetcher,
    get_fetcher,
)
from novel_cli.core.scraper.registry import get_adapter
from novel_cli.core.services.download import DownloadError
from novel_cli.core.services.pipeline import PipelineError, run_pipeline
from novel_cli.core.services.toc import crawl_toc
from novel_cli.core.services.translate import TranslateError, build_default_translator
from novel_cli.logging_setup import JOB_ID, configure_logging
from novel_cli.notifications import build_default_notifier
from novel_cli.run_history import RunRecord, append_run, record_from_manifest

logger = logging.getLogger(__name__)

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
        "opcional a un idioma elegible (default es).",
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
                help="Traducir al idioma destino y generar EPUB traducido ademas del original",
            ),
        ] = False,
        target: Annotated[
            str,
            typer.Option(
                "--target",
                help="Idioma destino de la traduccion (default: "
                f"{config.translate_target_default()}; "
                f"disponibles: {', '.join(config.TRANSLATE_TARGET_LANGUAGES)})",
            ),
        ] = config.translate_target_default(),
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
        refresh_toc: Annotated[
            bool,
            typer.Option(
                "--refresh-toc",
                help="Ignorar la cache del TOC y re-escanear el listado completo",
            ),
        ] = False,
        verbose: Annotated[
            bool,
            typer.Option("--verbose", "-V", help="Logs detallados"),
        ] = False,
    ) -> None:
        """Descarga una web novel, la convierte a EPUB y opcionalmente la traduce."""
        if not _valid_url(url):
            _fail("URL invalida: debe ser http(s)", EXIT_VALIDATION)
        if volume_size not in (50, 100, 150, 200):
            _fail("--volume-size solo acepta 50, 100, 150 o 200", EXIT_VALIDATION)
        if concurrency < 1:
            _fail("--concurrency debe ser >= 1", EXIT_VALIDATION)
        if translate_concurrency < 1:
            _fail("--translate-concurrency debe ser >= 1", EXIT_VALIDATION)
        if target not in config.TRANSLATE_TARGET_LANGUAGES:
            _fail(
                f"--target no soportado: {target} (disponibles: "
                f"{', '.join(config.TRANSLATE_TARGET_LANGUAGES)})",
                EXIT_VALIDATION,
            )

        error_console = Console(stderr=True)
        if verbose:
            install_traceback(console=error_console)

        output_dir = Path(output).expanduser() if output else config.default_output()
        configure_logging(output_dir=output_dir, verbose=verbose)
        JOB_ID.set("cli")
        operation = "translate" if translate_pending else "download"
        started = time.monotonic()

        def _record(
            status: str, *, manifest: object | None = None, error: str | None = None
        ) -> None:
            elapsed = time.monotonic() - started
            try:
                if manifest is not None:
                    record = record_from_manifest(
                        manifest,  # type: ignore[arg-type]
                        operation=operation,
                        status=status,
                        duration=elapsed,
                        url=url,
                        error=error,
                    )
                else:
                    record = RunRecord(
                        operation=operation,
                        status=status,
                        url=url,
                        duration_s=round(elapsed, 2),
                        error=error,
                    )
                append_run(output_dir, record)
            except Exception:  # noqa: BLE001 - el historial no debe romper el CLI
                logger.exception("no se pudo escribir el historial de ejecuciones")

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
                notifier = build_default_notifier()

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
                            target=target,
                            fetcher=fetcher,
                            translator=translator,
                            on_status=ui.status,
                            on_download_progress=ui.callback(
                                "download", "Descargando capitulos"
                            ),
                            on_translate_progress=ui.callback(
                                "translate", f"Traduciendo a {target}"
                            ),
                            on_epub_progress=ui.callback(
                                "epub", "Generando EPUBs"
                            ),
                            notifier=notifier,
                            operation=operation,
                            refresh_toc=refresh_toc,
                        )
                    finally:
                        await fetcher.aclose()
                        if translator is not None:
                            await translator.aclose()
                        await notifier.aclose()

                manifest = asyncio.run(_pipeline())
        except typer.Exit:
            raise
        except (FetchError, DownloadError) as exc:
            _record("error", error=str(exc))
            _fail(f"Error de red/descarga: {exc}", EXIT_NETWORK)
        except TranslateError as exc:
            _record("error", error=str(exc))
            _fail(f"Error de traduccion: {exc}", EXIT_TRANSLATION)
        except PipelineError as exc:
            _record("error", error=str(exc))
            _fail(f"Error de EPUB/manifest: {exc}", EXIT_EPUB)
        except Exception as exc:  # noqa: BLE001 - fallback a codigo 4
            _record("error", error=str(exc))
            _fail(f"Error inesperado: {exc}", EXIT_EPUB)

        _record("done", manifest=manifest)
        logger.info("run completado con exito: %s", manifest.slug)

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


def _make_pdf_app() -> typer.Typer:
    """App para `novel-cli pdf`: importa un PDF de novela (EPUB + traduccion opcional)."""
    app = typer.Typer(
        name="pdf",
        help="Importa un PDF de novela: EPUB original (pdf-to-epub) y traduccion "
        "opcional al idioma destino.",
        no_args_is_help=True,
        add_completion=False,
    )

    @app.command()
    def convert(
        file: Annotated[Path, typer.Argument(help="PDF de la novela")],
        output: Annotated[
            str | None,
            typer.Option(
                "--output", "-o",
                help="Directorio de salida (default: core/config.default_output)",
            ),
        ] = None,
        source: Annotated[
            str,
            typer.Option(
                "--source",
                help="Idioma del PDF (default: es; disponibles: "
                f"{', '.join(config.SOURCE_LANGUAGES)})",
            ),
        ] = "es",
        translate: Annotated[
            bool,
            typer.Option(
                "--translate", "-t",
                help="Traducir al idioma destino y generar el EPUB traducido",
            ),
        ] = False,
        target: Annotated[
            str,
            typer.Option(
                "--target",
                help="Idioma destino de la traduccion (default: "
                f"{config.translate_target_default()}; "
                f"disponibles: {', '.join(config.TRANSLATE_TARGET_LANGUAGES)})",
            ),
        ] = config.translate_target_default(),
        volume_size: Annotated[
            int,
            typer.Option(
                "--volume-size", "-v",
                help="Capitulos por tomo del EPUB traducido (default: 50)",
            ),
        ] = config.DEFAULT_VOLUME_SIZE,
        verbose: Annotated[
            bool,
            typer.Option("--verbose", "-V", help="Logs detallados"),
        ] = False,
    ) -> None:
        """Convierte un PDF y opcionalmente lo traduce."""
        from novel_cli.core.services.pdf_import import (
            PdfImportError,
            run_pdf_pipeline,
        )

        if not file.is_file():
            _fail(f"el PDF no existe: {file}", EXIT_VALIDATION)
        if file.suffix.lower() != ".pdf":
            _fail("el archivo debe tener extension .pdf", EXIT_VALIDATION)
        if source not in config.SOURCE_LANGUAGES:
            _fail(
                f"--source no soportado: {source} (disponibles: "
                f"{', '.join(config.SOURCE_LANGUAGES)})",
                EXIT_VALIDATION,
            )
        if target not in config.TRANSLATE_TARGET_LANGUAGES:
            _fail(
                f"--target no soportado: {target} (disponibles: "
                f"{', '.join(config.TRANSLATE_TARGET_LANGUAGES)})",
                EXIT_VALIDATION,
            )
        if volume_size not in (50, 100, 150, 200):
            _fail("--volume-size solo acepta 50, 100, 150 o 200", EXIT_VALIDATION)

        error_console = Console(stderr=True)
        if verbose:
            install_traceback(console=error_console)

        output_dir = Path(output).expanduser() if output else config.default_output()
        configure_logging(output_dir=output_dir, verbose=verbose)
        JOB_ID.set("pdf")
        started = time.monotonic()
        translator = build_default_translator() if translate else None

        def _record(status: str, *, error: str | None = None) -> None:
            elapsed = time.monotonic() - started
            try:
                append_run(
                    output_dir,
                    RunRecord(
                        operation="pdf",
                        status=status,
                        url=str(file),
                        duration_s=round(elapsed, 2),
                        error=error,
                    ),
                )
            except Exception:  # noqa: BLE001 - el historial no debe romper el CLI
                logger.exception("no se pudo escribir el historial de ejecuciones")

        ui = ProgressUI(verbose=verbose)
        try:
            with ui:
                ui.status(f"Salida: {output_dir.resolve()}")

                async def _pipeline() -> object:
                    try:
                        return await run_pdf_pipeline(
                            pdf_path=file,
                            output_dir=output_dir,
                            source_language=source,
                            translate=translate,
                            target_language=target,
                            volume_size=volume_size,
                            translator=translator,
                            on_status=ui.status,
                            on_epub_progress=ui.callback("epub", "Generando EPUBs"),
                            on_translate_progress=ui.callback(
                                "translate", f"Traduciendo a {target}"
                            ),
                        )
                    finally:
                        if translator is not None:
                            await translator.aclose()

                manifest = asyncio.run(_pipeline())
        except typer.Exit:
            raise
        except PdfImportError as exc:
            _record("error", error=str(exc))
            _fail(f"Error de importacion PDF: {exc}", EXIT_VALIDATION)
        except TranslateError as exc:
            _record("error", error=str(exc))
            _fail(f"Error de traduccion: {exc}", EXIT_TRANSLATION)
        except Exception as exc:  # noqa: BLE001 - fallback a codigo 4
            _record("error", error=str(exc))
            _fail(f"Error inesperado: {exc}", EXIT_EPUB)

        _record("done")
        typer.echo(f"Listo: {manifest.title} -> {output_dir / manifest.slug}")
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

        configure_logging(output_dir=config.default_output())

        if not no_browser:
            url = f"http://127.0.0.1:{port}"
            threading.Timer(1.0, lambda: webbrowser.open(url)).start()

        import uvicorn

        uvicorn.run(create_app(), host=host, port=port, log_level="info")

    return app


def _make_toc_app() -> typer.Typer:
    """App para `novel-cli toc`: genera/actualiza la cache del TOC (manual)."""
    app = typer.Typer(
        name="toc",
        help="Genera o actualiza la cache del TOC (.toc.json) de las novelas.",
        no_args_is_help=True,
        add_completion=False,
    )

    @app.command()
    def rebuild(
        slug: Annotated[
            str | None, typer.Option("--slug", help="Novela concreta (slug)")
        ] = None,
        all_novels: Annotated[
            bool, typer.Option("--all", help="Todas las novelas con manifest")
        ] = False,
        pacer_ms: Annotated[
            int,
            typer.Option("--pacer-ms", help="Pausa entre paginas del listado (ms)"),
        ] = config.TOC_REQUEST_MIN_INTERVAL_MS,
        output: Annotated[
            str | None, typer.Option("--output", "-o", help="Directorio de salida")
        ] = None,
    ) -> None:
        """Recorre el listado y escribe output/<slug>/.toc.json."""
        if not slug and not all_novels:
            _fail("indica --slug SLUG o --all", EXIT_VALIDATION)
        if pacer_ms < 0:
            _fail("--pacer-ms debe ser >= 0", EXIT_VALIDATION)
        output_dir = Path(output).expanduser() if output else config.default_output()
        configure_logging(output_dir=output_dir)
        JOB_ID.set("toc")
        targets = _toc_targets(output_dir, slug, all_novels)
        if not targets:
            _fail("no se encontraron novelas con manifest", EXIT_VALIDATION)
        updated = asyncio.run(_rebuild_tocs(targets, pacer_ms))
        typer.echo(f"TOC actualizado en {updated} novela(s)")

    return app


def _toc_targets(
    output_dir: Path, slug: str | None, all_novels: bool
) -> list[Path]:
    """Resuelve los slug_dir con manifest a (re)cachear."""
    if slug:
        candidate = output_dir / slug
        if (candidate / ".manifest.json").exists():
            return [candidate]
        return []
    if not all_novels or not output_dir.exists():
        return []
    return [
        path
        for path in sorted(output_dir.iterdir())
        if path.is_dir() and (path / ".manifest.json").exists()
    ]


async def _rebuild_tocs(targets: list[Path], pacer_ms: int) -> int:
    """Crawlea el TOC de cada novela y escribe su `.toc.json`."""
    pacer = Pacer(pacer_ms)
    http = HttpFetcher(pacer=Pacer(), cooldown=CooldownGate())
    playwright = PlaywrightFetcher()
    fetcher = get_fetcher(http, playwright)
    updated = 0
    try:
        for slug_dir in targets:
            manifest = Manifest.load(slug_dir)
            if manifest is None or not manifest.source_url:
                continue
            adapter = get_adapter(manifest.source_url)
            try:
                site, listing_pages = await crawl_toc(
                    fetcher, adapter, manifest.source_url, toc_pacer=pacer
                )
            except Exception as exc:  # noqa: BLE001 - una novela no corta las demas
                logger.exception("TOC: fallo en %s", slug_dir.name)
                typer.echo(f"ERROR {slug_dir.name}: {exc}", err=True)
                continue
            make_cache(manifest.source_url, site.chapters, listing_pages).save(slug_dir)
            updated += 1
            typer.echo(f"OK    {slug_dir.name}: {len(site.chapters)} capitulos")
    finally:
        await fetcher.aclose()
    return updated


run_app = _make_run_app()
pdf_app = _make_pdf_app()
web_app = _make_web_app()
toc_app = _make_toc_app()

app = run_app  # alias de compatibilidad: la descarga es el comando por defecto


def _valid_url(url: str) -> bool:
    parts = urlsplit(url)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _fail(message: str, code: int) -> NoReturn:
    Console(stderr=True).print(f"[red]Error:[/red] {message}")
    raise typer.Exit(code)


def main() -> None:
    """Entry point del script `novel-cli`: despacha `web`, `toc` o el run por defecto."""
    args = sys.argv[1:]
    if args and args[0] == "web":
        web_app(args[1:])
    elif args and args[0] == "toc":
        toc_app(args[1:])
    elif args and args[0] == "pdf":
        pdf_app(args[1:])
    else:
        run_app(args)


if __name__ == "__main__":
    main()
