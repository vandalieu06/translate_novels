# Uso de novel-cli

> Documentos relacionados: [Arquitectura](arquitectura.md) · [Features](features.md)

CLI para descargar web novels, convertirlas a EPUB y opcionalmente traducirlas a un idioma elegible (por defecto español; endpoint gratuito de Google Translate o LibreTranslate local). Escrito en Python con `uv`, `httpx`, `ebooklib`, `typer` y `rich`.

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
| `-t, --translate` | Traduce al idioma destino y genera además el EPUB traducido (`Novela 1-50 (ES).epub`). |
| `--target <lang>` | Idioma destino de la traducción (default `es` o `NOVEL_TRANSLATE_TARGET`). Disponibles: `es`, `en`, `fr`, `de`, `it`, `pt`, `ru`, `ja`, `ko`, `zh`. |
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

# Tomos de 100 capítulos + traducción a español (idioma por defecto)
novel-cli https://example.com/novel -v 100 -t

# Traducción a otro idioma
novel-cli https://example.com/novel -t --target fr

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
- En los **EPUBs**, un capítulo sin contenido (raw vacío o sin traducción) no sale en blanco: lleva un **aviso** (`(Chapter content not available…)` en el original, `(Capítulo sin contenido disponible…)` en el traducido). Los tomos del EPUB traducido se **alinean** con los del original aunque falten capítulos.
- Al re-traducir (`--translate-pending` o con `-t`): si un capítulo estaba vacío y luego se arregló su raw, se **re-traduce** desde el raw corregido (un `translated/` vacío no cuenta como ya traducido). Si el raw sigue vacío, el `translated/` vacío heredado se **limpia** para que el EPUB traducido no incluya capítulos en blanco.

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

> **Rate-limit**: LibreTranslate limita por defecto a ~200 peticiones/día/IP, lo que **rompe re-traducciones largas con 429** (el job falla a mitad). El `docker-compose.yaml` ya define `LT_API_KEYS=local` (con API key se omite el límite); el `.env` lleva `NOVEL_TRANSLATE_API_KEY=local` para que el CLI y la web la envíen. Si recreas el contenedor, asegúrate de que ambas claves coincidan. Recuerda **reiniciar `novel-cli web`** tras cambiar el `.env`.
```

**Acelerar con CUDA (GPU NVIDIA)**: si tienes una GPU NVIDIA, el contenedor `latest-cuda` traduce mucho más rápido. Usa `docker-compose.cuda.yaml` (se lanza con **`sudo docker compose`**):

```bash
# 1. Instalar el NVIDIA Container Toolkit (solo la primera vez, requiere sudo)
sudo pacman -S nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# 2. Detener el contenedor CPU (comparte el puerto 5000, no pueden estar a la vez)
podman compose down

# 3. Lanzar el CUDA
sudo docker compose -f docker-compose.cuda.yaml up -d
```

El `.env` no cambia (mismo puerto `5000`, misma key `local`). Para volver al CPU: `sudo docker compose -f docker-compose.cuda.yaml down` y `podman compose up -d`. El `docker-compose.cuda.yaml` persiste los modelos en un volumen propio (`libretranslate_cuda_models`).

- El `compose.yaml` del repo expone el puerto solo en `127.0.0.1` y guarda los modelos en un volumen con nombre.
- Configuración vía env: `NOVEL_TRANSLATE_BACKEND` (`google`|`libre`), `NOVEL_TRANSLATE_URL` (default `http://localhost:5000`) y `NOVEL_TRANSLATE_API_KEY` (opcional).
- **Configuración persistente con `.env`**: novel-cli carga un `.env` del directorio de trabajo (o el de `NOVEL_CLI_ENV_FILE`) al arrancar, sin sobrescribir variables ya exportadas. Crea un `.env` en la raíz (ya está en `.gitignore`) con:
  ```
  NOVEL_TRANSLATE_BACKEND=libre
  NOVEL_TRANSLATE_URL=http://127.0.0.1:5000
  ```
  Así `novel-cli web` y el CLI quedan apuntando a LibreTranslate sin exportar nada en cada arranque. La web muestra el motor activo ("Traducción: LibreTranslate") junto al estado del servidor.

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
| `NOVEL_CLI_ENV_FILE` | Ruta al `.env` a cargar al arrancar (default: `.env` del directorio de trabajo). |
| `NOVEL_TELEGRAM_BOT_TOKEN` | Token del bot de Telegram (de @BotFather) para enviar notificaciones. |
| `NOVEL_TELEGRAM_CHAT_ID` | `chat_id` destino de las notificaciones (uno). |
| `NOVEL_TELEGRAM_ENABLED` | `off`/`false` desactiva las notificaciones aunque haya token+chat. |
| `NOVEL_WEB_TOKEN` | Si está definida, la web exige este token para las llamadas a la API (cabecera `X-Auth-Token`). Recomendado si expones la web fuera de tu LAN. |
| `NOVEL_WEB_HOST` / `NOVEL_WEB_PORT` | Valores por defecto de `--host` / `--port` (default: `0.0.0.0` / `8000`). |

## Notificaciones por Telegram

Si no quieres quedarte pendiente de la web/terminal, el CLI puede avisarte por
Telegram al terminar cada sync/descarga (y al fallar). Usa
[python-telegram-bot](https://docs.python-telegram-bot.org/) **solo para enviar**
mensajes: no hace falta exponer nada ni dejar un proceso de bot corriendo.

### Configuración

1. Crea un bot con [@BotFather](https://t.me/BotFather) y copia el **token**.
2. Obtén tu **chat_id** (p. ej. hablándole a [@userinfobot](https://t.me/userinfobot)).
3. Añádelo al `.env` de la raíz (ya está en `.gitignore`, no se sube a git):

   ```
   NOVEL_TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
   NOVEL_TELEGRAM_CHAT_ID=987654321
   ```

Con eso, **tanto el CLI como `novel-cli web`** envían notificaciones. Para
desactivarlas sin borrar el token: `NOVEL_TELEGRAM_ENABLED=off`. Si no defines
token y chat, no se envía nada y el comportamiento es el de siempre.

### Qué se notifica

- **Un resumen** al terminar el job: capítulos descargados (con el total del TOC
  y los vacíos pendientes), tomos del EPUB original, traducción a `<LANG>` y
  tomos del EPUB traducido. La cabecera indica la **operación** (Descarga / Sync
  / Traducción / Re-traducción) y la **duración del job completo** (incluye
  scrape y traducción; los jobs muy cortos se muestran como `<1s`). En la línea
  de traducción se distingue lo traducido en este run del total: `50 capítulos`,
  `2 nuevos (total 1000)` o `sin cambios (total 1000)`.
- **Un aviso inmediato** si el pipeline falla, con la fase (descarga, traducción,
  EPUB) y el detalle del error. La fase se infiere del tipo de excepción.

```
✅ Renacido como el Héroe
Sync completado · 2m 14s

📥 Descarga: 50/512 capítulos ⚠️ 2 vacíos
📚 EPUB original: 1 tomo
🌐 Traducción ES: 50 capítulos
📗 EPUB ES: 1 tomo
```

```
❌ Error en descarga — Renacido como el Héroe
HTTP 429 tras 3 reintentos
tras 12s
```

Los mensajes se envían en **HTML** (título en negrita); el título y el detalle
del error se escapan para no romper el formato. Los fallos de Telegram (sin red,
token inválido) se registran pero **nunca** interrumpen la descarga/traducción.

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

### Páginas de la web

La web se organiza en varias páginas (navegación común: **Descargar · Biblioteca · Ayuda**):

- **`/`** — Descarga: formulario con URL, tomo, concurrencia y opciones, progreso en vivo y una franja de **novelas recientes** (portadas) que enlaza a la ficha de cada una.
- **`/biblioteca`** — Grid de solo portadas: toca una portada para abrir su ficha.
- **`/novela/{slug}`** — Ficha individual: portada grande, datos, progreso, acciones (**Traducir** en novelas no traducidas, Sync, Re-traducir, Tomos, Regenerar EPUBs) con su progreso en vivo y la lista de **EPUBs** generados (original y traducción).
- **`/ayuda`** — Guía rápida de qué hace cada acción, por si olvidas el detalle.

### Qué ofrece

- **Lanzar descarga**: URL, tomo (`50`/`100`), concurrencia, idioma de traducción y opciones (`--translate`, `--all`, `--translate-pending`, `--force`, `--playwright`), igual que el CLI.
- **Progreso en vivo** por WebSocket: fases de descarga, traducción y EPUB con barras y contadores.
- **Traducir** (botón **🌐 Traducir** en la ficha de novelas no traducidas): abre un **modal para elegir el idioma** (es, en, fr, de, it, pt, ru, ja, ko, zh) y lanza un job de **solo traducción** de los capítulos pendientes; si el idioma difiere del guardado, **re-traduce todo** sin volver a descargar.
- **Sincronizar novela** (botón **↻ Sync** en la ficha de la novela): obtiene nuevos capítulos de una novela ya descargada **sin re-pegar la URL**. El sync reusa la `source_url` guardada y el mismo mecanismo de la CLI (misma URL + `--resume` → descarga el siguiente tomo pendiente), y **hereda la traducción, el idioma y el tamaño de tomo** de la novela: si la novela se descargó traducida, los nuevos capítulos también se traducen y se regenera el EPUB traducido.
- **Re-traducir** (botón **📝 Re-traducir** en la ficha, solo en novelas ya traducidas): lanza un job de **solo traducción** (sin descargar ni tocar el TOC) que **traduce los capítulos pendientes** — faltantes y `translated/` vacíos corregidos — usando las opciones del manifest (`volume_size`, idioma). No sobrescribe lo ya traducido; si no hay pendientes no cambia nada. **Regenera siempre los EPUB traducidos** con las traducciones actuales y **limpia del disco los EPUBs huérfanos** (los que ya no están referenciados en el manifest, p. ej. tomos con rangos viejos).
- **Cambiar tamaño de tomo** (botón **📄 Tomos N** en la ficha): abre un modal con píldoras **50 · 100 · 150 · 200 · ALL** (marca el tamaño actual). Al elegir uno se habilita **Regenerar**, que reconstruye los EPUBs (original y traducido) con el nuevo tamaño sin descargar ni traducir; **ALL** genera un único EPUB. El tamaño se guarda en el manifest y lo heredan los próximos **Sync**/**Re-traducir**. El formulario de descarga acepta ahora 50/100/150/200.
- **Regenerar EPUBs** (botón **♻ Regenerar EPUBs** en la ficha): reconstruye los tomos (original y traducido) desde los capítulos en disco **sin cambiar el tamaño ni descargar**. Útil para aplicar mejoras del generador, como la página final **FIN** que cierra cada tomo. También limpia del disco los EPUBs huérfanos.
- **Biblioteca** (`/biblioteca`): grid de portadas de las novelas ya descargadas (`output/<slug>/`); cada portada abre su ficha.
- **Ficha de novela** (`/novela/{slug}`): portada, título/autor, badges (idioma + original / original), % de progreso, aviso de capítulos vacíos, acciones y la lista de **EPUBs** (original y traducción) para descargarlos directamente al dispositivo.
- **Guía de acciones** (`/ayuda`): resumen de qué hace cada acción.
- **Cancelar** un job en curso.
- **Notificaciones por Telegram** (opcional): con `NOVEL_TELEGRAM_BOT_TOKEN` y `NOVEL_TELEGRAM_CHAT_ID` en el `.env`, cada job avisa al terminar (resumen) y al fallar; ver [Notificaciones por Telegram](#notificaciones-por-telegram).
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