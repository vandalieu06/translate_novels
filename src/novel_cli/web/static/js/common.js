"use strict";

const state = {
  token: localStorage.getItem("novel_web_token") || "",
  currentJobId: null,
  socket: null,
  config: { auth_required: false, default_volume_size: 50, default_concurrency: 4 },
};

const $ = (sel) => document.querySelector(sel);

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
    promptToken();
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

function promptToken() {
  const token = window.prompt("Introduce el token de acceso (NOVEL_WEB_TOKEN):");
  if (token !== null) {
    state.token = token;
    localStorage.setItem("novel_web_token", token);
  }
}

async function loadConfig() {
  try {
    state.config = await api("/api/config");
  } catch (_) {}
  if (state.config.auth_required && !state.token) {
    promptToken();
  }
  renderBackend();
}

function renderBackend() {
  const pill = $("#backend-pill");
  if (!pill) return;
  const backend = state.config.translate_backend;
  if (backend === "libre") {
    pill.textContent = "Traducción: LibreTranslate";
  } else if (backend === "ollama") {
    pill.textContent = `Traducción: Ollama (${state.config.ollama_model || "LLM"})`;
  } else {
    pill.textContent = "Traducción: Google";
  }
  pill.hidden = false;
}

function setServerStatus(busy) {
  const el = $("#server-status");
  if (!el) return;
  el.classList.toggle("busy", busy);
  $("#server-status-text").textContent = busy ? "Job en curso" : "Servidor OK";
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function coverMarkup(n) {
  return n.cover
    ? `<img class="cover" src="${n.cover}" alt="" loading="lazy">`
    : `<div class="cover placeholder">&#128214;</div>`;
}

function coverCard(n) {
  const pct = n.chapters_total > 0
    ? Math.round((n.chapters_downloaded / n.chapters_total) * 100)
    : 0;
  const emptyNums = (n.chapters_empty_nums || []).slice(0, 20);
  const emptyWarning = n.chapters_empty > 0
    ? `<span class="badge badge-warning cover-badge" title="${escapeHtml(emptyNums.join(", "))}">&#9888; ${n.chapters_empty}</span>`
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
    </a>`;
}

function languageLabel(code) {
  if (!code) return "";
  const langs = (state.config && state.config.translate_languages) || {};
  return langs[code] || code.toUpperCase();
}

function populateLanguageSelect(select) {
  const langs = (state.config && state.config.translate_languages) || {};
  select.innerHTML = Object.entries(langs)
    .map(([code, label]) => `<option value="${code}">${label}</option>`)
    .join("");
}

function setupNavActive() {
  const page = document.body.dataset.page;
  const link = document.querySelector(`#main-nav a[data-nav="${page}"]`);
  if (link) link.classList.add("active");
}