# 00 — Overview

## Propósito

CLI independiente (Python) para **descargar web novels y convertirlas en EPUB**, con traducción opcional a español vía la capa gratuita de Google Translate. Reutiliza el proyecto existente `translate_novels`, que abandonó el uso de Ollama (LLM local calentaba el equipo), reemplazándolo por el endpoint gratuito de Google Translate — el mismo enfoque que Readest usa en `apps/readest-app/src/services/translators/providers/google.ts`.

## Objetivos (desired outcomes)

1. Scraper de web novels con Playwright (fallback) que extraiga: título de la novela, portada, autor, y la lista de capítulos con sus rangos (ej: `Novela 1-100`).
2. Generar EPUB **en el idioma original** conservando el formato original (párrafos, título, portada, TOC).
3. **Ruta por defecto** para las novelas (directorio de salida configurable).
4. Opción de **traducir a español** la novela generada con Google Translate (endpoint gratuito, sin clave).
5. Opción de **empaquetar en volúmenes de 50 o 100 capítulos** (ej: `Novela 1-50.epub`, `Novela 51-100.epub`).
6. Separación limpia entre **`core/`** (lógica de dominio, sin dependencias de CLI) y **`cli/`** (typer + config + progreso).

## No-objetivos (fuera de alcance v1)

- UI/web app, sync, anotaciones (eso es dominio de Readest).
- Paginación compleja / sitios con anti-bot JS-challenge avanzado (Cloudflare Turnstile real). Solo fallback Playwright.
- Traducción con LLMs locales (Ollama) como backend por defecto — puede existir como backend opcional pero no es el foco.
- Soporte de EPUB de terceros (solo generamos, no leemos ni editamos EPUBs existentes).
- Multi-idioma arbitrario: v1 traduce a **español** desde auto-detección de idioma.

## Relación con Readest

Lecciones adoptadas directamente del código de Readest:

| Concepto Readest | Cómo lo adoptamos |
|---|---|
| `googleProvider` (endpoint `translate_a/single` con `client=gtx`) | Cliente delgado propio de traducción, sin depender de `googletrans`. |
| `novelImport.ts`: pacer (~300ms) + retry con backoff + cool-down ante 429 | `core/scraper/fetcher.py` y `core/services/download.py`: pacing + retry. |
| Heurística de TOC (`chapterList.ts`) | Selectores por sitio + heurística genérica de enlaces de capítulo. |
| `buildEpub` con múltiples capítulos y portada | `ebooklib` con un capítulo por XHTML, portada + TOC. |
| Inyección de `fetchPage` (fetcher intercambiable) | Interfaz `Fetcher` (httpx-first, Playwright fallback). |
| `stubTranslation`/i18n | No aplica (CLI); usamos idioma de la novela tal cual. |

## Decisiones tomadas (confirmadas)

- **Traducción**: cliente directo al endpoint gratuito de Google Translate (como Readest). Nada de `googletrans` ni Ollama por defecto.
- **Fetch**: `httpx` primero; Playwright solo como fallback cuando el sitio exige JS.
- **Persistencia**: sin SQLite. Manifest JSON por novela para estado/reanudación.
- **Volúmenes**: `Novela 1-50.epub`, `Novela 51-100.epub`; cada volumen reutiliza la misma portada de la webnovel.
- **CLI**: comando único con flags (flujo completo scrape → epub → translate → pack).
- **Framework CLI**: `typer`.
- **Concurrencia**: async `httpx` con pool + pacer (~300ms) para capítulos.
- **Estado en disco**: capítulos en archivos (`.xhtml`/`.md`) + `.manifest.json` con metadatos y estado.

## Resumen del flujo (comando único)

```
URL de la novela
   │
   ├─ 1. Resolver adaptador de sitio (por dominio)
   ├─ 2. Obtener TOC: título, portada, autor, lista de capítulos (httpx/Playwright)
   ├─ 3. Descargar capítulos (async pool + pacing) → output/<slug>/raw/
   ├─ 4. Generar EPUB original (ebooklib, volúmenes opcionales) → output/<slug>/
   ├─ 5. [--translate] Traducir a es → output/<slug>/translated/
   │      y generar EPUB traducido (volúmenes opcionales)
   └─ 6. Escribir .manifest.json (estado/reenable)
```