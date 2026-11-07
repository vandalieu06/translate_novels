---
code: "01"
title: "TOC de NovelPhoenix: numero y titulo desde el markup estructurado"
project: "novel_cli"
status: completed
version: "0.3.1"
date: 2026-11-07
tags: [spec, sdd, scraper, novelphoenix]
affected_files:
  - src/novel_cli/core/scraper/sites/novelfire.py
  - src/novel_cli/core/utils/text.py
  - src/novel_cli/core/models/toc.py
  - tests/test_novelfire.py
  - tests/fixtures/novelphoenix_toc_2026.html
---

# 01 — TOC de NovelPhoenix: numero y titulo desde el markup estructurado

## Purpose

Que el crawler de `novelphoenix.com` extraiga el **numero canonico** y el **titulo limpio**
de cada capitulo a partir del markup estructurado actual del sitio, sin depender del atributo
`title` (que el sitio ya no emite) y sin concatenar el badge `Ch. N` ni la fecha relativa
`<time>`.

## Context

El listado actual de NovelPhoenix renderiza cada capitulo asi:

```html
<a href="/novel/<slug>/chapter-1">
  <span class="chapter-no">Ch. 1</span>
  <strong class="chapter-title">1. Woman's World</strong>
  <time class="chapter-update">3 years ago</time>
</a>
```

`NovelfireAdapter.parse_toc` hace `text = anchor_title(anchor)` y
`num = guess_chapter_num(text, href, fallback)`:

- `anchor_title()` (`core/utils/text.py:18-23`) prioriza `anchor.get("title")`; el sitio ya **no**
  publica ese atributo, asi que cae a `anchor.text_content()`, que concatena
  `"Ch. 1" + "1. Woman's World" + "3 years ago"`.
- `guess_chapter_num()` (`core/utils/text.py:26-34`) hace `search` del regex
  `(?:chapter|ch\.?…)(\d+)` sobre ese texto; el `href` solo se usa si el texto no matchea.

Evidencia en la novela `surviving-in-womans-world-as-a-novel-villain` (2026-11-07):

| URL | texto concatenado | num actual | num correcto |
| --- | --- | --- | --- |
| `chapter-1` | `Ch. 11. Woman's World3 years ago` | 11 | 1 |
| `chapter-10` | `Ch. 1010. Dumbass Rose3 years ago` | 1010 | 10 |
| `chapter-100` | `Ch. 100100. Xiao Bai3 years ago` | 100100 | 100 |
| `chapter-513` | `Ch. 513491. Heroines…6 hours ago` | 513491 | 513 |

Consecuencias: orden del TOC roto (se ordena por `num`), ficheros `raw/NNNN.md` con numeros
absurdos, colision `chapter-8`/`chapter-88` (ambos `num=88`) que pierde un capitulo, rangos de
EPUB (`11-3333`) sin sentido y titulos con `"3 years ago"`.

Esto es una **regresion del sitio**, no del repo: el commit `be619e2` introdujo el soporte de
`title` precisamente para limpiar titulos; el ultimo cambio del scraper fue `41c2de3`
(solo paginacion). Afecta a cualquier novela de NovelPhoenix crawleada con el markup actual.

## Proposed change

1. **`core/utils/text.py`** — helper de numero canonico:

   ```python
   def chapter_num_from_href(href: str) -> int | None:
       """Numero canonico del capitulo a partir del href (/chapter-123)."""
       match = _HREF_CHAPTER.search(href)
       return int(match.group(1)) if match else None
   ```

   Refactorizar `guess_chapter_num()` para reutilizarlo en el fallback del `href`.

2. **`core/scraper/sites/novelfire.py`** — leer el título estructurado y priorizar el `href`
   para el numero:

   ```python
   SEL_CHAPTER_TITLE = ".chapter-title"

   # en parse_toc(), dentro del bucle:
   text = _chapter_title(anchor)          # antes: anchor_title(anchor)
   if not text:
       continue
   url = urljoin(base_url, href)
   num = chapter_num_from_href(href)      # el href manda
   if num is None:
       num = guess_chapter_num(text, href, fallback)

   def _chapter_title(anchor) -> str:
       nodes = anchor.cssselect(SEL_CHAPTER_TITLE)
       if nodes:
           return clean_text(nodes[0].text_content())
       return anchor_title(anchor)        # compatibilidad novel fire.net / markup viejo
   ```

3. **`core/models/toc.py`** — invalidar caches construidas con el parser viejo:

   ```python
   class TocCache(BaseModel):
       CURRENT_VERSION: ClassVar[int] = 2  # antes 1
       version: int = CURRENT_VERSION

       @classmethod
       def load(cls, slug_dir):
           data = json.loads(path.read_text(encoding="utf-8"))
           if int(data.get("version", 1)) < cls.CURRENT_VERSION:
               return None                  # fuerza re-crawl
           return cls.model_validate(data)
   ```

   Sin este bump, un `.toc.json` con `num` corruptos seguiria vigente hasta 6 h
   (`NOVEL_TOC_TTL_HOURS`) y el fix no se aplicaria en `resume`.

## Technical decision

- **El `href` es la fuente canonica del numero.** El propio sitio titula mal algunos capitulos
  (el 513 aparece como `491.`); el path `/chapter-513` y el badge `Ch. 513` sí son fiables.
- **`.chapter-title` es el titulo limpio**: excluye badge y `<time>`, y existe tanto en el markup
  actual como en el de las novelas cacheadas en septiembre.
- Se mantiene `anchor_title()` como **fallback** para `novelfire.net` y markups antiguos: el
  cambio no altera el comportamiento cuando sí hay `title` o cuando no existe `.chapter-title`.
- No se toca `parse_chapter` ni `next_page` (la paginacion ya funciona; ver spec 0.3.0/10).
- **Migracion de estado**: este spec no renumera `raw/` existente. Una novela descargada con el
  parser viejo debe re-descargarse desde cero (ver spec 03 y el informe de limpieza). El bump de
  `.toc.json` evita reutilizar el indice corrupto, pero no renombra ficheros.
- Riesgo asumido: si el sitio vuelve a cambiar el markup, `_chapter_title` cae a `anchor_title` y
  el problema reaparece; el fixture nuevo debe actualizarse cuando se detecte.

## Affected files

- `src/novel_cli/core/scraper/sites/novelfire.py` — `SEL_CHAPTER_TITLE`, `_chapter_title()`,
  `parse_toc()`.
- `src/novel_cli/core/utils/text.py` — `chapter_num_from_href()`, `guess_chapter_num()`.
- `src/novel_cli/core/models/toc.py` — version de cache y validacion en `load()`.
- `tests/fixtures/novelphoenix_toc_2026.html` — nuevo fixture con el markup real
  (`chapter-no` / `chapter-title` / `time`).
- `tests/test_novelfire.py` — casos nuevos; conservar los de paginacion.

## Tests

- `parse_toc` con el fixture nuevo:
  - `chapter-1` → `(1, "1. Woman's World")`.
  - `chapter-26` → `(26, "Chapter 26.Hypocrite Protaganist")` (sin badge ni fecha).
  - `chapter-513` → `(513, "491. Heroines Unique Exclusive Aura (R-)")`.
  - ningun titulo termina en `… ago`.
- El `href` gana a un numero contradictorio en el titulo (caso 513).
- Un listado de 100 items genera 100 `num` unicos.
- `crawl_toc` con 2 paginas de rango sigue devolviendo `listing_pages = [primera, ultima]`.
- `TocCache.load` descarta un JSON con `version: 1` y acepta `version: 2`.
- Los tests de `novelphoenix_toc.html` (title attr) y de `novelfire.net` siguen pasando.

## Acceptance criteria

- [ ] `parse_toc` del HTML real de la pagina 1 devuelve `num` 1..100 y titulos sin badge ni fecha.
- [ ] Los 513 capitulos del listado completo tienen `num` unicos 1..513.
- [ ] `chapter-8` y `chapter-88` dejan de colisionar.
- [ ] Un `.toc.json` viejo (`version: 1`) se ignora y se re-crawlea.
- [ ] No cambian los tests de paginacion ni el comportamiento de `novelfire.net`.
- [ ] `uv run pytest -q` y `uv run ruff check .` en verde.
