"use strict";

/* ==========================================================================
   common.js — estado, API, shell (ajustes/tema), helpers compartidos
   spec 0.3.0/06
   ========================================================================== */

const state = {
  token: localStorage.getItem("novel_web_token") || "",
  currentJobId: null,
  socket: null,
  config: { auth_required: false, default_volume_size: 50, default_concurrency: 4 },
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

let configPromise = null;

function authHeader() {
  return state.token ? { "X-Auth-Token": state.token } : {};
}

async function api(path, options = {}) {
  const headers = { ...authHeader(), ...(options.headers || {}) };
  if (
    options.body &&
    typeof options.body !== "string" &&
    !(options.body instanceof FormData)
  ) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  const res = await fetch(path, { ...options, headers });
  if (res.status === 401) {
    showToast("Token requerido o inválido", "error");
    openSettings();
    throw new Error("unauthorized");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch (_) {}
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

function showToast(msg, type = "info") {
  const el = $("#toast");
  if (!el) return;
  el.textContent = msg;
  el.className = "show toast-" + type;
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => el.classList.remove("show"), 3200);
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

/* --------------------------------------------------------------------------
   Iconos declarativos: <span data-icon="globe"></span>
   -------------------------------------------------------------------------- */
function hydrateIcons(root = document) {
  $$("[data-icon]", root).forEach((el) => {
    if (el.dataset.iconDone) return;
    el.innerHTML = icon(el.dataset.icon);
    el.dataset.iconDone = "1";
  });
}

/* --------------------------------------------------------------------------
   Config del servidor
   -------------------------------------------------------------------------- */
async function loadConfig() {
  if (!configPromise) {
    configPromise = (async () => {
      try {
        state.config = await api("/api/config");
      } catch (_) {}
      if (state.config.auth_required && !state.token) openSettings();
      renderBackend();
      return state.config;
    })();
  }
  return configPromise;
}

function renderBackend() {
  const pill = $("#backend-pill");
  if (!pill) return;
  const backend = state.config.translate_backend;
  if (backend === "libre") {
    pill.textContent = "Traducción · LibreTranslate";
  } else if (backend === "ollama") {
    pill.textContent = `Traducción · ${state.config.ollama_model || "Ollama"}`;
  } else {
    pill.textContent = "Traducción · Google";
  }
  pill.title = "Backend de traducción activo";
  pill.hidden = false;
}

function setupNavActive() {
  const page = document.body.dataset.page;
  const link = $(`#main-nav a[data-nav="${page}"]`);
  if (link) link.classList.add("active");
}

/* --------------------------------------------------------------------------
   Portadas y utilidades de novela
   -------------------------------------------------------------------------- */
function coverMarkup(n) {
  return n.cover
    ? `<img class="cover" src="${n.cover}" alt="" loading="lazy">`
    : `<div class="cover placeholder">${icon("book")}</div>`;
}

function coverCard(n) {
  const pct =
    n.chapters_total > 0
      ? Math.round((n.chapters_downloaded / n.chapters_total) * 100)
      : 0;
  const emptyNums = (n.chapters_empty_nums || []).slice(0, 20);
  const emptyWarning =
    n.chapters_empty > 0
      ? `<span class="badge badge-warning cover-badge" title="${escapeHtml(
          emptyNums.join(", "),
        )}">${icon("warning")}${n.chapters_empty}</span>`
      : "";
  return `
    <a class="cover-card" href="/novela/${encodeURIComponent(n.slug)}">
      <div class="cover-frame">
        ${coverMarkup(n)}
        ${n.source_pdf ? `<span class="badge badge-info cover-badge cover-badge-pdf">PDF</span>` : ""}
        ${emptyWarning}
        ${n.translated ? `<span class="badge badge-success cover-badge cover-badge-translated">${(n.translated_language || "es").toUpperCase()}</span>` : ""}
        <span class="cover-pct">${pct}%</span>
      </div>
      <div class="cover-title">${escapeHtml(n.title)}</div>
      ${n.author ? `<div class="cover-author">${escapeHtml(n.author)}</div>` : ""}
    </a>`;
}

function languageLabel(code) {
  if (!code) return "";
  const langs = (state.config && state.config.translate_languages) || {};
  return langs[code] || code.toUpperCase();
}

function populateLanguageSelect(select) {
  if (!select) return;
  const langs = (state.config && state.config.translate_languages) || {};
  select.innerHTML = Object.entries(langs)
    .map(([code, label]) => `<option value="${code}">${label}</option>`)
    .join("");
}

/* --------------------------------------------------------------------------
   Ajustes: tema y token
   -------------------------------------------------------------------------- */
function openSettings() {
  const pop = $("#settings-popover");
  const btn = $("#settings-btn");
  if (!pop) return;
  pop.hidden = false;
  if (btn) btn.setAttribute("aria-expanded", "true");
  const input = $("#settings-token");
  if (input) input.value = state.token || "";
  syncThemeButtons();
}

function closeSettings() {
  const pop = $("#settings-popover");
  const btn = $("#settings-btn");
  if (!pop) return;
  pop.hidden = true;
  if (btn) btn.setAttribute("aria-expanded", "false");
}

function toggleSettings() {
  const pop = $("#settings-popover");
  if (!pop) return;
  if (pop.hidden) openSettings();
  else closeSettings();
}

function syncThemeButtons() {
  const current = window.NOVEL_THEME.getTheme();
  $$("#theme-options button").forEach((b) => {
    b.setAttribute("aria-pressed", b.dataset.themeValue === current ? "true" : "false");
  });
}

function saveToken() {
  const input = $("#settings-token");
  const hint = $("#settings-hint");
  state.token = input ? input.value.trim() : "";
  try {
    if (state.token) localStorage.setItem("novel_web_token", state.token);
    else localStorage.removeItem("novel_web_token");
  } catch (_) {}
  if (hint) hint.textContent = "Guardado";
  showToast("Ajustes guardados", "success");
}

function setupSettings() {
  const btn = $("#settings-btn");
  const pop = $("#settings-popover");
  if (!btn || !pop) return;
  btn.innerHTML = icon("settings");
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    toggleSettings();
  });
  pop.addEventListener("click", (e) => e.stopPropagation());
  $$("#theme-options button").forEach((b) => {
    b.addEventListener("click", () => {
      window.NOVEL_THEME.setTheme(b.dataset.themeValue);
      syncThemeButtons();
    });
  });
  $("#settings-save").addEventListener("click", saveToken);
  document.addEventListener("click", closeSettings);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeSettings();
  });
  // Refresca el tema si el usuario cambia el del sistema estando en "auto"
  window
    .matchMedia("(prefers-color-scheme: dark)")
    .addEventListener("change", () => {
      if (window.NOVEL_THEME.getTheme() === "auto") window.NOVEL_THEME.applyTheme("auto");
    });
}

/* --------------------------------------------------------------------------
   Diálogo de confirmación
   -------------------------------------------------------------------------- */
function confirmDialog({ title, message, confirmLabel = "Continuar" }) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.innerHTML = `
      <div class="modal" role="dialog" aria-modal="true">
        <div class="modal-head"><h3>${escapeHtml(title)}</h3></div>
        <p class="modal-desc">${escapeHtml(message)}</p>
        <div class="modal-actions">
          <button type="button" class="btn btn-secondary" data-act="cancel">Cancelar</button>
          <button type="button" class="btn btn-destructive" data-act="ok">${escapeHtml(confirmLabel)}</button>
        </div>
      </div>`;
    document.body.appendChild(overlay);
    const onKey = (e) => {
      if (e.key === "Escape") finish(false);
    };
    const done = (value) => {
      overlay.remove();
      resolve(value);
    };
    function finish(value) {
      document.removeEventListener("keydown", onKey);
      done(value);
    }
    document.addEventListener("keydown", onKey);
    overlay.querySelector('[data-act="ok"]').addEventListener("click", () => finish(true));
    overlay.querySelector('[data-act="cancel"]').addEventListener("click", () => finish(false));
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) finish(false);
    });
    overlay.querySelector('[data-act="ok"]').focus();
  });
}

/* Mueve el foco al primer elemento interactivo de un diálogo */
function focusFirstIn(root) {
  const items = root.querySelectorAll(FOCUSABLE);
  if (items.length) items[0].focus();
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), ' +
  'select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/* Focus trap para diálogos abiertos (Tab/Shift+Tab dentro del overlay) */
document.addEventListener("keydown", (e) => {
  if (e.key !== "Tab") return;
  const overlay = document.querySelector(".modal-overlay:not([hidden])");
  if (!overlay) return;
  const items = overlay.querySelectorAll(FOCUSABLE);
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  if (!overlay.contains(document.activeElement)) {
    e.preventDefault();
    first.focus();
  } else if (e.shiftKey && document.activeElement === first) {
    e.preventDefault();
    last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault();
    first.focus();
  }
});

/* Arranque común (se ejecuta antes que el script de cada página) */
document.addEventListener("DOMContentLoaded", () => {
  hydrateIcons();
  setupNavActive();
  setupSettings();
  loadConfig();
  if (typeof initJobBar === "function") initJobBar();
});
