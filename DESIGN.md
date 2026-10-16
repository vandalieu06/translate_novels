# DESIGN.md — novel-cli web

Design system de la web de `novel-cli`. Es una **herramienta personal**: prima
ser directa, densa y fácil de usar por encima del ornamento. Sustituye al
anterior spec "MOSH" (una landing de marketing) por un sistema propio, compacto
y con lenguaje inspirado en shadcn, escrito a mano en CSS vanilla (sin build).

> Referencia técnica: `specs/0.3.0/05-design-system.md`. Este documento es la
> fuente viva del lenguaje visual.

## Principios

- **Herramienta, no folleto**: sin hero de marketing, sin relleno; cada bloque
  gana su espacio con contenido real.
- **Una decisión, no un default**: un solo accent, una sola fuente, un set de
  iconos. Nada decorativo que no comunique.
- **Denso pero legible**: UI a 14px, contadores tabulares, foco visible.

## Tokens

Variables CSS en `static/css/tokens.css`. El tema se activa con
`<html data-theme="auto|light|dark">`; `auto` sigue `prefers-color-scheme`.

| Rol | Claro | Oscuro |
|---|---|---|
| `--bg` | `#ffffff` | `#09090b` |
| `--fg` | `#18181b` | `#fafafa` |
| `--card` | `#ffffff` | `#121215` |
| `--muted` | `#f4f4f5` | `#1f1f23` |
| `--muted-fg` | `#71717a` | `#a1a1aa` |
| `--border` / `--input` | `#e4e4e7` | `#27272a` |
| `--primary` / `--primary-fg` | `#18181b` / `#fafafa` | `#fafafa` / `#18181b` |
| `--accent` / `--accent-fg` | `#e0575f` / `#ffffff` | `#f2777e` / `#18181b` |
| `--ring` | `--accent` | `--accent` |
| `--destructive` | `#dc2626` | `#ef4444` |
| `--success` | `#16a34a` | `#4ade80` |
| `--warning` | `#d97706` | `#fbbf24` |

- **Radios**: `--radius` 6px (controles), `--radius-card` 8px, `--radius-overlay` 12px.
- **Tipo**: `--font` = stack `system-ui`; escala `12 / 13 / 14 / 16 / 20 / 28`.
  `font-variant-numeric: tabular-nums` en contadores.
- **Layout**: contenedor `1120px`, header `56px`.

## Reglas (no negociables)

- Sin **gradientes**.
- **Sin sombras en reposo**; solo `--shadow-overlay`/`--shadow-popover` en
  dialog, sheet, popover y toast.
- Sin **emojis** como iconos → SVG inline (`icon(name)` de `theme.js`).
- Sin "eyebrows"/kickers decorativos, sin labels uppercase con tracking, sin
  "glass", sin numeración 01/02.
- Un **único accent**; el estado usa `--destructive/--success/--warning`.
- Titulares de **≤2 líneas**; sentence case.

## Componentes

CSS en `static/css/components.css`. Nombres de clase estables, reutilizables por
plantillas y JS.

| Componente | Clases / notas |
|---|---|
| Button | `.btn` + `.btn-primary` / `.btn-secondary` / `.btn-ghost` / `.btn-destructive`; `.btn-lg`, `.btn-icon`, estado `.loading` (con `.spinner`). |
| Campos | `.field`, `.label`, `input`/`select`/`textarea`, `.field-hint`. |
| Checkbox group | `.checkbox-group` (chips seleccionables). |
| Switch | `.switch`. |
| Segmented | `.segmented` (botones con `aria-selected`). |
| Badge | `.badge` + `-info` / `-success` / `-warning` / `-danger` / `-neutral`. |
| Chip / Pill | `.chip`, `.pill` (`.active`), `.pill-group`. |
| Alert | `.alert` + `-info` / `-success` / `-warning` / `-error`. |
| Card | `.card`. |
| Dialog / Sheet | `.modal-overlay` + `.modal` (`.modal-head`, `.modal-desc`, `.modal-actions`); en móvil pasa a sheet inferior. |
| Toast | `#toast` + `.show`, `.toast-info/success/error`. |
| Progress | `.bar`/`.bar-fill` (alias `.mini-bar`/`.mini-fill`). |
| Empty state | `.empty`, `.empty-icon`, `.empty-actions`. |
| Popover / Menu | `.popover`, `.menu-item`, `.menu-label`. |
| Tooltip / ayuda inline | `.help-dot`. |
| Skeleton | `.skeleton`. |

## Estructura de ficheros

```
static/css/tokens.css      # variables, tema, reset, base
static/css/components.css  # primitivas
static/css/app.css         # orquestador (importa los anteriores) + shell + páginas
static/js/theme.js         # tema (getTheme/setTheme) + icon(name)
```

El panel de progreso del job y el shell se comparten entre páginas (ver specs
`0.3.0/06`). El tema se guarda en `localStorage["novel_web_theme"]`.
