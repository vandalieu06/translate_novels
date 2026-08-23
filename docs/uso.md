# Uso de novel-cli

CLI para descargar web novels, convertirlas a EPUB y opcionalmente traducirlas a español (endpoint gratuito de Google Translate). Escrito en Python con `uv`, `httpx`, `ebooklib`, `typer` y `rich`.

## Instalación

```bash
uv sync --extra dev     # dependencias del proyecto + dev
```

## Uso básico

```bash
novel-cli <URL> [flags]
```

Un solo comando ejecuta el flujo completo: resolver el sitio → obtener TOC → descargar capítulos → generar EPUB original → (opcional) traducir y generar EPUB traducido → escribir el manifest.

### Descarga por tomos (comportamiento por defecto)

Por defecto la novela se descarga **un tomo a la vez**:

- `-v` (tamaño de volumen) tiene como valor por defecto **50**.
- La primera ejecución descarga los primeros `50` capítulos y genera `Novela 1-50.epub`.
- Re-ejecutar el mismo comando **avanza al siguiente tomo**: descarga `51-100`, `101-150`, ... y añade su EPUB sin reescribir los anteriores.
- Cuando todos los capítulos están descargados, re-ejecutar no descarga ni reescribe nada (idempotente).

Esto te da un primer volumen al instante sin bajar toda la novela de golpe. Para descargarlo todo de una vez usa `--all`.

### Flags

| Flag | Efecto |
|---|---|
| `-o, --output <dir>` | Directorio base de salida (default: env `NOVEL_OUTPUT_DIR` o `./output`). |
| `-v, --volume-size <50\|100>` | Capítulos por tomo (default: **50**). |
| `-t, --translate` | Traduce a español y genera además el EPUB traducido (`Novela 1-50 (ES).epub`). |
| `--resume / --no-resume` | Reanudar según `.manifest.json` (default: `--resume`). |
| `-f, --force` | Ignora el manifest y re-descarga (y re-traduce) todo. |
| `--all` | Descarga **todos** los capítulos de golpe (en vez de un tomo por ejecución). |
| `-p, --playwright` | Fuerza Playwright para todo (sin intentar HTTP primero). |
| `-c, --concurrency <n>` | Workers del pool de descarga (default: 4). |
| `-V, --verbose` | Logs detallados y traceback. |

## Ejemplos

```bash
# Primer tomo (1-50) y avance al siguiente con la misma orden
novel-cli https://novelfire.net/book/inner-voice-all-heroines-hear-my-inner-voice
novel-cli https://novelfire.net/book/inner-voice-all-heroines-hear-my-inner-voice   # ahora baja 51-100

# Tomos de 100 capítulos + traducción a español
novel-cli https://example.com/novel -v 100 -t

# Descargar toda la novela de una vez, en tomos de 50
novel-cli https://example.com/novel --all

# Salida en otro directorio y con 8 workers
novel-cli https://example.com/novel -o /media/lecturas -c 8

# Re-descargar desde cero
novel-cli https://example.com/novel --force
```

## Estructura de salida

Cada novela vive en `output/<slug>/` (el slug deriva del título):

```
output/
└── <slug>/
    ├── .manifest.json        # estado/índice (fuente de verdad para reanudar)
    ├── cover.jpg             # portada local (si el sitio la dio)
    ├── raw/                  # capítulos en idioma original (0001.md, 0002.md, ...)
    ├── translated/           # capítulos traducidos a es (si --translate)
    ├── Novela 1-50.epub
    ├── Novela 51-100.epub
    └── Novela 1-50 (ES).epub  # traducido (si --translate)
```

- La portada es la misma para todos los tomos.
- Los EPUB incluyen `content.opf`, `toc.ncx`, portada y un capítulo XHTML por capítulo con `<h1>` + un `<p>` por párrafo (estructura original conservada 1:1).

## Reanudación

- La fuente de verdad de "ya descargado/traducido" es la **existencia del archivo** en disco (`raw/<NNNN>.md`, `translated/<NNNN>.md`); el `.manifest.json` es el índice.
- Con `--resume` (default) se saltan las fases ya completadas y los EPUB que ya existen no se reescriben.
- Con `--force` se re-descarga y re-traduce todo desde cero.
- Con `--no-resume` no se consulta el manifest, pero la existencia de archivos sigue evitando re-descargas.

## Códigos de salida

| Código | Significado |
|---|---|
| `0` | Éxito. |
| `1` | Error de entrada/validación (URL inválida, `-v` distinto de 50/100, concurrency < 1). |
| `2` | Fallo de red/descarga (tras reintentos; incluye fallo del fallback Playwright). |
| `3` | Fallo de traducción. |
| `4` | Error de EPUB/manifest u otro inesperado. |

## Traducción

- Backend por defecto: endpoint gratuito `translate.googleapis.com/translate_a/single` (`client=gtx`), sin clave ni token.
- Traduce **párrafo a párrafo** con chunking (~400 palabras) y reensamblado 1:1, por lo que el EPUB traducido conserva la estructura del original.
- Respeta pacing (~300 ms), retry con backoff y `Retry-After` ante 429/503. Si el endpoint te limita (429 persistente), saldrá con código 3; re-ejecuta más tarde para continuar con lo pendiente (la caché evita re-traducir lo hecho).

## Variables de entorno

| Variable | Uso |
|---|---|
| `NOVEL_OUTPUT_DIR` | Directorio de salida por defecto (si no se pasa `-o`). |