"use strict";

/* ==========================================================================
   library.js — biblioteca: buscar, filtrar, ordenar y densidad
   spec 0.3.0/07
   ========================================================================== */

const LIB_PREFS_KEY = "novel_web_library";

const libraryState = {
  novels: [],
  filter: "all",
  sort: "recent",
  density: "grid",
  query: "",
};

function loadLibraryPrefs() {
  try {
    const saved = JSON.parse(localStorage.getItem(LIB_PREFS_KEY) || "null");
    if (saved) Object.assign(libraryState, saved, { novels: [], query: "" });
  } catch (_) {}
}

function saveLibraryPrefs() {
  try {
    localStorage.setItem(
      LIB_PREFS_KEY,
      JSON.stringify({
        filter: libraryState.filter,
        sort: libraryState.sort,
        density: libraryState.density,
      }),
    );
  } catch (_) {}
}

function applyLibraryPrefsToUI() {
  $$("#lib-filter button").forEach((b) =>
    b.setAttribute("aria-pressed", b.dataset.filter === libraryState.filter ? "true" : "false"),
  );
  $$("#lib-density button").forEach((b) =>
    b.setAttribute("aria-pressed", b.dataset.density === libraryState.density ? "true" : "false"),
  );
  const sort = $("#lib-sort");
  if (sort) sort.value = libraryState.sort;
}

function matchesFilter(n) {
  switch (libraryState.filter) {
    case "translated":
      return !!n.translated;
    case "empty":
      return (n.chapters_empty || 0) > 0;
    case "pdf":
      return !!n.source_pdf;
    default:
      return true;
  }
}

function matchesQuery(n) {
  const q = libraryState.query.trim().toLowerCase();
  if (!q) return true;
  return (
    (n.title || "").toLowerCase().includes(q) ||
    (n.author || "").toLowerCase().includes(q)
  );
}

function renderLibrary() {
  const container = $("#cover-grid");
  if (!container) return;
  const filtered = libraryState.novels
    .filter((n) => matchesFilter(n) && matchesQuery(n))
    .sort((a, b) =>
      libraryState.sort === "title"
        ? (a.title || "").localeCompare(b.title || "")
        : (b.updated_at || "").localeCompare(a.updated_at || ""),
    );

  container.classList.toggle("list", libraryState.density === "list");

  const controls = $(".library-controls");
  if (controls) controls.hidden = libraryState.novels.length === 0;

  const count = $("#lib-count");
  if (count) {
    count.textContent = filtered.length
      ? `${filtered.length} de ${libraryState.novels.length}`
      : "";
  }

  if (!libraryState.novels.length) {
    container.innerHTML = `
      <div class="empty">
        <span class="empty-icon" data-icon="book"></span>
        <p>Aún no hay novelas descargadas.</p>
        <div class="empty-actions"><a class="btn btn-primary" href="/">Ir a descargar</a></div>
      </div>`;
  } else if (!filtered.length) {
    container.innerHTML = `
      <div class="empty">
        <span class="empty-icon" data-icon="search"></span>
        <p>Ninguna novela coincide con el filtro.</p>
      </div>`;
  } else {
    container.innerHTML = filtered.map((n) => coverCard(n)).join("");
  }
  hydrateIcons(container);
}

async function refreshLibrary() {
  try {
    libraryState.novels = await api("/api/novels");
    renderLibrary();
  } catch (_) {}
}

function setupLibraryControls() {
  const search = $("#lib-search");
  if (search) {
    let t = null;
    search.addEventListener("input", () => {
      clearTimeout(t);
      t = setTimeout(() => {
        libraryState.query = search.value;
        renderLibrary();
      }, 120);
    });
  }
  const filter = $("#lib-filter");
  if (filter) {
    filter.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-filter]");
      if (!btn) return;
      libraryState.filter = btn.dataset.filter;
      saveLibraryPrefs();
      applyLibraryPrefsToUI();
      renderLibrary();
    });
  }
  const sort = $("#lib-sort");
  if (sort) {
    sort.addEventListener("change", () => {
      libraryState.sort = sort.value;
      saveLibraryPrefs();
      renderLibrary();
    });
  }
  const density = $("#lib-density");
  if (density) {
    density.addEventListener("click", (e) => {
      const btn = e.target.closest("button[data-density]");
      if (!btn) return;
      libraryState.density = btn.dataset.density;
      saveLibraryPrefs();
      applyLibraryPrefsToUI();
      renderLibrary();
    });
  }
}

window.refreshAfterJob = refreshLibrary;

document.addEventListener("DOMContentLoaded", async () => {
  hydrateIcons();
  loadLibraryPrefs();
  applyLibraryPrefsToUI();
  setupLibraryControls();
  await loadConfig();
  refreshLibrary();
  setInterval(refreshLibrary, 15000);
});
