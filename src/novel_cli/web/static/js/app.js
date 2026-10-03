"use strict";

async function refreshNovels() {
  try {
    const novels = await api("/api/novels");
    novels.sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
    renderStats(novels);
    renderRecent(novels);
  } catch (_) {}
}

function renderStats(novels) {
  const totalChapters = novels.reduce((n, x) => n + (x.chapters_downloaded || 0), 0);
  const translated = novels.reduce((n, x) => n + (x.chapters_translated || 0), 0);
  $("#stat-novels").textContent = novels.length.toLocaleString();
  $("#stat-chapters").textContent = totalChapters.toLocaleString();
  $("#stat-translated").textContent = translated.toLocaleString();
}

function renderRecent(novels) {
  const container = $("#recent-list");
  if (!container) return;
  if (!novels.length) {
    container.innerHTML = `
      <div class="empty">
        <span class="empty-icon">&#128214;</span>
        Aún no hay novelas descargadas.
        <div class="empty-actions">
          <a class="btn btn-primary" href="#descargar">Ir a descargar</a>
        </div>
      </div>`;
    return;
  }
  const recent = novels.slice(0, 8);
  container.innerHTML = recent
    .map((n) => coverCard(n))
    .join("");
}

function setupTranslateField() {
  const checkbox = $("#job-translate");
  const field = $("#field-translate-concurrency");
  const langField = $("#field-language");
  const syncVisibility = () => {
    field.hidden = !checkbox.checked;
    if (langField) langField.hidden = !checkbox.checked;
  };
  checkbox.addEventListener("change", syncVisibility);
  syncVisibility();
}

function setupPdfForm() {
  const form = $("#pdf-form");
  if (!form) return;
  form.addEventListener("submit", submitPdfJob);
  const checkbox = $("#pdf-translate");
  const langField = $("#pdf-field-language");
  const syncVisibility = () => {
    if (langField) langField.hidden = !checkbox.checked;
  };
  checkbox.addEventListener("change", syncVisibility);
  syncVisibility();
  const sourceLangs = (state.config && state.config.source_languages) || {};
  const source = $("#pdf-source");
  if (source) {
    source.innerHTML = Object.entries(sourceLangs)
      .map(([code, label]) => `<option value="${code}">${label}</option>`)
      .join("");
  }
  populateLanguageSelect($("#pdf-language"));
}

document.addEventListener("DOMContentLoaded", async () => {
  $("#job-form").addEventListener("submit", submitJob);
  $("#cancel-btn").addEventListener("click", cancelJob);
  $("#cancel-btn").style.display = "none";
  setupNavActive();
  setupTranslateField();
  await loadConfig();
  populateLanguageSelect($("#job-language"));
  setupPdfForm();
  refreshNovels();
  setInterval(() => {
    if (!state.currentJobId) refreshNovels();
  }, 15000);
});