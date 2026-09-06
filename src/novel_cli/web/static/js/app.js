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
  renderBackend();
}

function renderBackend() {
  const pill = $("#backend-pill");
  if (!pill) return;
  const backend = state.config.translate_backend;
  pill.textContent = backend === "libre" ? "Traducción: LibreTranslate" : "Traducción: Google";
  pill.hidden = false;
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

async function retranslateNovel(btn) {
  if (await hasActiveJob()) {
    showToast("Ya hay un job en curso. Espera a que termine.", "info");
    return;
  }
  const slug = btn.dataset.slug;
  const title = btn.dataset.title;
  setRetranslateLoading(btn, true);
  try {
    const { job_id } = await api(`/api/novels/${slug}/retranslate`, { method: "POST" });
    state.currentJobId = job_id;
    showProgressPanel(title);
    resetProgress();
    connectSocket(job_id);
    startPolling();
    showToast(`Re-traduciendo: ${title}`, "info");
  } catch (e) {
    showToast(e.message, "error");
    setRetranslateLoading(btn, false);
  }
}

function setRetranslateLoading(btn, loading) {
  btn.disabled = loading;
  btn.classList.toggle("loading", loading);
  const label = btn.querySelector(".retranslate-label");
  if (label) label.textContent = loading ? "Re-traduciendo..." : "Re-traducir";
}

/* ---------- Modal de tamaño de tomo ---------- */
let volumeState = { slug: null, size: null };

function openVolumeModal(slug, title, currentSize) {
  volumeState = { slug, size: null };
  $("#volume-modal-novel").textContent = title;
  const applyBtn = $("#volume-modal-apply");
  applyBtn.disabled = true;
  const pills = document.querySelectorAll("#volume-pills .pill");
  pills.forEach((pill) => {
    const pillSize = pill.dataset.size;
    const active = currentSize == null
      ? pillSize === "null"
      : pillSize === String(currentSize);
    pill.classList.toggle("active", active);
  });
  $("#volume-modal").hidden = false;
}

function closeVolumeModal() {
  $("#volume-modal").hidden = true;
}

function selectVolumePill(pill) {
  document.querySelectorAll("#volume-pills .pill").forEach((p) => p.classList.remove("active"));
  pill.classList.add("active");
  volumeState.size = pill.dataset.size === "null" ? null : parseInt(pill.dataset.size, 10);
  $("#volume-modal-apply").disabled = false;
}

async function applyVolumeSize() {
  if (volumeState.size == null && volumeState.slug === null) return;
  const btn = $("#volume-modal-apply");
  btn.disabled = true;
  btn.classList.add("loading");
  const label = btn.querySelector(".btn-label");
  if (label) label.textContent = "Regenerando...";
  try {
    await api(`/api/novels/${volumeState.slug}/volume-size`, {
      method: "POST",
      body: { volume_size: volumeState.size },
    });
    closeVolumeModal();
    showToast("EPUBs regenerados", "success");
    refreshNovels();
  } catch (e) {
    showToast(e.message, "error");
    btn.disabled = false;
  } finally {
    btn.classList.remove("loading");
    if (label) label.textContent = "Regenerar";
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
              ${n.translated
                ? `<button class="btn btn-secondary btn-retranslate" data-slug="${encodeURIComponent(n.slug)}" data-title="${escapeHtml(n.title)}">
                     <span class="retranslate-icon">&#128221;</span>
                     <span class="retranslate-label">Re-traducir</span>
                   </button>`
                : ""}
              <button class="btn btn-secondary btn-volumes" data-slug="${encodeURIComponent(n.slug)}" data-title="${escapeHtml(n.title)}" data-size="${n.volume_size == null ? "ALL" : n.volume_size}">
                <span class="volumes-icon">&#128196;</span>
                <span class="volumes-label">Tomos ${n.volume_size == null ? "ALL" : n.volume_size}</span>
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
    const syncBtn = event.target.closest(".btn-sync");
    if (syncBtn) syncNovel(syncBtn);
    const retranslateBtn = event.target.closest(".btn-retranslate");
    if (retranslateBtn) retranslateNovel(retranslateBtn);
    const volumesBtn = event.target.closest(".btn-volumes");
    if (volumesBtn) {
      openVolumeModal(
        volumesBtn.dataset.slug,
        volumesBtn.dataset.title,
        volumesBtn.dataset.size === "ALL" ? null : parseInt(volumesBtn.dataset.size, 10),
      );
    }
  });
  $("#volume-modal-close").addEventListener("click", closeVolumeModal);
  $("#volume-modal-cancel").addEventListener("click", closeVolumeModal);
  $("#volume-modal-apply").addEventListener("click", applyVolumeSize);
  $("#volume-modal").addEventListener("click", (event) => {
    if (event.target.id === "volume-modal") closeVolumeModal();
  });
  document.querySelectorAll("#volume-pills .pill").forEach((pill) => {
    pill.addEventListener("click", () => selectVolumePill(pill));
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeVolumeModal();
  });
  setupTranslateField();
  setupScrollspy();
  await loadConfig();
  refreshNovels();
  setInterval(() => {
    if (!state.currentJobId) refreshNovels();
  }, 15000);
});
