"use strict";
// Alterna o tema; sem escolha salva, vale a preferência do sistema (prefers-color-scheme).
(function () {
  const root = document.documentElement;
  try {
    const saved = localStorage.getItem("bdd.theme");
    if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);
  } catch (error) { /* armazenamento indisponível: segue o sistema */ }
  const button = document.getElementById("theme-toggle");
  if (!button) return;
  button.addEventListener("click", () => {
    const current = root.getAttribute("data-theme") || (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
    const next = current === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    try { localStorage.setItem("bdd.theme", next); } catch (error) { /* ignora */ }
  });

  // Seletor de formato de citação (maquete)
  const citation = document.getElementById("citation-text");
  const buttons = document.querySelectorAll("[data-cite]");
  const styles = {
    ABNT: "SILVA, A. B.; COSTA, C. D.; LIMA, E. F. Duração de corticoide guiada por eosinófilos na exacerbação de asma. Revista Exemplo de Medicina, v. 12, n. 3, p. 101-110, 2026.",
    APA: "Silva, A. B., Costa, C. D., & Lima, E. F. (2026). Duração de corticoide guiada por eosinófilos na exacerbação de asma. Revista Exemplo de Medicina, 12(3), 101-110.",
    Vancouver: "Silva AB, Costa CD, Lima EF. Duração de corticoide guiada por eosinófilos na exacerbação de asma. Rev Exemplo Med. 2026;12(3):101-10.",
  };
  buttons.forEach((b) => b.addEventListener("click", () => {
    buttons.forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    if (citation) citation.textContent = styles[b.dataset.cite] || "";
  }));
})();
