---
code: "04"
title: "Backend de traducción con LLM local (Ollama + TranslateGemma)"
project: "novel_cli"
status: completed
version: "0.3.0"
date: 2026-10-16
tags: [spec, sdd]
affected_files:
  - src/novel_cli/core/config.py
  - src/novel_cli/core/services/translate.py
  - src/novel_cli/core/services/pipeline.py
  - src/novel_cli/web/routes.py
  - .env.example
  - docs/arquitectura.md
  - docs/uso.md
  - docs/features.md
  - README.md
  - tests/test_translate.py
  - tests/test_config.py
---

# 04 — Backend de traducción con LLM local (Ollama + TranslateGemma)

## Propósito

Añadir un backend de traducción `ollama` que traduzca los capítulos con un LLM
local de traducción (default `translategemma:4b`) usando la API HTTP de Ollama.
El objetivo es mejorar la **fluidez y coherencia** del español frente a los
backends NMT (Google/LibreTranslate), sin añadir dependencias Python nuevas.

## Contexto / Problema

- Google (endpoint gratuito) y LibreTranslate (Argos/OPUS-MT) son NMT: traducen
  correcto a nivel léxico pero con redacción a veces rígida y poca adaptación de
  estilo. Cambiar de NMT (NLLB, EuroNano, …) no arregla la redacción porque son
  la misma familia.
- Las novelas del proyecto se descargan **en inglés** (los sitios ya tradujeron
  del chino/coreano), así que el par real es `en → es`.
- Ya existe un `OllamaTranslator` stub sin implementar (`translate.py`), y el
  entorno tiene Ollama con `translategemma:4b` (3.3 GB, Q4_K_M) instalado y una
  RTX 3060 de 12 GB.

## Cambio propuesto (antes → después)

- **Antes**: `NOVEL_TRANSLATE_BACKEND` acepta `google` (default) y `libre`.
  `OllamaTranslator.translate_text` lanza `NotImplementedError`.
- **Después**: `NOVEL_TRANSLATE_BACKEND=ollama` activa el backend LLM. Se
  construye con la URL/modelo por env, usa el prompt oficial de TranslateGemma,
  mantiene el ritmo con concurrencia 1 y traduce línea a línea (con `WARNING`)
  si el
  LLM no respeta la estructura de párrafos.

## Decisión técnica

- **Sin dependencias nuevas**: se habla con Ollama por `httpx`
  (`POST {base_url}/api/chat`, `stream=false`). El `Translator` Protocol no
  cambia.
- **Prompt oficial** (guía de Ollama): una sola user message con el texto
  `You are a professional {SRC} ({src}) to {TGT} ({tgt}) translator. …` y **dos
  líneas en blanco** antes del texto a traducir.
- **Idioma origen**: `translate_chapters` recibe `source` desde
  `manifest.language_code` (suele ser `"auto"`); el backend interpreta `"auto"`
  como su default configurable (`NOVEL_OLLAMA_SOURCE_LANG`, default `en`).
- **Estructura de párrafos**: el spike (capítulo real, `translategemma:4b`)
  mostró que el modelo devuelve **una línea por párrafo** separadas por `\n`, de
  modo que el reensamblado 1:1 existente de `translate_paragraphs` funciona sin
  cambios. Si el recuento de líneas no cuadra:
  1. se reintenta una vez con la instrucción extra *"Preserve the paragraph
     breaks …"*;
  2. si sigue sin cuadrar, se traduce **línea a línea** (una llamada por
     párrafo) para garantizar exactamente un párrafo de salida por párrafo de
     entrada, registrando un `WARNING`, **sin fallar el job**. Si una línea no
     produce traducción, se conserva el texto original (nunca un párrafo vacío
     en el EPUB).
- **Timeout**: `POST /api/chat` usa un timeout propio largo
  (`NOVEL_OLLAMA_TIMEOUT`, default 300 s); la primera llamada en frío del spike
  tardó ~37 s y las siguientes ~4–9 s.
- **Rendimiento**: `keep_alive` (default `10m`) mantiene el modelo cargado entre
  chunks. Con `translategemma:4b` en la RTX 3060, 573 palabras tardaron ~9 s
  (≈63 palabras/s). Concurrencia **1** (una GPU) y pacer 0.
- **Chunking**: `max_words_per_chunk` para ollama = 400 (mismo default global);
  el spike validó alineación perfecta a 249 y 573 palabras.

## Variables de entorno

| Variable | Uso | Default |
|---|---|---|
| `NOVEL_OLLAMA_URL` | Base URL de Ollama | `http://localhost:11434` |
| `NOVEL_OLLAMA_MODEL` | Modelo a usar | `translategemma:4b` |
| `NOVEL_OLLAMA_SOURCE_LANG` | Idioma origen cuando llega `auto` | `en` |
| `NOVEL_OLLAMA_TIMEOUT` | Timeout del POST en segundos | `300` |
| `NOVEL_OLLAMA_MAX_WORDS_PER_CHUNK` | Palabras por chunk | `400` |
| `NOVEL_OLLAMA_KEEP_ALIVE` | Tiempo que Ollama mantiene el modelo | `10m` |

## Archivos afectados

- `src/novel_cli/core/config.py` — backend `ollama`, constantes `OLLAMA_*`,
  concurrencia 1, mapa de nombres de idioma en inglés.
- `src/novel_cli/core/services/translate.py` — `OllamaTranslator` real,
  `build_default_translator()`, hilo de `source` en
  `translate_paragraphs/_chapter/_chapters`.
- `src/novel_cli/core/services/pipeline.py` — pasa
  `source=manifest.language_code` a `translate_chapters`.
- `.env.example` — documenta las variables nuevas.
- `src/novel_cli/web/routes.py` — `/api/config` expone `ollama_model`.
- `docs/arquitectura.md`, `docs/uso.md`, `docs/features.md`, `README.md`.
- `tests/test_translate.py`, `tests/test_config.py`.

## Tests

- `respx` sobre `POST /api/chat`: prompt exacto (incluye las dos líneas en
  blanco), parseo de `message.content`, texto vacío sin llamada, retry de red,
  `source` derivado de `manifest.language_code`/`auto`, selección de backend
  `ollama` y concurrencia forzada a 1. Sin red.
- Reintento + fallback: si la salida tiene un nº de líneas distinto al de
  párrafos, se reintenta con el prompt reforzado y, si persiste, se traduce
  línea a línea (sin párrafos vacíos) registrando un warning.

## Criterios de aceptación

- `NOVEL_TRANSLATE_BACKEND=ollama` traduce un capítulo real con
  `translategemma:4b` y el EPUB traducido se genera con la estructura 1:1.
- Google y LibreTranslate conservan su comportamiento actual (default sin
  cambios; `source="auto"`).
- `uv run pytest -q` y `uv run ruff check .` pasan sin red.
- El fallo de formato del LLM nunca aborta el job ni deja párrafos vacíos
  (reintento + traducción línea a línea con warning).
