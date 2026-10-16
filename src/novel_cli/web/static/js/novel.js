"use strict";

/* ==========================================================================
   novel.js — ficha de novela: cabecera, acciones agrupadas y EPUBs
   spec 0.3.0/07
   ========================================================================== */

let novelState = { slug: null, data: null, target_language: null, size: null };

function getSlug() {
  const parts = location.pathname.split("/").filter(Boolean);
  return parts.length ? decodeURIComponent(parts[parts.length - 1]) : "";
}

async function loadNovel() {
  const slug = getSlug();
  if (!slug) {
    renderNotFound("Novela no indicada en la URL");
    return;
  }
  try {
    const n = await api(`/api/novels/${encodeURIComponent(slug)}`);
    novelState.data = n;
    renderHero(n);
    renderActions(n);
    renderEpubs(n);
    document.title = `${n.title} · novel-cli web`;
  } catch (e) {
    renderNotFound(e.message);
  }
}

window.refreshAfterJob = loadNovel;

function renderHero(n) {
  $("#novel-cover").innerHTML = coverMarkup(n);
  $("#novel-title").textContent = n.title;
  $("#novel-author").textContent = n.author || "";

  const meta = [];
  if (n.source_pdf) meta.push(`<span class="badge badge-info">PDF</span>`);
  meta.push(
    `<span class="badge ${n.translated ? "badge-success" : "badge-neutral"}">${
      n.translated ? `${languageLabel(n.translated_language || "es")} + original` : "solo original"
    }</span>`,
  );
  const volCount = (n.epub_original || []).length;
  if (volCount) meta.push(`<span class="chip">${volCount} vol.</span>`);
  meta.push(
    `<span class="chip">${n.volume_size == null ? "tomo único" : `${n.volume_size} cap/tomo`}</span>`,
  );
  $("#novel-meta").innerHTML = meta.join(" ");

  const pct =
    n.chapters_total > 0
      ? Math.round((n.chapters_downloaded / n.chapters_total) * 100)
      : 0;
  $("#novel-progress").innerHTML = `
    <div class="novel-stats">
      <span>${n.chapters_downloaded || 0} / ${n.chapters_total || 0} capítulos</span>
      <span>${pct}%</span>
    </div>
    <div class="mini-bar"><div class="mini-fill" style="width:${pct}%"></div></div>`;

  const emptyNums = (n.chapters_empty_nums || []).slice(0, 20);
  $("#novel-empty-warning").innerHTML =
    n.chapters_empty > 0
      ? `<div class="empty-warning" title="${escapeHtml(emptyNums.join(", "))}">${icon("warning")} ${n.chapters_empty} capítulo(s) vacío(s) pendientes de reintento</div>`
      : "";
}

function actionBtn(label, iconName, slug, title, { cls = "", variant = "secondary" } = {}) {
  return `
    <button class="btn btn-${variant} ${cls}" data-slug="${encodeURIComponent(slug)}"
      data-title="${escapeHtml(title)}" data-label="${label}" data-loading="…">
      ${iconName ? icon(iconName) : ""}<span class="btn-label">${label}</span>
    </button>`;
}

function renderActions(n) {
  const slug = n.slug;
  const title = n.title;
  const volumeSize = n.volume_size == null ? "ALL" : n.volume_size;
  const primary = [];
  const secondary = [];
  const translationBtn = (variant) =>
    n.translated
      ? actionBtn("Re-traducir", "pencil", slug, title, { cls: "btn-retranslate", variant })
      : actionBtn("Traducir", "translate", slug, title, { cls: "btn-translate", variant });

  if (!n.source_pdf) {
    primary.push(actionBtn("Actualizar", "refresh", slug, title, { cls: "btn-sync", variant: "primary" }));
    secondary.push(translationBtn("secondary"));
  } else {
    primary.push(translationBtn("primary"));
  }
  secondary.push(`
    <button class="btn btn-secondary btn-volumes" data-slug="${encodeURIComponent(slug)}"
      data-title="${escapeHtml(title)}" data-size="${volumeSize}">
      ${icon("file-text")}<span class="btn-label">Tomos: ${volumeSize}</span>
    </button>`);
  secondary.push(
    actionBtn("Regenerar EPUBs", "rebuild", slug, title, { cls: "btn-rebuild" }),
  );
  if (n.source_url) {
    secondary.push(
      `<a class="btn btn-secondary" href="${escapeHtml(n.source_url)}" target="_blank" rel="noopener">${icon("external")} Fuente</a>`,
    );
  }
  $("#novel-primary").innerHTML = primary.join(" ");
  $("#novel-secondary").innerHTML = secondary.join(" ");
}

function renderEpubs(n) {
  const groups = [];
  const orig = (n.epub_original || []).map((name) => epubCard(n.slug, name)).join("");
  const trans = (n.epub_translated || []).map((name) => epubCard(n.slug, name)).join("");
  if (orig) {
    groups.push(`<div class="epub-group"><h3>Original</h3><div class="epub-grid">${orig}</div></div>`);
  }
  if (trans) {
    const lang = (n.translated_language || "es").toUpperCase();
    groups.push(
      `<div class="epub-group"><h3>Traducción (${lang})</h3><div class="epub-grid">${trans}</div></div>`,
    );
  }
  $("#epub-groups").innerHTML = groups.length
    ? groups.join("")
    : `<div class="empty"><span class="empty-icon" data-icon="file-text"></span><p>Aún no hay EPUBs generados.</p></div>`;
  hydrateIcons($("#epub-groups"));
}

function epubCard(slug, name) {
  return `
    <div class="epub-card">
      <span class="epub-name" title="${escapeHtml(name)}">${escapeHtml(name)}</span>
      <a class="btn btn-secondary" href="/api/novels/${encodeURIComponent(slug)}/epub/${encodeURIComponent(name)}" download="${escapeHtml(name)}">
        ${icon("download")} Descargar
      </a>
    </div>`;
}

function renderNotFound(msg) {
  $("#novel-cover").innerHTML = `<div class="cover placeholder">${icon("book")}</div>`;
  $("#novel-title").textContent = "Novela no encontrada";
  $("#novel-author").textContent = "";
  $("#novel-meta").innerHTML = "";
  $("#novel-progress").innerHTML = "";
  $("#novel-empty-warning").innerHTML = `<p class="section-desc">${escapeHtml(msg || "Revisa el enlace o vuelve a la biblioteca.")}</p>`;
  $("#novel-primary").innerHTML = `<a class="btn btn-secondary" href="/biblioteca">Volver a la biblioteca</a>`;
  $("#novel-secondary").innerHTML = "";
  $("#epub-groups").innerHTML = "";
  document.title = "Novela no encontrada · novel-cli web";
}

/* --------------------------------------------------------------------------
   Modal de idioma
   -------------------------------------------------------------------------- */
function openTranslateModal(slug, title) {
  novelState.slug = slug;
  novelState.target_language = null;
  $("#translate-modal-novel").textContent = title;
  $("#translate-modal-apply").disabled = true;
  const langs = (state.config && state.config.translate_languages) || {};
  $("#translate-pills").innerHTML = Object.entries(langs)
    .map(([code, label]) => `<button type="button" class="pill" data-lang="${code}">${label}</button>`)
    .join("");
  $$("#translate-pills .pill").forEach((pill) =>
    pill.addEventListener("click", () => selectTranslatePill(pill)),
  );
  $("#translate-modal").hidden = false;
}

function closeTranslateModal() {
  $("#translate-modal").hidden = true;
}

function selectTranslatePill(pill) {
  $$("#translate-pills .pill").forEach((p) => p.classList.remove("active"));
  pill.classList.add("active");
  novelState.target_language = pill.dataset.lang;
  $("#translate-modal-apply").disabled = false;
}

async function applyTranslate() {
  const { slug, target_language: lang } = novelState;
  if (!slug || !lang) return;
  const btn = $("#translate-modal-apply");
  btn.disabled = true;
  try {
    const { job_id } = await api(`/api/novels/${slug}/retranslate`, {
      method: "POST",
      body: { target_language: lang },
    });
    closeTranslateModal();
    attachJob(job_id, $("#novel-title").textContent);
    showToast(`Traduciendo a ${languageLabel(lang)}`, "info");
  } catch (e) {
    showToast(e.message, "error");
    btn.disabled = false;
  }
}

/* --------------------------------------------------------------------------
   Regenerar EPUBs
   -------------------------------------------------------------------------- */
async function rebuildNovel(btn) {
  if (await hasActiveJob()) {
    showToast("Ya hay un job en curso. Espera a que termine.", "info");
    return;
  }
  setButtonLoading(btn, true);
  try {
    await api(`/api/novels/${btn.dataset.slug}/rebuild`, { method: "POST" });
    showToast("EPUBs regenerados", "success");
    loadNovel();
  } catch (e) {
    showToast(e.message, "error");
  } finally {
    setButtonLoading(btn, false);
  }
}

/* --------------------------------------------------------------------------
   Modal de tamaño de tomo
   -------------------------------------------------------------------------- */
function openVolumeModal(slug, title, currentSize) {
  novelState.slug = slug;
  novelState.size = null;
  $("#volume-modal-novel").textContent = title;
  $("#volume-modal-apply").disabled = true;
  $$("#volume-pills .pill").forEach((pill) => {
    const active =
      currentSize == null
        ? pill.dataset.size === "null"
        : pill.dataset.size === String(currentSize);
    pill.classList.toggle("active", active);
  });
  $("#volume-modal").hidden = false;
}

function closeVolumeModal() {
  $("#volume-modal").hidden = true;
}

function selectVolumePill(pill) {
  $$("#volume-pills .pill").forEach((p) => p.classList.remove("active"));
  pill.classList.add("active");
  novelState.size = pill.dataset.size === "null" ? null : parseInt(pill.dataset.size, 10);
  $("#volume-modal-apply").disabled = false;
}

async function applyVolumeSize() {
  const { slug, size } = novelState;
  if (!slug) return;
  const btn = $("#volume-modal-apply");
  btn.disabled = true;
  btn.classList.add("loading");
  try {
    await api(`/api/novels/${slug}/volume-size`, {
      method: "POST",
      body: { volume_size: size },
    });
    closeVolumeModal();
    showToast("EPUBs regenerados", "success");
    loadNovel();
  } catch (e) {
    showToast(e.message, "error");
    btn.disabled = false;
  } finally {
    btn.classList.remove("loading");
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  hydrateIcons();
  await loadConfig();
  loadNovel();

  $("#novel-primary").addEventListener("click", onActionClick);
  $("#novel-secondary").addEventListener("click", onActionClick);

  $("#translate-modal-close").addEventListener("click", closeTranslateModal);
  $("#translate-modal-cancel").addEventListener("click", closeTranslateModal);
  $("#translate-modal-apply").addEventListener("click", applyTranslate);
  $("#translate-modal").addEventListener("click", (e) => {
    if (e.target.id === "translate-modal") closeTranslateModal();
  });
  $("#volume-modal-close").addEventListener("click", closeVolumeModal);
  $("#volume-modal-cancel").addEventListener("click", closeVolumeModal);
  $("#volume-modal-apply").addEventListener("click", applyVolumeSize);
  $("#volume-modal").addEventListener("click", (e) => {
    if (e.target.id === "volume-modal") closeVolumeModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      closeVolumeModal();
      closeTranslateModal();
    }
  });
});

function onActionClick(event) {
  const t = event.target.closest("button");
  if (!t) return;
  if (t.classList.contains("btn-translate")) {
    openTranslateModal(t.dataset.slug, t.dataset.title);
  } else if (t.classList.contains("btn-sync")) {
    syncNovel(t);
  } else if (t.classList.contains("btn-retranslate")) {
    retranslateNovel(t);
  } else if (t.classList.contains("btn-volumes")) {
    openVolumeModal(
      t.dataset.slug,
      t.dataset.title,
      t.dataset.size === "ALL" ? null : parseInt(t.dataset.size, 10),
    );
  } else if (t.classList.contains("btn-rebuild")) {
    rebuildNovel(t);
  }
}
