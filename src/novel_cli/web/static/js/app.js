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
  if (options.body && typeof options.body !== "string") {
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
}

/* ---------- Job form ---------- */
async function hasActiveJob() {
  try {
    const jobs = await api("/api/jobs");
    return jobs.some((j) => j.state === "pending" || j.state === "running");
  } catch (_) {
    return false;
  }
}

async function submitJob(event) {
  event.preventDefault();
  const url = $("#job-url").value.trim();
  if (!url) return showToast("Introduce una URL", "error");
  const body = {
    url,
    volume_size: parseInt($("#job-volume").value, 10) || 50,
    translate: $("#job-translate").checked,
    all: $("#job-all").checked,
    translate_pending: $("#job-pending").checked,
    force: $("#job-force").checked,
    playwright: $("#job-playwright").checked,
    concurrency: parseInt($("#job-concurrency").value, 10) || 4,
  };
  const tcField = $("#job-translate-concurrency");
  if (tcField && !tcField.closest(".field").hidden) {
    body.translate_concurrency = parseInt(tcField.value, 10) || 1;
  }
  const btn = $("#job-submit");
  if (await hasActiveJob()) {
    showToast("Ya hay un job en curso", "info");
    return;
  }
  setButtonLoading(btn, true);
  try {
    const { job_id } = await api("/api/jobs", { method: "POST", body });
    state.currentJobId = job_id;
    showProgressPanel(url);
    resetProgress();
    connectSocket(job_id);
    startPolling();
    showToast("Descarga lanzada", "success");
  } catch (e) {
    showToast(e.message, "error");
  } finally {
    setButtonLoading(btn, false);
  }
}

function setButtonLoading(btn, loading) {
  btn.disabled = loading;
  btn.classList.toggle("loading", loading);
  const label = btn.querySelector(".btn-label");
  if (label) label.textContent = loading ? "Lanzando..." : "Lanzar descarga";
}

function showProgressPanel(url) {
  $("#job-progress-url").textContent = url;
  setServerStatus(true);
  $("#job-progress").classList.add("visible");
  $("#job-progress").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function cancelJob() {
  if (!state.currentJobId) return;
  try {
    await api(`/api/jobs/${state.currentJobId}/cancel`, { method: "POST" });
  } catch (e) {
    showToast(e.message, "error");
  }
}

async function syncNovel(btn) {
  if (await hasActiveJob()) {
    showToast("Ya hay un job en curso. Espera a que termine.", "info");
    return;
  }
  const slug = btn.dataset.slug;
  const title = btn.dataset.title;
  setSyncLoading(btn, true);
  try {
    const { job_id } = await api(`/api/novels/${slug}/sync`, { method: "POST" });
    state.currentJobId = job_id;
    showProgressPanel(title);
    resetProgress();
    connectSocket(job_id);
    startPolling();
    showToast(`Sincronizando: ${title}`, "info");
  } catch (e) {
    showToast(e.message, "error");
    setSyncLoading(btn, false);
  }
}

function setSyncLoading(btn, loading) {
  btn.disabled = loading;
  btn.classList.toggle("loading", loading);
  const label = btn.querySelector(".sync-label");
  if (label) label.textContent = loading ? "Sincronizando..." : "Sync";
}

function resetProgress() {
  ["download", "translate", "epub"].forEach((phase) => {
    const bar = $(`#bar-${phase}`);
    const count = $(`#count-${phase}`);
    if (bar) bar.style.width = "0%";
    if (count) count.textContent = "0/0";
  });
  $("#status-line").className = "status-line";
  $("#status-line").innerHTML = "";
  setJobBadge("en curso", "badge-info");
  $("#cancel-btn").style.display = "inline-flex";
}

function setJobBadge(text, cls) {
  const badge = $("#job-state-badge");
  badge.textContent = text;
  badge.className = "badge " + cls;
}

function onJobEvent(event) {
  if (event.type === "status") {
    renderStatus(event);
  } else if (event.type === "progress") {
    renderProgress(event);
  }
  if (event.type === "done" || event.type === "error" || event.type === "cancelled") {
    setServerStatus(false);
    stopPolling();
    if (state.socket) state.socket.close();
    state.currentJobId = null;
    refreshNovels();
  }
}

function renderStatus(event) {
  const line = $("#status-line");
  if (event.phase === "error") {
    line.className = "status-line error";
    setJobBadge("error", "badge-danger");
    line.innerHTML = `<span class="tag">error</span>${escapeHtml(event.message || "")}`;
    return;
  }
  if (event.phase === "done") {
    line.className = "status-line done";
    setJobBadge("listo", "badge-success");
    line.innerHTML = `<span class="tag">listo</span>${escapeHtml(event.message || "")}`;
    return;
  }
  line.className = "status-line";
  if (event.phase === "status" && /^AVISO/i.test(event.message || "")) {
    line.classList.add("warning");
  }
  line.innerHTML = `<span class="tag">${escapeHtml(event.phase)}</span>${escapeHtml(event.message || "")}`;
}

function renderProgress(event) {
  const bar = $(`#bar-${event.phase}`);
  const count = $(`#count-${event.phase}`);
  if (!bar || !count) return;
  const pct = event.total > 0 ? (event.done / event.total) * 100 : 0;
  bar.style.width = pct + "%";
  count.textContent = `${event.done}/${event.total}`;
}

function connectSocket(jobId) {
  if (state.socket) state.socket.close();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/api/jobs/${jobId}/ws`);
  ws.onmessage = (msg) => onJobEvent(JSON.parse(msg.data));
  ws.onclose = () => {
    state.socket = null;
  };
  state.socket = ws;
}

/* ---------- Polling fallback / final state ---------- */
let pollTimer = null;
function startPolling() {
  stopPolling();
  pollTimer = setInterval(async () => {
    if (!state.currentJobId) return;
    try {
      const job = await api(`/api/jobs/${state.currentJobId}`);
      if (["done", "error", "cancelled"].includes(job.state)) {
        if (job.state === "error") {
          $("#status-line").className = "status-line error";
          setJobBadge("error", "badge-danger");
          $("#status-line").innerHTML = `<span class="tag">error</span>${escapeHtml(job.error || "error")}`;
        } else if (job.state === "done") {
          setJobBadge("listo", "badge-success");
        } else {
          setJobBadge("cancelado", "badge-neutral");
        }
        $("#cancel-btn").style.display = "none";
        setServerStatus(false);
        stopPolling();
        state.currentJobId = null;
        refreshNovels();
      }
    } catch (_) {}
  }, 1500);
}
function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

/* ---------- Server status pill ---------- */
function setServerStatus(busy) {
  const el = $("#server-status");
  el.classList.toggle("busy", busy);
  $("#server-status-text").textContent = busy ? "Job en curso" : "Servidor OK";
}

/* ---------- Novel list ---------- */
async function refreshNovels() {
  try {
    const novels = await api("/api/novels");
    novels.sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
    renderNovels(novels);
    renderStats(novels);
  } catch (_) {}
}

function renderStats(novels) {
  const totalChapters = novels.reduce((n, x) => n + (x.chapters_downloaded || 0), 0);
  const translated = novels.reduce((n, x) => n + (x.chapters_translated || 0), 0);
  $("#stat-novels").textContent = novels.length.toLocaleString();
  $("#stat-chapters").textContent = totalChapters.toLocaleString();
  $("#stat-translated").textContent = translated.toLocaleString();
}

function renderNovels(novels) {
  const container = $("#novel-list");
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
  container.innerHTML = novels
    .map((n) => {
      const cover = n.cover
        ? `<img class="cover" src="${n.cover}" alt="">`
        : `<div class="cover placeholder">&#128214;</div>`;
      const lang = n.translated ? "ES + original" : "original";
      const epubLinks = epubButtons(n);
      const pct = n.chapters_total > 0
        ? Math.round((n.chapters_downloaded / n.chapters_total) * 100)
        : 0;
      const volumeCount = (n.epub_original || []).length;
      const emptyNums = (n.chapters_empty_nums || []).slice(0, 20);
      const emptyWarning = n.chapters_empty > 0
        ? `<div class="empty-warning" title="${escapeHtml(emptyNums.join(", "))}">
             &#9888; ${n.chapters_empty} cap. vacío(s) pendientes de reintento
           </div>`
        : "";
      return `
        <article class="novel-card">
          ${cover}
          <div class="body">
            <h3>${escapeHtml(n.title)}</h3>
            <div class="author">${escapeHtml(n.author || "")}</div>
            <div class="meta">
              <span class="badge ${n.translated ? "badge-success" : "badge-neutral"}">${lang}</span>
              ${volumeCount ? `<span class="chip">${volumeCount} vol.</span>` : ""}
            </div>
            ${emptyWarning}
            <div class="progress-row">
              <div class="mini-bar"><div class="mini-fill" style="width:${pct}%"></div></div>
              <span class="pct">${pct}%</span>
            </div>
            <div class="card-actions">
              <button class="btn btn-secondary btn-sync" data-slug="${encodeURIComponent(n.slug)}" data-title="${escapeHtml(n.title)}">
                <span class="sync-icon">&#8635;</span>
                <span class="sync-label">Sync</span>
              </button>
              <div class="epub-links">${epubLinks}</div>
            </div>
          </div>
        </article>`;
    })
    .join("");
}

function epubButtons(n) {
  const mk = (name) =>
    name
      ? `<a class="btn btn-secondary" href="/api/novels/${encodeURIComponent(n.slug)}/epub/${encodeURIComponent(name)}" download="${escapeHtml(name)}">${escapeHtml(name)}</a>`
      : "";
  const orig = (n.epub_original || []).map(mk).join("");
  const trans = (n.epub_translated || []).map(mk).join("");
  return orig + trans;
}

function escapeHtml(str) {
  return String(str).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

/* ---------- Scrollspy ---------- */
function setupScrollspy() {
  const sections = ["descargar", "biblioteca"];
  const links = {};
  sections.forEach((id) => {
    const a = document.querySelector(`#main-nav a[href="#${id}"]`);
    if (a) links[id] = a;
  });
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          sections.forEach((id) => {
            if (links[id]) links[id].classList.toggle("active", id === entry.target.id);
          });
        }
      });
    },
    { rootMargin: "-40% 0px -55% 0px" }
  );
  sections.forEach((id) => {
    const el = document.getElementById(id);
    if (el) observer.observe(el);
  });
}

/* ---------- Init ---------- */
function setupTranslateField() {
  const checkbox = $("#job-translate");
  const field = $("#field-translate-concurrency");
  const syncVisibility = () => {
    field.hidden = !checkbox.checked;
  };
  checkbox.addEventListener("change", syncVisibility);
  syncVisibility();
}

document.addEventListener("DOMContentLoaded", async () => {
  $("#job-form").addEventListener("submit", submitJob);
  $("#cancel-btn").addEventListener("click", cancelJob);
  $("#cancel-btn").style.display = "none";
  $("#novel-list").addEventListener("click", (event) => {
    const btn = event.target.closest(".btn-sync");
    if (btn) syncNovel(btn);
  });
  setupTranslateField();
  setupScrollspy();
  await loadConfig();
  refreshNovels();
  setInterval(() => {
    if (!state.currentJobId) refreshNovels();
  }, 15000);
});
