"use strict";

async function refreshLibrary() {
  const container = $("#cover-grid");
  try {
    const novels = await api("/api/novels");
    novels.sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""));
    if (!novels.length) {
      container.innerHTML = `
        <div class="empty">
          <span class="empty-icon">&#128214;</span>
          Aún no hay novelas descargadas.
          <div class="empty-actions">
            <a class="btn btn-primary" href="/">Ir a descargar</a>
          </div>
        </div>`;
      return;
    }
    container.innerHTML = novels.map((n) => coverCard(n)).join("");
  } catch (_) {}
}

document.addEventListener("DOMContentLoaded", async () => {
  setupNavActive();
  await loadConfig();
  refreshLibrary();
  setInterval(refreshLibrary, 15000);
});