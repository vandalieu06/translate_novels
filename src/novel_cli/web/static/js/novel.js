"use strict";

function getSlug() {
  const parts = location.pathname.split("/").filter(Boolean);
  return parts.length ? decodeURIComponent(parts[parts.length - 1]) : "";
}

async function refreshNovels() {
  await loadNovel();
}

async function loadNovel() {
  const slug = getSlug();
  if (!slug) {
    renderNotFound("Novela no indicada en la URL");
    return;
  }
  try {
    const n = await api(`/api/novels/${encodeURIComponent(slug)}`);
    renderHero(n);
    renderActions(n);
    renderEpubs(n);
    document.title = `${n.title} · novel-cli web`;
  } catch (e) {
    renderNotFound(e.message);
  }
}

function renderHero(n) {
  $("#novel-cover").innerHTML = `<div class="novel-cover-frame">${coverMarkup(n)}</div>`;
  $("#novel-title").textContent = n.title;
  $("#novel-author").textContent = n.author || "";

  const meta = [];
  meta.push(`<span class="badge ${n.translated ? "badge-success" : "badge-neutral"}">${n.translated ? `${languageLabel(n.translated_language || "es")} + original` : "original"}</span>`);
  const volCount = (n.epub_original || []).length;
  if (volCount) meta.push(`<span class="chip">${volCount} vol.</span>`);
  meta.push(`<span class="chip">${n.volume_size == null ? "ALL capítulos/tomo" : `${n.volume_size} cap/tomo`}</span>`);
  $("#novel-meta").innerHTML = meta.join(" ");

  const pct = n.chapters_total > 0
    ? Math.round((n.chapters_downloaded / n.chapters_total) * 100)
    : 0;
  $("#novel-progress").innerHTML = `
    <div class="novel-stats">
      <span>${n.chapters_downloaded || 0} / ${n.chapters_total || 0} capítulos</span>
      <span>${pct}%</span>
    </div>
    <div class="mini-bar"><div class="mini-fill" style="width:${pct}%"></div></div>`;

  const emptyNums = (n.chapters_empty_nums || []).slice(0, 20);
  $("#novel-empty-warning").innerHTML = n.chapters_empty > 0
    ? `<div class="empty-warning" title="${escapeHtml(emptyNums.join(", "))}">&#9888; ${n.chapters_empty} cap. vacío(s) pendientes de reintento</div>`
    : "";
}

function renderActions(n) {
  const slug = encodeURIComponent(n.slug);
  const title = escapeHtml(n.title);
  const volumeSize = n.volume_size == null ? "ALL" : n.volume_size;
  const actions = [];
  actions.push(`
    <button class="btn btn-secondary btn-sync" data-slug="${slug}" data-title="${title}" data-label="Sync" data-loading="Sincronizando...">
      <span class="sync-icon">&#8635;</span><span class="btn-label">Sync</span>
    </button>`);
  if (!n.translated) {
    actions.push(`
      <button class="btn btn-secondary btn-translate" data-slug="${slug}" data-title="${title}" data-label="Traducir" data-loading="Abriendo...">
        <span class="translate-icon">&#127760;</span><span class="btn-label">Traducir</span>
      </button>`);
  } else {
    actions.push(`
      <button class="btn btn-secondary btn-retranslate" data-slug="${slug}" data-title="${title}" data-label="Re-traducir" data-loading="Re-traduciendo...">
        <span class="retranslate-icon">&#128221;</span><span class="btn-label">Re-traducir</span>
      </button>`);
  }
  actions.push(`
    <button class="btn btn-secondary btn-volumes" data-slug="${slug}" data-title="${title}" data-size="${volumeSize}">
      <span class="volumes-icon">&#128196;</span><span class="btn-label">Tomos ${volumeSize}</span>
    </button>`);
  if (n.source_url) {
    actions.push(`<a class="btn btn-secondary" href="${escapeHtml(n.source_url)}" target="_blank" rel="noopener">Fuente</a>`);
  }
  $("#novel-actions").innerHTML = actions.join(" ");
}

function renderEpubs(n) {
  const groups = [];
  const orig = (n.epub_original || []).map((name) => epubCard(n.slug, name)).join("");
  const trans = (n.epub_translated || []).map((name) => epubCard(n.slug, name)).join("");
  if (orig) groups.push(`<div class="epub-group"><h3>Original</h3><div class="epub-grid">${orig}</div></div>`);
  if (trans) {
    const lang = (n.translated_language || "es").toUpperCase();
    groups.push(`<div class="epub-group"><h3>Traducción (${lang})</h3><div class="epub-grid">${trans}</div></div>`);
  }
  $("#epub-groups").innerHTML = groups.length
    ? groups.join("")
    : `<div class="empty"><span class="empty-icon">&#128196;</span>Aún no hay EPUBs generados.</div>`;
}

function epubCard(slug, name) {
  return `
    <div class="epub-card">
      <span class="epub-name" title="${escapeHtml(name)}">${escapeHtml(name)}</span>
      <a class="btn btn-primary" href="/api/novels/${encodeURIComponent(slug)}/epub/${encodeURIComponent(name)}" download="${escapeHtml(name)}">Descargar</a>
    </div>`;
}

function renderNotFound(msg) {
  $("#novel-cover").innerHTML = `<div class="novel-cover-frame"><div class="cover placeholder">&#128214;</div></div>`;
  $("#novel-title").textContent = "Novela no encontrada";
  $("#novel-author").textContent = msg || "";
  $("#novel-meta").innerHTML = "";
  $("#novel-progress").innerHTML = "";
  $("#novel-empty-warning").innerHTML = "";
  $("#novel-actions").innerHTML = `<a class="btn btn-secondary" href="/biblioteca">Volver a la biblioteca</a>`;
  $("#epub-groups").innerHTML = "";
  document.title = "Novela no encontrada · novel-cli web";
}

/* ---------- Modal de idioma de traducción ---------- */
let translateState = { slug: null, target_language: null };

function openTranslateModal(slug, title) {
  translateState = { slug, target_language: null };
  $("#translate-modal-novel").textContent = title;
  const applyBtn = $("#translate-modal-apply");
  applyBtn.disabled = true;
  const langs = (state.config && state.config.translate_languages) || {};
  $("#translate-pills").innerHTML = Object.entries(langs)
    .map(([code, label]) => `<button type="button" class="pill" data-lang="${code}">${label}</button>`)
    .join("");
  document.querySelectorAll("#translate-pills .pill").forEach((pill) => {
    pill.addEventListener("click", () => selectTranslatePill(pill));
  });
  $("#translate-modal").hidden = false;
}

function closeTranslateModal() {
  $("#translate-modal").hidden = true;
}

function selectTranslatePill(pill) {
  document.querySelectorAll("#translate-pills .pill").forEach((p) => p.classList.remove("active"));
  pill.classList.add("active");
  translateState.target_language = pill.dataset.lang;
  $("#translate-modal-apply").disabled = false;
}

async function applyTranslate() {
  const slug = translateState.slug;
  const lang = translateState.target_language;
  if (!slug || !lang) return;
  const btn = $("#translate-modal-apply");
  btn.disabled = true;
  try {
    const { job_id } = await api(`/api/novels/${slug}/retranslate`, {
      method: "POST",
      body: { target_language: lang },
    });
    state.currentJobId = job_id;
    closeTranslateModal();
    showProgressPanel($("#novel-title").textContent);
    resetProgress();
    connectSocket(job_id);
    startPolling();
    showToast(`Traduciendo a ${languageLabel(lang)}`, "info");
  } catch (e) {
    showToast(e.message, "error");
    btn.disabled = false;
  }
}

/* ---------- Modal de tamaño de tomo ---------- */
let volumeState = { slug: null, size: null };

function openVolumeModal(slug, title, currentSize) {
  volumeState = { slug, size: null };
  $("#volume-modal-novel").textContent = title;
  const applyBtn = $("#volume-modal-apply");
  applyBtn.disabled = true;
  document.querySelectorAll("#volume-pills .pill").forEach((pill) => {
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
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  setupNavActive();
  await loadConfig();
  loadNovel();

  $("#novel-actions").addEventListener("click", (event) => {
    const translateBtn = event.target.closest(".btn-translate");
    if (translateBtn) {
      openTranslateModal(translateBtn.dataset.slug, translateBtn.dataset.title);
    }
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
  $("#cancel-btn").addEventListener("click", cancelJob);
  $("#cancel-btn").style.display = "none";
  $("#translate-modal-close").addEventListener("click", closeTranslateModal);
  $("#translate-modal-cancel").addEventListener("click", closeTranslateModal);
  $("#translate-modal-apply").addEventListener("click", applyTranslate);
  $("#translate-modal").addEventListener("click", (event) => {
    if (event.target.id === "translate-modal") closeTranslateModal();
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
    if (event.key === "Escape") {
      closeVolumeModal();
      closeTranslateModal();
    }
  });
});