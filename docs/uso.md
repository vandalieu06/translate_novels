# Uso de novel-cli

> Documentos relacionados: [Arquitectura](arquitectura.md) · [Features](features.md)

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
| `--translate-pending` | Traduce **solo los capítulos pendientes** (ya descargados pero sin traducir) sin descargar nuevos; retoma el trabajo colgado desde el manifest previo (sin red). |
| `-p, --playwright` | Fuerza Playwright para todo (sin intentar HTTP primero). |
| `-c, --concurrency <n>` | Workers del pool de descarga (default: 4). |
| `-tc, --translate-concurrency <n>` | Workers de **traducción en paralelo** (capítulos a la vez). Default inteligente según backend: **1** para Google (protegido), **4** para LibreTranslate local. Tope máximo por defecto: 16. |
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
- **Capítulos vacíos**: si el parser devuelve 0 párrafos para un capítulo (página sin contenido parseable), se **reintenta** al final del lote. Si persiste, queda en "pendientes de reintento": se muestra un **aviso** (`AVISO: N capítulo(s) vacío(s) pendientes de reintento`) en el CLI y en la web, y el capítulo **no** cuenta como descargado. Un archivo vacío no cuenta como "ya descargado", así que re-ejecutar el mismo comando lo reintenta automáticamente.

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
- Respeta pacing, retry con backoff (5 reintentos, base 5 s) y `Retry-After` (hasta 60 s) ante 429/503, con un cool-down compartido para toda la pasada de traducción. Si el endpoint te limita de forma persistente, saldrá con código 3; re-ejecuta más tarde para continuar (la caché evita re-traducir lo hecho).
- **Traducción en paralelo**: los capítulos se traducen a la vez (`-tc, --translate-concurrency`). El pacer sigue limitando el ritmo global de peticiones, así que el paralelismo no "quema" el endpoint.
- El pacer es ajustable por env: `NOVEL_TRANSLATE_PACER_MS` (ms entre peticiones).

### Traducción local con Docker/podman (LibreTranslate)

Si Google te limita, puedes levantar un motor local sin rate-limit (LibreTranslate) y apuntar el CLI:

```bash
# 1. Levantar LibreTranslate (podman rootless + docker-compose instalado)
podman compose up -d           # primer arranque descarga modelos (minutos)

# 2. Probar la API local
curl -X POST localhost:5000/translate -H 'Content-Type: application/json' \
     -d '{"q":"Hello","source":"auto","target":"es","format":"text"}'

# 3. Usar novel-cli con LibreTranslate (concurrencia alta para CPUs potentes)
NOVEL_TRANSLATE_BACKEND=libre uv run novel-cli -t <url> -tc 8
```

- El `compose.yaml` del repo expone el puerto solo en `127.0.0.1` y guarda los modelos en un volumen con nombre.
- Configuración vía env: `NOVEL_TRANSLATE_BACKEND` (`google`|`libre`), `NOVEL_TRANSLATE_URL` (default `http://localhost:5000`) y `NOVEL_TRANSLATE_API_KEY` (opcional).

#### Concurrencia de traducción: defaults y protección

| Backend | Default `-tc` | Pacer default | Protección |
|---|---|---|---|
| `google` | **1** | 1500 ms | Fuerza concurrencia = **1** (ignora `-tc`) para no arriesgar rate-limit. |
| `libre` | **4** | 250 ms | Tope máximo (default **16**, env `NOVEL_TRANSLATE_MAX_CONCURRENCY`) para no saturar el servidor local. |

Con LibreTranslate local y una CPU potente puedes subir la concurrencia (`-tc 8`, `-tc 16`) y bajar el pacer a ~100–500 ms (`NOVEL_TRANSLATE_PACER_MS`) para traducir 100 capítulos en mucho menos tiempo sin ir capítulo a capítulo.

### Retomar traducción pendiente (`--translate-pending`)

Si una traducción se cortó (p. ej. por rate-limit), puedes traducir **solo lo colgado** sin volver a descargar ni avanzar de tomo:

```bash
uv run novel-cli -t <url>                  # se corta a mitad...
uv run novel-cli --translate-pending <url> # traduce solo lo pendiente, sin red
```

Busca el manifest previo por `source_url`, traduce los capítulos que falten en `translated/` y regenera los EPUB `(ES)` que falten. No descarga capítulos nuevos ni toca el TOC.

## Variables de entorno

| Variable | Uso |
|---|---|
| `NOVEL_OUTPUT_DIR` | Directorio de salida por defecto (si no se pasa `-o`). |
| `NOVEL_TRANSLATE_PACER_MS` | Milisegundos entre peticiones de traducción (default según backend: 1500 google / 250 libre). |
| `NOVEL_TRANSLATE_CONCURRENCY` | Workers de traducción explícitos (0 = auto según backend). |
| `NOVEL_TRANSLATE_MAX_CONCURRENCY` | Tope máximo de concurrencia de traducción (default: 16). |
| `NOVEL_TRANSLATE_BACKEND` | Backend de traducción: `google` (default) o `libre`. |
| `NOVEL_TRANSLATE_URL` | Base URL de LibreTranslate (default: `http://localhost:5000`). |
| `NOVEL_TRANSLATE_API_KEY` | API key opcional para LibreTranslate. |
| `NOVEL_WEB_TOKEN` | Si está definida, la web exige este token para las llamadas a la API (cabecera `X-Auth-Token`). Recomendado si expones la web fuera de tu LAN. |
| `NOVEL_WEB_HOST` / `NOVEL_WEB_PORT` | Valores por defecto de `--host` / `--port` (default: `0.0.0.0` / `8000`). |

## Interfaz web (`novel-cli web`)

Desde la versión 0.2.0 puedes controlar novel-cli desde el navegador (móvil, tablet o escritorio) sin SSH: un servidor FastAPI sirve una UI responsive que permite lanzar descargas/traducciones, ver el progreso en vivo y descargar los EPUB generados.

```bash
# Lanza el servidor (escucha en 0.0.0.0:8000 para acceder desde tu LAN)
uv run novel-cli web

# Desde la propia máquina con el navegador abierto
uv run novel-cli web --port 8080

# Sin abrir navegador y con token de acceso
NOVEL_WEB_TOKEN=clave-secreta uv run novel-cli web --no-browser
```

Desde la tablet/móvil abre `http://<ip-del-pc>:8000/` en el navegador (ambos en la misma red).

### Qué ofrece

- **Lanzar descarga**: URL, tomo (`50`/`100`), concurrencia y opciones (`--translate`, `--all`, `--translate-pending`, `--force`, `--playwright`), igual que el CLI.
- **Progreso en vivo** por WebSocket: fases de descarga, traducción y EPUB con barras y contadores.
- **Sincronizar novela** (botón **↻ Sync** en cada tarjeta): obtiene nuevos capítulos de una novela ya descargada **sin re-pegar la URL**. El sync reusa la `source_url` guardada y el mismo mecanismo de la CLI (misma URL + `--resume` → descarga el siguiente tomo pendiente), y **hereda la traducción y el tamaño de tomo** de la novela: si la novela se descargó traducida, los nuevos capítulos también se traducen y se regenera el EPUB `(ES)`.
- **Biblioteca**: lista las novelas ya descargadas (`output/<slug>/`) con portada, % de progreso, nº de volúmenes y botones para **descargar los EPUB** (original y traducido) directamente al dispositivo.
- **Cancelar** un job en curso.
- **Un job activo a la vez**: al lanzar un job nuevo, la UI consulta `GET /api/jobs` en el servidor y bloquea "Lanzar descarga"/"Sync" mientras exista un job en estado `pending` o `running`. Al terminar (listo/error/cancelado) se puede lanzar otro inmediatamente.

### Nota sobre puertos y WebSocket

La web usa **un solo puerto** (default `8000`, configurable con `--port` o `NOVEL_WEB_PORT`). El **WebSocket no abre un puerto adicional**: viaja por el mismo puerto HTTP en la ruta `/api/jobs/{id}/ws` (upgrade del protocolo). Los únicos puertos que puede abrir la app son:

- **`8000`** — servidor web (`novel-cli web`). Único puerto de la web.
- **`5000`** — LibreTranslate, **solo** si usas `NOVEL_TRANSLATE_BACKEND=libre` para traducción local (ver `docker-compose.yaml`). No es de la web.

Si accedes desde la LAN, abre en la tablet/móvil `http://<ip-del-pc>:8000/` (o el puerto que hayas elegido).

#### Por qué en los logs aparecen "muchos puertos"

Es normal y no significa que la app abra varios puertos. La app solo escucha en **uno** (`8000`); los demás números que aparecen en los logs son **puertos efímeros de origen**, que el sistema operativo asigna automáticamente a cada conexión TCP del cliente y que cambian en cada request. No hay que abrirlos en el firewall ni son de la app.

Ejemplo real:

```
INFO:     Uvicorn running on http://0.0.0.0:8000          <- ÚNICO puerto de la app (destino)
INFO:     127.0.0.1:41570 - "GET / HTTP/1.1" 200 OK
INFO:     127.0.0.1:41570 - "GET /static/css/app.css" 200 OK   <- mismo 41570: conexión reutilizada
INFO:     127.0.0.1:50528 - "GET /api/novels HTTP/1.1" 200 OK   <- nueva conexión efímera
INFO:     127.0.0.1:42014 - "WebSocket /api/jobs/.../ws" [accepted]  <- upgrade HTTP→WS, mismo puerto 8000
```

- **`0.0.0.0:8000`** = dónde escucha el servidor (el único real).
- **`127.0.0.1:41570`** = dirección del cliente + **puerto efímero de origen** (lo elige el SO). El navegador reutiliza la misma conexión TCP (HTTP keep-alive), por eso varias requests comparten el mismo número.
- Cada vez que el navegador (o el JS) abre una conexión nueva, el SO le asigna un puerto efímero distinto (`50528`, `41998`, `42014`, `33134`, `37688`, ...). No es la app abriendo puertos.
- El **WebSocket** (`42014`) tampoco abre un puerto nuevo: es un *upgrade* HTTP→WS sobre la misma conexión del puerto `8000`.
- El **mismo puerto repetido** (`41998` muchas veces con `GET /api/jobs/...`) es el **polling de respaldo** (cada 1,5 s) mientras un job corre, por si el WebSocket se cae.
- Los **`304 Not Modified`** (JS/CSS) significan "no ha cambiado, usa la caché": el navegador revalida los assets sin re-descargarlos.

En resumen: solo tienes que permitir el puerto **`8000`** hacia el PC. El resto son puertos de origen efímeros del cliente, irrelevantes para tu configuración.

### Opciones de `novel-cli web`

| Flag | Efecto |
|---|---|
| `--host <ip>` | Interfaz a la que escuchar (default: `0.0.0.0` para LAN). |
| `--port <n>` | Puerto (default: `8000`). |
| `--no-browser` | No abre el navegador al arrancar. |

### Notas

- El servidor mantiene los jobs **en memoria** (un job activo a la vez): debe permanecer lanzado mientras dura una descarga/traducción.
- Se puede proteger con `NOVEL_WEB_TOKEN`; la UI lo pide una vez y lo guarda en `localStorage`.
- También existe el entry point `novel-cli-web` equivalente a `novel-cli web`.