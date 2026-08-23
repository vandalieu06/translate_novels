"""CLI de novel_cli (typer). Orquesta core; no contiene logica de dominio."""

from __future__ import annotations

from typing import Annotated

import typer

from novel_cli.core import config

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
        int | None,
        typer.Option(
            "--volume-size", "-v",
            help="Capitulos por volumen: 50, 100, o sin valor = un solo EPUB",
        ),
    ] = None,
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
        typer.Option("--force", "-f", help="Ignorar manifest y re-descargar todo"),
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
        typer.Option("--concurrency", "-c", help="Workers del pool de descarga (default: 4)"),
    ] = 4,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-V", help="Logs detallados"),
    ] = False,
) -> None:
    """Descarga una web novel, la convierte a EPUB y opcionalmente la traduce."""
    out = config.default_output() if output is None else __import__("pathlib").Path(output)
    typer.echo(f"novel-cli: url={url} output={out} (implementacion pendiente)")


def main() -> None:
    """Entry point del script `novel-cli`."""
    app()


if __name__ == "__main__":
    main()