"use strict";

/* ==========================================================================
   app.js — home: origen web/PDF, opciones avanzadas y recientes
   spec 0.3.0/06
   ========================================================================== */

const OPTIONS_KEY = "novel_web_options";

async function refreshNovels() {
  const container = $("#recent-list");
  if (!container) return;
  try {
    const novels = await api("/api/novels");
    novels.sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
    if (!novels.length) {
      container.innerHTML = emptyState(
        "Aún no hay novelas. Pega una URL para empezar.",
        "Ir a descargar",
        "#descargar",
      );
      return;
    }
    container.innerHTML = novels.slice(0, 8).map((n) => coverCard(n)).join("");
  } catch (_) {}
}

function emptyState(message, actionLabel, href) {
  return `
    <div class="empty">
      <span class="empty-icon" data-icon="inbox"></span>
      <p>${escapeHtml(message)}</p>
      ${actionLabel ? `<div class="empty-actions"><a class="btn btn-primary" href="${href}">${escapeHtml(actionLabel)}</a></div>` : ""}
    </div>`;
}

/* --------------------------------------------------------------------------
   Origen (segmented)
   -------------------------------------------------------------------------- */
function setupSourceSwitch() {
  const sw = $("#source-switch");
  if (!sw) return;
  sw.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-source]");
    if (!btn) return;
    const source = btn.dataset.source;
    $$("#source-switch button").forEach((b) =>
      b.setAttribute("aria-selected", b === btn ? "true" : "false"),
    );
    $$("[data-panel]").forEach((p) => (p.hidden = p.dataset.panel !== source));
  });
}

/* --------------------------------------------------------------------------
   Opciones avanzadas
   -------------------------------------------------------------------------- */
function setupAdvanced() {
  const toggle = $("#advanced-toggle");
  const panel = $("#advanced-panel");
  if (!toggle || !panel) return;
  toggle.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    toggle.setAttribute("aria-expanded", panel.hidden ? "false" : "true");
  });
}

function setupTranslateField() {
  const checkbox = $("#job-translate");
  if (!checkbox) return;
  const tc = $("#field-translate-concurrency");
  const lang = $("#field-language");
  const sync = () => {
    if (tc) tc.hidden = !checkbox.checked;
    if (lang) lang.hidden = !checkbox.checked;
    // Al activar traducción, abrir las opciones avanzadas para ver el ajuste.
    if (checkbox.checked) {
      const panel = $("#advanced-panel");
      const toggle = $("#advanced-toggle");
      if (panel && panel.hidden) {
        panel.hidden = false;
        if (toggle) toggle.setAttribute("aria-expanded", "true");
      }
    }
  };
  checkbox.addEventListener("change", sync);
  sync();
}

/* --------------------------------------------------------------------------
   Recordar últimas opciones
   -------------------------------------------------------------------------- */
function saveWebOptions(body) {
  try {
    localStorage.setItem(
      OPTIONS_KEY,
      JSON.stringify({
        volume_size: body.volume_size,
        concurrency: body.concurrency,
        translate: body.translate,
        target_language: body.target_language,
        all: body.all,
        translate_pending: body.translate_pending,
      }),
    );
  } catch (_) {}
}

function loadWebOptions() {
  let saved;
  try {
    saved = JSON.parse(localStorage.getItem(OPTIONS_KEY) || "null");
  } catch (_) {
    saved = null;
  }
  if (!saved) return;
  if ($("#job-volume") && saved.volume_size) $("#job-volume").value = saved.volume_size;
  if ($("#job-concurrency") && saved.concurrency) {
    $("#job-concurrency").value = saved.concurrency;
  }
  if ($("#job-translate")) $("#job-translate").checked = !!saved.translate;
  if ($("#job-all")) $("#job-all").checked = !!saved.all;
  if ($("#job-pending")) $("#job-pending").checked = !!saved.translate_pending;
  if ($("#job-language") && saved.target_language) {
    $("#job-language").value = saved.target_language;
  }
}

/* --------------------------------------------------------------------------
   Formulario PDF
   -------------------------------------------------------------------------- */
function setupPdfForm() {
  const form = $("#pdf-form");
  if (!form) return;
  form.addEventListener("submit", submitPdfJob);
  const checkbox = $("#pdf-translate");
  const lang = $("#pdf-field-language");
  const sync = () => {
    if (lang) lang.hidden = !checkbox.checked;
  };
  checkbox.addEventListener("change", sync);
  sync();
  const sourceLangs = (state.config && state.config.source_languages) || {};
  const source = $("#pdf-source");
  if (source) {
    source.innerHTML = Object.entries(sourceLangs)
      .map(([code, label]) => `<option value="${code}">${label}</option>`)
      .join("");
  }
  populateLanguageSelect($("#pdf-language"));
}

window.refreshAfterJob = refreshNovels;

document.addEventListener("DOMContentLoaded", async () => {
  setupSourceSwitch();
  setupAdvanced();
  $("#job-form").addEventListener("submit", submitJob);
  await loadConfig();
  loadWebOptions();
  populateLanguageSelect($("#job-language"));
  setupTranslateField();
  setupPdfForm();
  refreshNovels();
  setInterval(() => {
    if (!state.currentJobId) refreshNovels();
  }, 15000);
});
