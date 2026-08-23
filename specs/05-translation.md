# 05 — Traducción

## Backend por defecto: endpoint gratuito de Google Translate

Cliente delgado propio (como Readest `googleProvider`), **sin** depender de `googletrans` (no oficial, frágil) ni de Ollama (calentaba el equipo).

### Endpoint

```
GET https://translate.googleapis.com/translate_a/single
    ?client=gtx&dt=t&sl=<origen|auto>&tl=<destino>&q=<texto>
```

- `sl` = idioma origen (`auto` por defecto) → Readest usa `normalizeToShortLang`. Nosotros aceptamos `auto`.
- `tl` = idioma destino (v1: `es`).
- Respuesta JSON: `data[0]` es una lista de segmentos `[texto, ...]`; concatenar los `segment[0]`.
- Sin clave, sin token. Es la "capa gratuita" que usa Readest.

### Interfaz intercambiable (`core/services/translate.py`)

```python
class Translator(Protocol):
    def translate_text(self, text: str, *, source: str = "auto", target: str = "es") -> str: ...

class GoogleFreeTranslator:
    """Cliente del endpoint translate_a/single con httpx + retry/pacing."""
    ...

class OllamaTranslator:   # opcional / futuro (no default)
    ...
```

- `pipeline` recibe un `Translator` por inyección. El CLI por defecto usa `GoogleFreeTranslator`; el default está en `core/config.py` y puede sobrescribirse por flag/env.

### Traducción por párrafos y reensamblado

- El capítulo original está en `paragraphs` (idioma original).
- Se traduce **párrafo a párrafo** para conservar estructura → cada `<p>` traducido ocupa la misma posición.
- Texto vacío/whitespace se deja tal cual (sin llamar al endpoint).
- Se reensambla `translated_paragraphs` → mismo número de párrafos → EPUB traducido idéntico en estructura al original.

## Chunking (reutilizar `split_text_by_words` del proyecto viejo)

- El endpoint tiene límites prácticos de longitud por request (y rate limits agresivos).
- Se agrupan varios párrafos en un chunk sin exceder `max_words_per_chunk` (default 400 palabras, configurable) — ya implementado en `core/translate.py` del viejo `Translate.split_text_by_words`.
- Tras traducir el chunk, se re-dividen las líneas por `\n` para reconstruir párrafos 1:1.

## Pacing + retry + cache (lección de Readest)

- **Pacer** para no quemar el endpoint: mínimo ~250-500ms entre requests de traducción (constante configurable).
- **Retry con backoff** ante 429/5xx, honor `Retry-After` (tope 30s). El mismo `with_retry` de `fetcher.py` se reutiliza.
- **Cache en disco**: cada capítulo traducido se guarda en `output/<slug>/translated/<NNNN>.md`. Si el archivo existe y el manifest lo marca, se salta (reanudación).

## Conservación de contenido

- **Sin markdown**: el texto es prosa. No se aplica sanitización HTML a la salida (es texto plano; `ebooklib` escapa al emitir XHTML).
- No se traducen: títulos de capítulo se traducen (van en `<h1>`); la metadata (título de novela/portada) se deja en el idioma original salvo que se indique `--translate-title` (fuera de alcance v1).

## Funciones del servicio

```python
def translate_chapter(
    chapter: Chapter,
    translator: Translator,
    *,
    target: str = "es",
    max_words_per_chunk: int = 400,
) -> Chapter:
    """Devuelve un Chapter con paragraphs ya traducidos (mismo num/título/url)."""

def translate_cover_metadata(...) -> ...  # opcional, fuera de alcance v1
```

- `Chapter` traducido conserva `num`, `title` (título original si no se traduce), `url`.
- `pipeline` guarda `translated/<NNNN>.md` con el contenido traducido y actualiza `manifest.chapters_translated`.