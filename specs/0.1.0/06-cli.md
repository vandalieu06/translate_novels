# 06 — CLI (typer)

## Entrada del CLI

`[project.scripts] novel-cli = "novel_cli.cli.app:main"` → `novel-cli <URL> [flags]`.

## Comando único

Decisión confirmada: un **único comando** que ejecuta el flujo completo:
`resolver sitio → TOC → descargar capítulos → EPUB original → [traducir → EPUB traducido] → manifest`.

### Firma

```python
app = typer.Typer(help="Descarga web novels y las convierte a EPUB, con traducción opcional a español.")

@app.command()
def run(
    url: str = typer.Argument(..., help="URL de la web novel"),
    *,
    output: Path = typer.Option(None, "--output", "-o", help="Directorio de salida (default: core/config.default_output)"),
    volume_size: int | None = typer.Option(None, "--volume-size", "-v", help="Capítulos por volumen: 50, 100, o sin valor = un solo EPUB"),
    translate: bool = typer.Option(False, "--translate", "-t", help="Traducir a español y generar EPUB traducido además del original"),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Reanudar desde el manifest si existe (default: sí)"),
    force: bool = typer.Option(False, "--force", "-f", help="Ignorar manifest y re-descargar todo"),
    playwright: bool = typer.Option(False, "--playwright", "-p", help="Forzar uso de Playwright para todo (sin intentar HTTP primero)"),
    concurrency: int = typer.Option(4, "--concurrency", "-c", help="Workers del pool de descarga (default: 4)"),
    verbose: bool = typer.Option(False, "--verbose", "-V", help="Logs detallados"),
):
    ...
```

### Ruta por defecto

- `core/config.py` define `default_output`:
  1. Env `NOVEL_OUTPUT_DIR` (si está definida y es válida), o
  2. `./output` relativo al directorio de trabajo (compatible con el proyecto viejo que usa `output/`).
- `--output` sobrescribe siempre.
- Dentro, cada novela vive en `output/<slug>/`.

### Flags → comportamiento (resumen)

| Flag | Efecto |
|---|---|
| `-o/--output` | Ruta base de salida. |
| `-v/--volume-size 50|100` | Empaqueta en volúmenes `Novela 1-50.epub`... |
| `-t/--translate` | Genera también EPUB traducido a es (`Novela (ES).epub` o volúmenes `(ES)`). |
| `--resume/--no-resume` | Reanuda según `.manifest.json` (default resume). |
| `-f/--force` | Ignora manifest; re-descarga y re-genera todo. |
| `-p/--playwright` | Fuerza Playwright (sin HTTP primero). |
| `-c/--concurrency` | Workers del pool de descarga (default 4). |
| `-V/--verbose` | Logs detallados (rich traceback, debug). |

### Validación de flags

- `volume_size` solo acepta `50` o `100` (typer `click.Choice([50, 100])`; None = único).
- `concurrency` ≥ 1.
- `url` debe ser http(s) válida.

## Progreso y logs

- `cli/progress.py` usa `rich.progress` para: (1) descarga de capítulos, (2) traducción por capítulo, (3) generación de EPUBs.
- Errores: `typer.echo` a stderr; con `--verbose`, `rich.traceback.install`.
- `core` expone callbacks (`on_progress`, `on_status`) que la CLI conecta a las barras (sin que core importe rich).

## Códigos de salida

- `0` éxito.
- `1` error de entrada/validación.
- `2` fallo de red/descarga (tras reintentos).
- `3` fallo de traducción.
- `4` error de EPUB/manifest.