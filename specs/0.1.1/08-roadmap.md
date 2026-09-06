# 08 — Roadmap (0.1.1 → próximos)

Estado: en curso. Próximos cambios planeados por el usuario (a documentar en
su spec antes de implementar, según el workflow specs-driven).

## Candidatos (pendientes de spec)

- **CI GitHub Actions**: `uv sync --dev`, `ruff`, `pytest -q` (sin integración) en cada push/PR.
- **Validar el adaptador genérico en más sitios** (Royal Road, biquge, Scribble Hub) con fixtures propios.
- **`--translate-title`**: traducir también el título/metadata (hoy se conserva el original).
- **Descarga de imágenes dentro de los capítulos** (hoy el EPUB es autocontenido sin imágenes internas).
- **Control de rango**: `--start <num> --end <num>` para bajar solo un tramo.
- **Multi-idioma destino** (`--target <lang>`) en vez de fijar `es`.
- **`OllamaTranslator`** real como backend opcional.
- **Perfil de prioridad/cola de novelas** (descarga programada de varias novelas).

## Regla

Cada item se convierte en un spec en la versión en curso (`specs/<version>/NN-<tema>.md`)
siguiendo el formato de `00-changelog.md` **antes** de escribir código.