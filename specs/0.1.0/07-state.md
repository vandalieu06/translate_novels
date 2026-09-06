# 07 — Estado en disco y reanudación

## Layout de salida (por novela)

```
output/
└── <slug>/                       # ej: inner-voice-all-heroines-hear-my-inner-voice
    ├── .manifest.json            # estado/índice (fuente de verdad para reanudar)
    ├── cover.jpg                 # portada local (si el sitio la dio)
    ├── raw/                      # capítulos en idioma original
    │   ├── 0001.md
    │   ├── 0002.md
    │   └── ...
    ├── translated/               # capítulos traducidos a es (si --translate)
    │   ├── 0001.md
    │   └── ...
    ├── Novela.epub               # EPUB original (sin --volume-size)
    ├── Novela 1-50.epub          # o volúmenes
    ├── Novela 51-100.epub
    ├── Novela (ES).epub          # traducido (si --translate)
    └── Novela 1-50 (ES).epub     # o volúmenes traducidos
```

## Formato de capítulo en disco

- `raw/<NNNN>.md`: texto plano, párrafos separados por `\n\n`. Primera línea opcional `# <título>`.
- `translated/<NNNN>.md`: idéntico formato, contenido traducido.
- Al reanudar, `core` parsea estos archivos para reconstruir `Chapter.paragraphs` (título del manifest o de la primera línea `#`).

## Manifest (`.manifest.json`)

Definido en `specs/02-models.md`. Reglas de reanudación:

1. Si `resume` y existe `.manifest.json` y `!force`:
   - `chapters_total == chapters_downloaded` → se salta la descarga.
   - `translated == True` y `chapters_translated == chapters_total` → se salta la traducción.
   - `epub_original` / `epub_translated` presentes y archivos existentes → se salta la generación de EPUB.
2. Si `force` → se borra el estado y se re-descarga (nunca borrar archivos en `raw/` re-utilizables: `force` re-descarga solo los que falten a menos que `--force` explícito re-escriba todo).

> Nota de diseño: la fuente de verdad de "ya descargado" es la **existencia del archivo** en disco; el manifest es índice/caché de metadatos. Si un archivo falta pero el manifest dice que existe, se re-descarga ese capítulo.

## Escritura

- `state.py` provee `Manifest.load(slug_dir) -> Manifest | None` y `save()`.
- Se escribe al final de cada fase (descarga, traducción, EPUB) para que un corte a mitad permita reanudar.
- `updated_at` se actualiza en cada escritura.

## Reanudación sin SQLite

- Sin base de datos: nada de Peewee, migraciones, ni tablas. Todo el estado es el manifest + archivos.
- Ventaja: portable, editable a mano, sin dependencias de persistencia; el CLI se puede mover a otra máquina copiando la carpeta.