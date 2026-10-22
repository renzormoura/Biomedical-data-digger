/* Efeitos compartilhados pelas duas telas (navegador de artigos e Laboratório de IA): paleta de comandos (Ctrl/Cmd+K) e brilho que
   segue o cursor. Sem dependências. A parte pura (busca de comandos) é testada em Node; o resto só roda no navegador. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else {
    root.NexusFx = api;
    if (root.document) {
      if (root.document.readyState === "loading") root.document.addEventListener("DOMContentLoaded", () => api.start(root));
      else api.start(root);
    }
  }
})(typeof self !== "undefined" ? self : this, function () {
  const fold = (text) => String(text || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();

  /** Comandos que casam com a consulta (sem acento, por prefixo da palavra ou trecho), os melhores primeiro. */
  function filterCommands(commands, query) {
    const q = fold(query);
    if (!q) return commands.slice();
    const scored = [];
    commands.forEach((command, order) => {
      const label = fold(command.label);
      const words = label.split(/[^a-z0-9]+/);
      const keys = (command.keys || []).map(fold);
      let score = -1;
      if (label.startsWith(q)) score = 0;
      else if (words.some((word) => word.startsWith(q))) score = 1;
      else if (label.includes(q)) score = 2;
      else if (keys.some((key) => key.startsWith(q) || key.includes(q))) score = 3;
      if (score >= 0) scored.push({ command, score, order });
    });
    return scored.sort((a, b) => a.score - b.score || a.order - b.order).map((item) => item.command);
  }

  /** Lista que a paleta mostra: os comandos que casam e, no fim, "Buscar «texto»" quando a pessoa digitou algo. */
  function paletteItems(commands, query, searchHref) {
    const items = filterCommands(commands, query);
    const text = String(query || "").trim();
    if (text.length >= 2) items.push({ id: "search-text", label: `Buscar artigos: “${text}”`, href: searchHref(text) });
    return items;
  }

  /** Move a seleção com as setas, dando a volta nas pontas. */
  function moveIndex(index, delta, length) {
    if (!length) return 0;
    return (((index + delta) % length) + length) % length;
  }

  const SPOT = ".card, .feed-card, .feature, .gplan-card, .plan-card, .panel:not([role=\"tabpanel\"]), .bento-tile, .lib-card, .list-block, .results .result";

  function start(win) {
    const doc = win.document;
    const home = win.location.pathname === "/" ? "" : "/";  // na tela de IA, os atalhos voltam para "/#/..."
    const route = (hash) => `${home}#/${hash}`;
    const commands = [
      { id: "home", label: "Início", keys: ["painel", "home"], href: route("") },
      { id: "search", label: "Buscar artigos", keys: ["pesquisar", "busca"], href: route("busca") },
      { id: "feed", label: "Abrir o feed de novidades", keys: ["noticias", "feed"], href: route("feed") },
      { id: "library", label: "Minha biblioteca", keys: ["salvos", "listas", "artigos salvos"], href: route("biblioteca") },
      { id: "reports", label: "Relatórios de tema", keys: ["relatorio", "documento"], href: route("relatorio") },
      { id: "interests", label: "Interesses e alertas", keys: ["avisos", "sino", "notificacoes"], href: route("perfil/interesses") },
      { id: "profile", label: "Meu perfil e conta", keys: ["conta", "senha", "nome"], href: route("perfil") },
      { id: "plans", label: "Ver planos", keys: ["assinatura", "preco", "pro", "max", "pix"], href: route("planos") },
      { id: "lab", label: "Laboratório de IA", keys: ["ia", "analise", "resumo"], href: "/ia" },
      { id: "theme", label: "Alternar tema claro ou escuro", keys: ["tema", "escuro", "claro"], action: () => { const button = doc.getElementById("theme-toggle"); if (button) button.click(); } },
    ];

    // ---- brilho que segue o cursor nos cartoes e blocos
    doc.addEventListener("pointermove", (event) => {
      if (event.pointerType === "touch") return;
      const host = event.target.closest && event.target.closest(SPOT);
      if (!host) return;
      const box = host.getBoundingClientRect();
      host.style.setProperty("--mx", `${event.clientX - box.left}px`);
      host.style.setProperty("--my", `${event.clientY - box.top}px`);
    }, { passive: true });

    // ---- paleta de comandos
    let dialog = null;
    let input = null;
    let list = null;
    let items = [];
    let selected = 0;
    let returnTo = null;
    const el = (tag, className, text) => { const node = doc.createElement(tag); if (className) node.className = className; if (text) node.textContent = text; return node; };
    const searchHref = (text) => `${home}#/busca?q=${encodeURIComponent(text)}`;

    function paint() {
      list.replaceChildren(...items.map((item, i) => {
        const row = el("li", `pal-item${i === selected ? " is-selected" : ""}`, item.label);
        row.id = `pal-opt-${i}`;
        row.setAttribute("role", "option");
        row.setAttribute("aria-selected", String(i === selected));
        row.addEventListener("pointermove", () => { if (selected !== i) { selected = i; paint(); } });
        row.addEventListener("click", () => run(i));
        return row;
      }));
      if (!items.length) list.append(el("li", "pal-empty", "Nada encontrado"));
      input.setAttribute("aria-activedescendant", items.length ? `pal-opt-${selected}` : "");
      const current = list.querySelector(".is-selected");
      if (current && current.scrollIntoView) current.scrollIntoView({ block: "nearest" });
    }
    function close() {
      if (!dialog || dialog.hidden) return;
      dialog.hidden = true;
      doc.body.classList.remove("pal-open");
      if (returnTo && returnTo.focus) returnTo.focus();
    }
    function run(i) {
      const item = items[i];
      if (!item) return;
      close();
      if (item.action) item.action();
      else if (item.href) win.location.href = item.href;
    }
    function build() {
      dialog = el("div", "pal");
      dialog.hidden = true;
      dialog.setAttribute("role", "dialog");
      dialog.setAttribute("aria-modal", "true");
      dialog.setAttribute("aria-label", "Paleta de comandos");
      const box = el("div", "pal-box");
      input = el("input", "pal-input");
      input.type = "text";
      input.placeholder = "Ir para… ou digite um tema para buscar";
      input.autocomplete = "off";
      input.setAttribute("role", "combobox");
      input.setAttribute("aria-expanded", "true");
      input.setAttribute("aria-controls", "pal-list");
      input.setAttribute("aria-label", "Comando ou busca");
      list = el("ul", "pal-list");
      list.id = "pal-list";
      list.setAttribute("role", "listbox");
      const foot = el("div", "pal-foot");
      ["↑↓ escolher", "↵ abrir", "esc fechar"].forEach((text) => foot.append(el("span", "", text)));
      box.append(input, list, foot);
      dialog.append(box);
      dialog.addEventListener("pointerdown", (event) => { if (event.target === dialog) close(); });
      input.addEventListener("input", () => { items = paletteItems(commands, input.value, searchHref); selected = 0; paint(); });
      input.addEventListener("keydown", (event) => {
        if (event.key === "ArrowDown") { event.preventDefault(); selected = moveIndex(selected, 1, items.length); paint(); }
        else if (event.key === "ArrowUp") { event.preventDefault(); selected = moveIndex(selected, -1, items.length); paint(); }
        else if (event.key === "Enter") { event.preventDefault(); run(selected); }
        else if (event.key === "Escape") { event.preventDefault(); close(); }
        else if (event.key === "Tab") { event.preventDefault(); }  // o foco fica no campo enquanto a paleta esta aberta
      });
      doc.body.append(dialog);
    }
    function open() {
      if (!dialog) build();
      returnTo = doc.activeElement;
      dialog.hidden = false;
      doc.body.classList.add("pal-open");
      input.value = "";
      items = paletteItems(commands, "", searchHref);
      selected = 0;
      paint();
      input.focus();
    }
    function toggle() { if (dialog && !dialog.hidden) close(); else open(); }

    doc.addEventListener("keydown", (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") { event.preventDefault(); toggle(); return; }
      // "/" leva ao campo de busca (e abre a busca, se a pessoa estiver em outra tela do navegador de artigos)
      if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey || (dialog && !dialog.hidden)) return;
      const target = event.target;
      if (target && (/^(input|textarea|select)$/i.test(target.tagName) || target.isContentEditable)) return;
      const focusSearch = () => { const field = doc.getElementById("q") || doc.getElementById("home-q"); if (field) { field.focus(); field.select(); return true; } return false; };
      if (focusSearch()) event.preventDefault();
      else if (home === "") { event.preventDefault(); win.location.hash = "#/busca"; win.setTimeout(focusSearch, 450); }
    });
    const button = doc.getElementById("palette-button");
    if (button) button.addEventListener("click", toggle);
  }

  return { filterCommands, paletteItems, moveIndex, fold, start };
});
