"use strict";

/* ==========================================================================
   jobs.js — job bar global, envío de jobs y seguimiento en vivo
   spec 0.3.0/06
   ========================================================================== */

async function hasActiveJob() {
  try {
    const jobs = await api("/api/jobs");
    return jobs.some((j) => j.state === "pending" || j.state === "running");
  } catch (_) {
    return false;
  }
}

function setButtonLoading(btn, loading) {
  if (!btn) return;
  btn.disabled = loading;
  btn.classList.toggle("loading", loading);
  const label = btn.querySelector(".btn-label");
  if (label) {
    label.textContent = loading
      ? btn.dataset.loading || "Procesando…"
      : btn.dataset.label || label.textContent;
  }
}

/* --------------------------------------------------------------------------
   Job bar
   -------------------------------------------------------------------------- */
function showJobBar(label) {
  const bar = $("#job-bar");
  if (!bar) return;
  bar.hidden = false;
  const title = $("#job-bar-title");
  if (title) title.textContent = label || "Job en curso";
  const indicator = $("#job-indicator");
  if (indicator) indicator.hidden = false;
  const cancel = $("#cancel-btn");
  if (cancel) cancel.hidden = false;
}

function hideJobBar() {
  const bar = $("#job-bar");
  if (bar) bar.hidden = true;
  const indicator = $("#job-indicator");
  if (indicator) indicator.hidden = true;
  const detail = $("#job-bar-detail");
  if (detail) detail.hidden = true;
  const toggle = $("#job-bar-toggle");
  if (toggle) toggle.setAttribute("aria-expanded", "false");
}

function toggleJobDetail(force) {
  const detail = $("#job-bar-detail");
  const toggle = $("#job-bar-toggle");
  if (!detail || !toggle) return;
  const open = force !== undefined ? force : detail.hidden;
  detail.hidden = !open;
  toggle.setAttribute("aria-expanded", open ? "true" : "false");
}

function resetProgress() {
  ["download", "translate", "epub"].forEach((phase) => {
    const bar = $(`#bar-${phase}`);
    const count = $(`#count-${phase}`);
    if (bar) bar.style.width = "0%";
    if (count) count.textContent = "0/0";
  });
  const line = $("#status-line");
  if (line) {
    line.className = "status-line";
    line.textContent = "";
  }
  const barCount = $("#job-bar-count");
  if (barCount) barCount.textContent = "";
}

function renderStatus(event) {
  const line = $("#status-line");
  if (!line) return;
  if (event.phase === "error") {
    line.className = "status-line error";
    line.textContent = event.message || "";
    return;
  }
  if (event.phase === "done") {
    line.className = "status-line done";
    line.textContent = event.message || "";
    return;
  }
  line.className = "status-line";
  if (event.phase === "status" && /^AVISO/i.test(event.message || "")) {
    line.classList.add("warning");
  }
  line.textContent = event.message || "";
}

function renderProgress(event) {
  const bar = $(`#bar-${event.phase}`);
  const count = $(`#count-${event.phase}`);
  if (!bar || !count) return;
  const pct = event.total > 0 ? (event.done / event.total) * 100 : 0;
  bar.style.width = pct + "%";
  count.textContent = `${event.done}/${event.total}`;
  const barCount = $("#job-bar-count");
  if (barCount && event.phase === "download") {
    barCount.textContent = `${event.done}/${event.total}`;
  }
}

function onJobEvent(event) {
  if (event.type === "status") renderStatus(event);
  else if (event.type === "progress") renderProgress(event);
  if (event.type === "done" || event.type === "error" || event.type === "cancelled") {
    if (event.type === "done") showToast("Job completado", "success");
    else if (event.type === "error") showToast(event.message || "El job falló", "error");
    else showToast("Job cancelado", "info");
    if (state.socket) state.socket.close();
    state.socket = null;
    state.currentJobId = null;
    stopPolling();
    hideJobBar();
    if (typeof refreshAfterJob === "function") refreshAfterJob();
  }
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

let pollTimer = null;
function startPolling() {
  stopPolling();
  pollTimer = setInterval(async () => {
    if (!state.currentJobId) return;
    try {
      const job = await api(`/api/jobs/${state.currentJobId}`);
      if (["done", "error", "cancelled"].includes(job.state)) {
        const line = $("#status-line");
        if (job.state === "error") {
          if (line) {
            line.className = "status-line error";
            line.textContent = job.error || "error";
          }
          showToast(job.error || "El job falló", "error");
        } else if (job.state === "done") {
          showToast("Job completado", "success");
        } else {
          showToast("Job cancelado", "info");
        }
        state.currentJobId = null;
        stopPolling();
        hideJobBar();
        if (typeof refreshAfterJob === "function") refreshAfterJob();
      }
    } catch (_) {}
  }, 1500);
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

function setJobIndicator(busy) {
  const indicator = $("#job-indicator");
  if (!indicator) return;
  indicator.hidden = !busy;
  indicator.classList.toggle("busy", busy);
}

function attachJob(jobId, label) {
  state.currentJobId = jobId;
  showJobBar(label);
  resetProgress();
  setJobIndicator(true);
  connectSocket(jobId);
  startPolling();
  toggleJobDetail(true);
}

async function cancelJob() {
  if (!state.currentJobId) return;
  try {
    await api(`/api/jobs/${state.currentJobId}/cancel`, { method: "POST" });
  } catch (e) {
    showToast(e.message, "error");
  }
}

/* Al cargar: si hay un job en curso (p. ej. lanzado desde otra página),
   reconectar el job bar. */
async function initJobBar() {
  const toggle = $("#job-bar-toggle");
  const cancel = $("#cancel-btn");
  if (toggle) toggle.innerHTML = icon("chevron-down");
  if (cancel) cancel.innerHTML = icon("x");
  if (toggle) toggle.addEventListener("click", () => toggleJobDetail());
  if (cancel) cancel.addEventListener("click", cancelJob);
  const indicator = $("#job-indicator");
  if (indicator) {
    indicator.innerHTML = icon("play");
    indicator.addEventListener("click", () => {
      showJobBar($("#job-bar-title") ? $("#job-bar-title").textContent : "");
      toggleJobDetail(true);
    });
  }
  try {
    const jobs = await api("/api/jobs");
    const active = jobs.find((j) => j.state === "pending" || j.state === "running");
    if (active) attachJob(active.id, active.url || "Job en curso");
  } catch (_) {}
}

/* --------------------------------------------------------------------------
   Envío de jobs
   -------------------------------------------------------------------------- */
function collectWebOptions() {
  const body = {
    url: $("#job-url").value.trim(),
    volume_size: parseInt($("#job-volume").value, 10) || 50,
    translate: $("#job-translate").checked,
    all: $("#job-all").checked,
    translate_pending: $("#job-pending").checked,
    force: $("#job-force").checked,
    playwright: $("#job-playwright").checked,
    concurrency: parseInt($("#job-concurrency").value, 10) || 4,
  };
  if (body.translate && $("#job-language")) {
    body.target_language = $("#job-language").value;
  }
  const tc = $("#job-translate-concurrency");
  if (tc && !$("#field-translate-concurrency").hidden) {
    body.translate_concurrency = parseInt(tc.value, 10) || 1;
  }
  return body;
}

async function submitJob(event) {
  event.preventDefault();
  const body = collectWebOptions();
  if (!body.url) {
    showToast("Introduce una URL", "error");
    return;
  }
  if (await hasActiveJob()) {
    showToast("Ya hay un job en curso", "info");
    return;
  }
  if (body.force || body.all) {
    const ok = await confirmDialog({
      title: "Confirmar descarga",
      message: body.force
        ? "Se volverán a descargar capítulos que ya existen en disco."
        : "Se descargará la novela completa de una vez (puede tardar).",
      confirmLabel: "Continuar",
    });
    if (!ok) return;
  }
  const btn = $("#job-submit");
  setButtonLoading(btn, true);
  try {
    saveWebOptions(body);
    const { job_id } = await api("/api/jobs", { method: "POST", body });
    attachJob(job_id, body.url);
    showToast("Descarga lanzada", "success");
  } catch (e) {
    showToast(e.message, "error");
  } finally {
    setButtonLoading(btn, false);
  }
}

async function submitPdfJob(event) {
  event.preventDefault();
  const file = $("#pdf-file").files[0];
  if (!file) {
    showToast("Selecciona un PDF", "error");
    return;
  }
  if (await hasActiveJob()) {
    showToast("Ya hay un job en curso", "info");
    return;
  }
  const body = new FormData();
  body.append("file", file);
  body.append("source_language", $("#pdf-source").value);
  body.append("volume_size", parseInt($("#pdf-volume").value, 10) || 50);
  if ($("#pdf-translate").checked) {
    body.append("translate", "true");
    body.append("target_language", $("#pdf-language").value);
  }
  const btn = $("#pdf-submit");
  setButtonLoading(btn, true);
  try {
    const { job_id } = await api("/api/upload", { method: "POST", body });
    attachJob(job_id, file.name);
    showToast("PDF subido, convirtiendo", "success");
  } catch (e) {
    showToast(e.message, "error");
  } finally {
    setButtonLoading(btn, false);
  }
}

/* --------------------------------------------------------------------------
   Acciones de novela (ficha)
   -------------------------------------------------------------------------- */
async function syncNovel(btn) {
  if (await hasActiveJob()) {
    showToast("Ya hay un job en curso. Espera a que termine.", "info");
    return;
  }
  setButtonLoading(btn, true);
  try {
    const { job_id } = await api(
      `/api/novels/${btn.dataset.slug}/sync`,
      { method: "POST" },
    );
    attachJob(job_id, btn.dataset.title || "");
    showToast(`Sincronizando: ${btn.dataset.title || ""}`, "info");
  } catch (e) {
    showToast(e.message, "error");
    setButtonLoading(btn, false);
  }
}

async function retranslateNovel(btn) {
  if (await hasActiveJob()) {
    showToast("Ya hay un job en curso. Espera a que termine.", "info");
    return;
  }
  setButtonLoading(btn, true);
  try {
    const { job_id } = await api(
      `/api/novels/${btn.dataset.slug}/retranslate`,
      { method: "POST" },
    );
    attachJob(job_id, btn.dataset.title || "");
    showToast(`Re-traduciendo: ${btn.dataset.title || ""}`, "info");
  } catch (e) {
    showToast(e.message, "error");
    setButtonLoading(btn, false);
  }
}
