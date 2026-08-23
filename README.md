# novel-cli

CLI para descargar **web novels** y convertirlas en **EPUB**, con traducción opcional a español vía el endpoint gratuito de Google Translate. Descarga por tomos (un volumen por ejecución) para tener el primer EPUB al instante sin bajar toda la novela de golpe.

## Stack

- **Python ≥ 3.11** + **uv**
- **httpx** (async) para el fetch HTTP primero; **Playwright** solo como fallback JS (navegador persistente)
- **ebooklib + lxml** para generar EPUB
- **typer + rich** para el CLI y el progreso
- **pydantic** para el manifest de estado (JSON por novela)
- Sin SQLite, sin Ollama, sin `googletrans`

## Instalación

```bash
uv sync --extra dev
```

## Uso rápido

```bash
# Primer tomo (50 capítulos) → Novela 1-50.epub
novel-cli https://novelfire.net/book/inner-voice-all-heroines-hear-my-inner-voice

# Re-ejecutar el mismo comando avanza al siguiente tomo (51-100, ...)
novel-cli https://novelfire.net/book/inner-voice-all-heroines-hear-my-inner-voice

# Tomos de 100 capítulos + traducción a español
novel-cli https://example.com/novel -v 100 -t

# Descargar toda la novela de una vez
novel-cli https://example.com/novel --all
```

## Flags principales

| Flag | Efecto |
|---|---|
| `-o, --output <dir>` | Directorio de salida (default: env `NOVEL_OUTPUT_DIR` o `./output`). |
| `-v, --volume-size <50\|100>` | Capítulos por tomo (default: **50**). |
| `-t, --translate` | Genera además el EPUB traducido a español. |
| `--resume / --no-resume` | Reanudar según `.manifest.json` (default: resume). |
| `-f, --force` | Ignorar manifest y re-descargar todo. |
| `--all` | Descargar todos los capítulos de golpe (en vez de un tomo por ejecución). |
| `-p, --playwright` | Forzar Playwright (sin intentar HTTP primero). |
| `-c, --concurrency <n>` | Workers del pool de descarga (default: 4). |
| `-V, --verbose` | Logs detallados. |

Salida por novela: `output/<slug>/` con `.manifest.json`, `raw/`, `translated/` (si `-t`) y los EPUB (`Novela 1-50.epub`, `Novela 1-50 (ES).epub`, ...).

## Documentación

- **[Uso detallado](docs/uso.md)** — flags, ejemplos, estructura de salida, reanudación, códigos de salida y traducción.
- **[Arquitectura](docs/arquitectura.md)** — diseño técnico, módulos, flujo de datos, estado, red/retry, EPUB, errores y testing.
- **[Features](docs/features.md)** — funcionalidades actuales y roadmap de posibles mejoras.

## Desarrollo

```bash
uv run pytest -q     # tests unitarios (sin red: respx + fixtures)
uv run ruff check .  # lint
```