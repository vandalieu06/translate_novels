"use strict";

/* ==========================================================================
   theme.js — Tema claro/oscuro y set de iconos SVG (spec 0.3.0/05)
   ========================================================================== */

const THEME_KEY = "novel_web_theme";
const THEMES = ["auto", "light", "dark"];

function getTheme() {
  try {
    return localStorage.getItem(THEME_KEY) || "auto";
  } catch (_) {
    return "auto";
  }
}

function applyTheme(mode) {
  const value = THEMES.includes(mode) ? mode : "auto";
  document.documentElement.dataset.theme = value;
  return value;
}

function setTheme(mode) {
  const value = applyTheme(mode);
  try {
    localStorage.setItem(THEME_KEY, value);
  } catch (_) {}
  return value;
}

/* Aplica el tema guardado lo antes posible (idempotente con el bootstrap). */
applyTheme(getTheme());

/* --------------------------------------------------------------------------
   Iconos SVG inline (un solo trazo). Uso: icon("globe") o icon("globe", 'class="x"')
   -------------------------------------------------------------------------- */
const ICONS = {
  download: '<path d="M12 3v12m0 0l-4-4m4 4l4-4M5 21h14"/>',
  upload: '<path d="M12 21V9m0 0l-4 4m4-4l4 4M5 3h14"/>',
  globe:
    '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 3 2.5 15 0 18M12 3c-2.5 3-2.5 15 0 18"/>',
  translate:
    '<path d="M4 5h8M8 3v2c0 4-2 7-5 9"/><path d="M5 9c2 3 5 5 8 5"/><path d="M13 20l4-9 4 9M14.5 17h5"/>',
  "file-text":
    '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
  refresh: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  rebuild: '<path d="M7 19H5a2 2 0 0 1-1.7-3l2-3.2"/><path d="M9 6.5l1.6-2.7a1 1 0 0 1 1.7 0L14 6.5"/><path d="M9 6.5l-2.3 2.3a1 1 0 0 0 0 1.4L9 12.5"/><path d="M17 6.5h2a2 2 0 0 1 1.7 3l-.7 1.2"/><path d="M15 17.5l2.3-2.3a1 1 0 0 0 0-1.4L15 11.5"/>',
  pencil: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  link: '<path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1"/><path d="M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1"/>',
  external:
    '<path d="M14 4h6v6M20 4l-9 9M18 14v4a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4"/>',
  warning: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
  alert: '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>',
  "check-circle": '<circle cx="12" cy="12" r="9"/><path d="M8.5 12.5l2.5 2.5 4.5-5"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9a2.5 2.5 0 1 1 3.6 2.3c-.7.4-1.1.9-1.1 1.7v.4M12 17h.01"/>',
  book: '<path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19a2 2 0 0 1 2-2h13"/>',
  inbox:
    '<path d="M4 13l2-7h12l2 7v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z"/><path d="M4 13h5l1 2h4l1-2h5"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  check: '<path d="M5 12l5 5L19 7"/>',
  "chevron-down": '<path d="M6 9l6 6 6-6"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  filter: '<path d="M3 5h18l-7 8v6l-4-2v-4z"/>',
  sort: '<path d="M7 4v16m0 0l-3-3m3 3l3-3M17 20V4m0 0l-3 3m3-3l3 3"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  settings:
    '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a7 7 0 1 0 10.5 10.5z"/>',
  monitor: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  play: '<path d="M7 4l12 8-12 8z"/>',
  trash: '<path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13"/>',
};

function icon(name, extra = "") {
  const path = ICONS[name];
  if (!path) return "";
  return (
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
    `stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" ` +
    `aria-hidden="true"${extra ? " " + extra : ""}>${path}</svg>`
  );
}

window.NOVEL_THEME = { getTheme, setTheme, applyTheme, THEMES, THEME_KEY };
window.icon = icon;
