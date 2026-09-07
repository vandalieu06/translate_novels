"use strict";

async function hasActiveJob() {
  try {
    const jobs = await api("/api/jobs");
    return jobs.some((j) => j.state === "pending" || j.state === "running");
  } catch (_) {
    return false;
  }
}

function setButtonLoading(btn, loading) {
  btn.disabled = loading;
  btn.classList.toggle("loading", loading);
  const label = btn.querySelector(".btn-label");
  if (label) {
    label.textContent = loading
      ? btn.dataset.loading || "Procesando..."
      : btn.dataset.label || label.textContent;
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
  const langField = $("#job-language");
  if (body.translate && langField) {
    body.target_language = langField.value;
  }
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

function showProgressPanel(label) {
  const url = $("#job-progress-url");
  if (url) url.textContent = label;
  setServerStatus(true);
  const jobSection = $("#novel-job");
  if (jobSection) jobSection.hidden = false;
  const panel = $("#job-progress");
  if (!panel) return;
  panel.classList.add("visible");
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
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
  setButtonLoading(btn, true);
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
    setButtonLoading(btn, false);
  }
}

async function retranslateNovel(btn) {
  if (await hasActiveJob()) {
    showToast("Ya hay un job en curso. Espera a que termine.", "info");
    return;
  }
  const slug = btn.dataset.slug;
  const title = btn.dataset.title;
  setButtonLoading(btn, true);
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
    setButtonLoading(btn, false);
  }
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
    line.innerHTML = "";
  }
  setJobBadge("en curso", "badge-info");
  const cancel = $("#cancel-btn");
  if (cancel) cancel.style.display = "inline-flex";
}

function setJobBadge(text, cls) {
  const badge = $("#job-state-badge");
  if (!badge) return;
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
  if (!line) return;
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
        const line = $("#status-line");
        if (job.state === "error") {
          if (line) {
            line.className = "status-line error";
            line.innerHTML = `<span class="tag">error</span>${escapeHtml(job.error || "error")}`;
          }
          setJobBadge("error", "badge-danger");
        } else if (job.state === "done") {
          setJobBadge("listo", "badge-success");
        } else {
          setJobBadge("cancelado", "badge-neutral");
        }
        const cancel = $("#cancel-btn");
        if (cancel) cancel.style.display = "none";
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