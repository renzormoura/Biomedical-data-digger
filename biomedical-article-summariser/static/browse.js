/* Navegador de artigos — telas e interação.
   Tudo é montado com DOM (textContent), nunca com innerHTML de dados externos; links só http(s). */
(() => {
  "use strict";

  const Lib = window.BrowseLib;
  const $app = document.getElementById("app");
  const THEME_KEY = "bdd.theme"; // compartilhado com a página de IA
  const PAGE_SIZE = 10;
  // ------------------------------------------------------------------ DOM
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") el.className = value;
      else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2), value);
      else if (value === true) el.setAttribute(key, "");
      else el.setAttribute(key, value);
    }
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === false) continue;
      el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return el;
  }
  function mount(parent, ...kids) {
    parent.replaceChildren(...kids.flat(Infinity)
      .filter((k) => k !== null && k !== undefined && k !== false)
      .map((k) => (k.nodeType ? k : document.createTextNode(String(k)))));
  }
  const loading = (text = "Carregando…") => h("div", { class: "loading" }, h("div", { class: "spinner", "aria-hidden": "true" }), h("span", {}, text));
  const errorBox = (message) => h("div", { class: "error-box", role: "alert" }, h("strong", {}, "Não foi possível concluir. "), message);
  const SVG_NS = "http://www.w3.org/2000/svg";
  function icon(name, filled = false) {
    const svg = document.createElementNS(SVG_NS, "svg");
    svg.setAttribute("class", `icon${filled ? " is-filled" : ""}`);
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS(SVG_NS, "use");
    use.setAttribute("href", `#i-${name}`);
    svg.append(use);
    return svg;
  }
  const setTitle = (text) => { document.title = `${text} — Biomedical Data Digger`; };

  let toastTimer;
  function toast(message) {
    const el = document.getElementById("toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 2400);
  }
  async function copyText(text, ok = "Copiado!") {
    try { await navigator.clipboard.writeText(text); } catch {
      const area = h("textarea", { "aria-hidden": "true" });
      area.value = text; document.body.append(area); area.select();
      try { document.execCommand("copy"); } catch { /* sem suporte */ }
      area.remove();
    }
    toast(ok);
  }

  // ------------------------------------------------------------------ API
  async function api(path, { method = "GET", body, signal } = {}) {
    let response;
    try {
      response = await fetch(path, {
        method, signal, credentials: "same-origin",
        headers: body === undefined ? {} : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (error) {
      if (error.name === "AbortError") throw error;
      throw new Error("Sem conexão com o servidor. Verifique a internet e tente novamente.");
    }
    let data = {};
    try { data = await response.json(); } catch { /* corpo vazio */ }
    if (!response.ok) {
      const error = new Error(data.error || (Array.isArray(data.detail) ? "Dados inválidos. Revise os campos." : `Erro ${response.status}.`));
      error.status = response.status;
      throw error;
    }
    return data;
  }

  let optionsPromise;
  const loadOptions = () => {
    optionsPromise ||= api("/api/discover/options").catch((error) => { optionsPromise = undefined; throw error; });
    return optionsPromise;
  };

  // ------------------------------------------------------------------ tema
  const systemTheme = () => (window.matchMedia && matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  const readTheme = () => { try { return JSON.parse(localStorage.getItem(THEME_KEY)) || systemTheme(); } catch { return systemTheme(); } };
  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    const toggle = document.getElementById("theme-toggle");
    toggle.setAttribute("aria-label", theme === "dark" ? "Mudar para o tema claro" : "Mudar para o tema escuro");
    toggle.title = toggle.getAttribute("aria-label");
  }
  applyTheme(readTheme());
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    try { localStorage.setItem(THEME_KEY, JSON.stringify(next)); } catch { /* modo privado */ }
  });

  // ------------------------------------------------------------------ conta
  const accountButton = document.getElementById("account-button");
  const dialog = document.getElementById("auth-dialog");
  const authError = document.getElementById("auth-error");
  const logoutButton = document.getElementById("logout-button");
  const profileLink = document.getElementById("profile-link");
  const session = { user: accountButton.dataset.user || "", profile: accountButton.dataset.profile || "", healthPack: accountButton.dataset.healthPack !== "0" };

  let userHook = null; // o sininho se registra aqui depois de montado
  function setUser(user) {
    session.user = user || "";
    document.getElementById("account-label").textContent = user || "Entrar";
    logoutButton.hidden = !user;
    profileLink.hidden = !user;
    dialog.querySelectorAll(".field, [data-auth='login'], [data-auth='register']").forEach((el) => { el.hidden = Boolean(user); });
    if (userHook) userHook();
  }
  setUser(session.user);

  // ------------------------------------------------------------------ avisos (sininho)
  const CHECK_EVERY_MS = 15 * 60 * 1000;
  const bell = { items: [], unread: 0, hasInterests: false, timer: null, busy: false };
  const bellWrap = document.getElementById("bell-wrap");
  const bellButton = document.getElementById("bell-button");
  const bellCount = document.getElementById("bell-count");
  const alertsPanel = document.getElementById("alerts-panel");

  function paintBell() {
    bellCount.hidden = bell.unread === 0;
    bellCount.textContent = bell.unread > 9 ? "9+" : String(bell.unread);
    bellButton.setAttribute("aria-label", bell.unread ? `Avisos de artigos novos: ${bell.unread} não lidos` : "Avisos de artigos novos");
    if (!alertsPanel.hidden) paintPanel();
  }
  function takeBox(data) {
    bell.items = data.alerts || [];
    bell.unread = data.unread || 0;
    paintBell();
  }
  async function alertAction(path, options) {
    try { takeBox(await api(path, options)); } catch (error) { if (error.status !== 401) toast(error.message); }
  }
  const KIND_BADGES = { retratacao: "Retratado", regulatorio: "Regulatório", "relatorio-lista": "Relatório" };
  function paintPanel() {
    const rows = bell.items.map((item) => h("li", { class: `alert-row${item.read ? "" : " is-unread"}${item.priority >= 2 ? " is-important" : ""}` },
      KIND_BADGES[item.kind] ? h("span", { class: "alert-kind" }, KIND_BADGES[item.kind]) : null,
      h("a", {
        href: item.href,
        onclick: () => { closePanel(); if (!item.read) alertAction("/api/alerts/read", { method: "POST", body: { id: item.id } }); },
      }, item.title),
      h("small", { class: "muted alert-body" }, item.work ? [metaLine(item.work), item.topic].filter(Boolean).join(" · ") : item.body),
      h("button", { type: "button", class: "alert-dismiss", "aria-label": `Dispensar aviso: ${item.title}`, onclick: () => alertAction(`/api/alerts?id=${encodeURIComponent(item.id)}`, { method: "DELETE" }) }, icon("x"))));
    mount(alertsPanel,
      h("div", { class: "alerts-head" }, h("strong", {}, "Avisos"),
        bell.unread ? h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: () => alertAction("/api/alerts/read", { method: "POST", body: {} }) }, "Marcar como lidos") : null),
      rows.length ? h("ul", { class: "plain-list alert-list" }, rows)
        : h("p", { class: "muted alerts-empty" }, "Nenhum aviso por enquanto. Avisamos de artigos retratados que você guarda, de mudanças regulatórias nas substâncias dos seus relatórios, de novidades nas listas dos relatórios e de artigos novos nos seus interesses."),
      h("div", { class: "alerts-foot" },
        h("a", { class: "btn btn-secondary btn-sm", href: "#/perfil/notificacoes", onclick: closePanel }, "Notificações"),
        h("a", { class: "btn btn-ghost btn-sm", href: "#/perfil/interesses", onclick: closePanel }, bell.hasInterests ? "Interesses" : "Escolher interesses"),
        h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: () => runCheck(true) }, "Verificar agora")));
  }
  function openPanel() { paintPanel(); alertsPanel.hidden = false; bellButton.setAttribute("aria-expanded", "true"); }
  function closePanel() { alertsPanel.hidden = true; bellButton.setAttribute("aria-expanded", "false"); }
  bellButton.addEventListener("click", () => (alertsPanel.hidden ? openPanel() : closePanel()));
  document.addEventListener("click", (event) => { if (!alertsPanel.hidden && !bellWrap.contains(event.target)) closePanel(); });
  document.addEventListener("keydown", (event) => { if (event.key === "Escape" && !alertsPanel.hidden) { closePanel(); bellButton.focus(); } });

  /** Procura artigos novos (o servidor respeita o intervalo mínimo) e avisa só quando há novidade. */
  async function runCheck(force = false) {
    if (!session.user || bell.busy) return;
    bell.busy = true;
    try {
      const result = await api("/api/alerts/check", { method: "POST", body: { force } });
      takeBox(result);
      if (result.new > 0) toast(result.new === 1 ? "1 aviso novo no sininho." : `${result.new} avisos novos no sininho.`);
      else if (force && result.ran) toast(result.baseline ? "Pronto: guardamos os artigos de hoje. Você será avisado dos próximos." : "Nenhum aviso novo por enquanto.");
      else if (force && result.reason === "intervalo") toast("Você verificou há pouco. Tente novamente em alguns minutos.");
      else if (force && result.reason === "fontes") toast("As fontes não responderam agora. Tente mais tarde.");
    } catch (error) {
      if (error.status === 401) { setUser(""); } else if (force) toast(error.message);
    } finally { bell.busy = false; }
  }
  async function syncBell() {
    clearInterval(bell.timer);
    bellWrap.hidden = !session.user;
    closePanel();
    if (!session.user) { bell.items = []; bell.unread = 0; bell.hasInterests = false; paintBell(); return; }
    try {
      const [box, prefs] = await Promise.all([api("/api/alerts"), api("/api/interests")]);
      bell.hasInterests = prefs.topics.length > 0 || prefs.terms.length > 0;
      takeBox(box);
    } catch { return; }
    runCheck(false);
    bell.timer = setInterval(() => { if (!document.hidden) runCheck(false); }, CHECK_EVERY_MS);
  }
  userHook = () => { syncBell(); syncProfile(); };
  syncBell();


  function openAuth(hint) {
    authError.hidden = true;
    document.getElementById("auth-hint").textContent = hint || "Entre para salvar artigos, criar listas e exportar. Buscar e ler não exige conta.";
    if (!dialog.open) dialog.showModal();
  }
  /** Garante conta para ações que a exigem; abre o diálogo se faltar. */
  function requireUser(message) {
    if (session.user) return true;
    openAuth(message);
    return false;
  }
  accountButton.addEventListener("click", () => openAuth());

  async function authenticate(kind) {
    const email = document.getElementById("auth-email").value.trim();
    const password = document.getElementById("auth-password").value;
    if (!email || !password) { authError.textContent = "Informe e-mail e senha."; authError.hidden = false; return; }
    try {
      const data = await api(`/api/auth/${kind}`, { method: "POST", body: { email, password } });
      document.getElementById("auth-password").value = "";
      setUser(data.user);
      dialog.close();
      toast(kind === "register" ? "Conta criada!" : "Login realizado!");
      render(); // reabre a tela atual já com os dados da conta
    } catch (error) {
      authError.textContent = error.message;
      authError.hidden = false;
    }
  }
  dialog.querySelector("[data-auth='login']").addEventListener("click", () => authenticate("login"));
  dialog.querySelector("[data-auth='register']").addEventListener("click", () => authenticate("register"));
  dialog.querySelector("[data-auth='cancel']").addEventListener("click", () => dialog.close());
  profileLink.addEventListener("click", () => dialog.close());
  logoutButton.addEventListener("click", async () => {
    try { await api("/api/auth/logout", { method: "POST", body: {} }); } catch { /* sessão já inválida */ }
    setUser("");
    dialog.close();
    toast("Você saiu da conta.");
    render();
  });

  /** Executa uma ação da conta tratando sessão expirada e erros comuns. */
  async function guarded(action, failure = "Não foi possível concluir a ação.") {
    try {
      return await action();
    } catch (error) {
      if (error.status === 401) { setUser(""); openAuth("Sua sessão expirou. Entre novamente."); }
      else toast(error.message || failure);
      return undefined;
    }
  }

  // ------------------------------------------------------------------ navegação
  function renderBottomNav(view) {
    const items = [["#/", "Início", "", "home"], ["#/feed", "Feed", "feed", "feed"], ["#/busca", "Busca", "busca", "search"], ["#/biblioteca", "Biblioteca", "biblioteca", "bookmark"], ["#/perfil", "Perfil", "perfil", "user"]];
    mount(document.getElementById("bottomnav"), items.map(([href, label, key, name]) => h("a", {
      href, "aria-current": key === view || (key === "busca" && view === "artigo") ? "page" : null,
    }, icon(name), h("span", {}, label))));
  }

  function renderNav(view) {
    renderBottomNav(view);
    const items = [["#/", "Início", ""], ["#/feed", "Feed", "feed"], ["#/busca", "Busca", "busca"], ["#/biblioteca", "Biblioteca", "biblioteca"], ["#/perfil", "Perfil", "perfil"]];
    mount(document.getElementById("mainnav"),
      items.map(([href, label, key]) => h("a", { href, "aria-current": key === view || (key === "busca" && view === "artigo") ? "page" : null }, label)),
      h("a", { href: "/ia", title: "Resumos e análises com IA (opcional)" }, "Laboratório de IA"));
  }

  // ------------------------------------------------------------------ componentes
  function highlighted(text, query) {
    const words = [...new Set(String(query || "").split(/[^\p{L}\p{N}]+/u).filter((w) => w.length > 1))];
    if (!words.length) return text;
    const pattern = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "giu");
    return String(text).split(pattern).map((part, index) => (index % 2 ? h("mark", {}, part) : part));
  }

  function badges(work) {
    return h("div", { class: "badges" },
      (work.studyTypes || []).map((t) => h("span", { class: "badge type" }, t)),
      work.openAccess ? h("span", { class: "badge oa" }, "Acesso aberto") : h("span", { class: "badge" }, "Acesso restrito"),
      work.citedBy > 0 ? h("span", { class: "badge" }, `${Lib.formatCount(work.citedBy)} citações`) : null,
      work.language ? h("span", { class: "badge" }, work.language.toUpperCase()) : null,
      work.source ? h("span", { class: "badge" }, work.source) : null);
  }
  // metadados no padrão do Google Scholar (citation_*): o conector do Zotero e o do Mendeley leem estas tags da página do artigo
  function setCitationMeta(work) {
    clearCitationMeta();
    const tags = [["citation_title", work.title], ["citation_journal_title", work.journal], ["citation_volume", work.volume],
      ["citation_issue", work.issue], ["citation_doi", work.doi], ["citation_pmid", work.pmid], ["citation_language", work.language],
      ["citation_publication_date", (work.published || "").replace(/-/g, "/") || (work.year ? String(work.year) : "")]];
    const [first, last] = String(work.pages || "").split(/\s*[-–—]\s*/);
    tags.push(["citation_firstpage", first], ["citation_lastpage", last]);
    for (const a of work.authorList || []) tags.push(["citation_author", [a.family, a.given].filter(Boolean).join(", ")]);
    for (const k of work.keywords || []) tags.push(["citation_keywords", k]);
    for (const [name, content] of tags) {
      if (!content) continue;
      document.head.append(h("meta", { name, content, "data-citation": "" }));
    }
  }
  const clearCitationMeta = () => document.querySelectorAll("meta[data-citation]").forEach((el) => el.remove());

  const metaLine = (work) => [work.authors, work.journal, work.year].filter(Boolean).join(" · ");
  const articleHref = (work) => Lib.buildHash("/artigo", { ref: work.ref });

  // um unico ouvinte fecha qualquer seletor de lista ou painel de download aberto quando o clique cai fora dele
  document.addEventListener("click", (event) => {
    document.querySelectorAll(".save-picker:not([hidden])").forEach((picker) => {
      if (!picker.parentElement.contains(event.target)) {
        picker.hidden = true; picker.replaceChildren();
        picker.parentElement.querySelector("button")?.setAttribute("aria-expanded", "false");
      }
    });
    document.querySelectorAll(".download-panel:not([hidden])").forEach((panel) => {
      if (!panel.parentElement.contains(event.target)) { panel.hidden = true; panel.parentElement.querySelector("button")?.setAttribute("aria-expanded", "false"); }
    });
  });

  // botão "Exportar" da biblioteca e das listas: um só botão, com todas as opções agrupadas dentro
  const EXPORT_GROUPS = [
    ["Gerenciadores de referências", "Importe no Zotero, Mendeley ou EndNote.",
      [["RIS (Zotero, Mendeley, EndNote)", "ris"], ["EndNote (.enw)", "endnote"], ["CSL JSON (Zotero)", "csljson"], ["BibTeX", "bibtex"]]],
    ["Citações prontas", "Uma referência por linha, para colar no seu trabalho.",
      [["ABNT", "abnt"], ["APA", "apa"], ["Vancouver", "vancouver"], ["IEEE", "ieee"], ["Harvard", "harvard"], ["MLA", "mla"]]],
    ["Planilha e dados", "Para analisar ou guardar.", [["Planilha (CSV)", "csv"], ["Dados (JSON)", "json"], ["Resumos (MD)", "resumos"]]],
  ];
  function exportMenu(listId) {
    const panel = h("div", { class: "download-panel", hidden: "", role: "region", "aria-label": "Opções de exportação" });
    const button = h("button", { type: "button", class: "btn btn-secondary btn-sm", "aria-expanded": "false", "aria-haspopup": "true" }, icon("download"), "Exportar");
    const close = () => { panel.hidden = true; button.setAttribute("aria-expanded", "false"); };
    const href = (format) => `/api/library/export?${new URLSearchParams({ format, ...(listId ? { list_id: listId } : {}) })}`;
    mount(panel, EXPORT_GROUPS.map(([title, hint, formats]) => h("section", { class: "download-option" },
      h("h4", {}, title), h("p", { class: "hint" }, hint),
      h("div", { class: "row" }, formats.map(([label, format]) => h("a", { class: "btn btn-sm btn-secondary", href: href(format), download: "", onclick: close }, label))))));
    button.addEventListener("click", () => {
      const open = panel.hidden;
      panel.hidden = !open;
      button.setAttribute("aria-expanded", String(open));
    });
    return h("span", { class: "download-wrap" }, button, panel);
  }

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    document.querySelectorAll(".download-panel:not([hidden])").forEach((panel) => {
      panel.hidden = true;
      const button = panel.parentElement.querySelector("button");
      button?.setAttribute("aria-expanded", "false");
      button?.focus();
    });
  });

  // analise salva do Laboratorio: ver (HTML sanitizado no servidor), baixar em 4 formatos e excluir
  function analysisRow(item, { showTitle = false, onChange } = {}) {
    const body = h("div", { class: "analysis-body prose", hidden: "" });
    const toggle = h("button", { type: "button", class: "btn btn-sm btn-secondary", "aria-expanded": "false" }, "Ver");
    let loaded = false;
    toggle.addEventListener("click", async () => {
      const open = body.hidden;
      if (open && !loaded) {
        const full = await guarded(() => api(`/api/analyses/${encodeURIComponent(item.id)}`));
        if (!full) return;
        body.innerHTML = full.html; // markdown_lite sanitiza no servidor (escapa o texto e so admite links http/https)
        loaded = true;
      }
      body.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
      toggle.textContent = open ? "Ocultar" : "Ver";
    });
    const remove = h("button", { type: "button", class: "btn btn-sm btn-ghost", "aria-label": `Excluir a análise ${item.label}` }, "Excluir");
    remove.addEventListener("click", async () => {
      if (await guarded(() => api(`/api/analyses/${encodeURIComponent(item.id)}`, { method: "DELETE" }))) { toast("Análise excluída"); if (onChange) onChange(); }
    });
    const date = new Date(item.createdAt);
    return h("li", { class: "analysis-item" },
      h("div", { class: "analysis-head" },
        h("strong", {}, item.label),
        h("span", { class: "muted" }, ` · ${item.page || "laboratório"} · ${Number.isNaN(date.getTime()) ? "" : date.toLocaleDateString("pt-BR")}`)),
      showTitle ? h("a", { href: Lib.buildHash("/artigo", { ref: item.ref }), class: "analysis-article" }, item.title) : null,
      h("div", { class: "row" }, toggle,
        ["docx", "md", "html", "txt"].map((f) => h("a", { class: "btn btn-sm btn-secondary", href: `/api/analyses/${encodeURIComponent(item.id)}/download?format=${f}`, download: "" }, f.toUpperCase())),
        remove),
      body);
  }

  // menu "Baixar": resumo, ficha, referencia e texto completo aberto; links abertos da fonte; impressao
  function downloadMenu(work) {
    const panel = h("div", { class: "download-panel", hidden: "", role: "region", "aria-label": "Opções de download" });
    const button = h("button", { type: "button", class: "btn btn-secondary", "aria-expanded": "false" }, icon("download"), "Baixar");
    const wrap = h("span", { class: "download-wrap" }, button, panel);
    let loaded = false;
    const fileHref = (kind, format) => `/api/discover/download?${new URLSearchParams({ ref: work.ref, kind, format })}`;
    async function load() {
      mount(panel, loading("Verificando o que há para baixar…"));
      let data;
      try { data = await api(`/api/discover/downloads?ref=${encodeURIComponent(work.ref)}`); } catch (error) {
        mount(panel, errorBox(error.message));
        return;
      }
      loaded = true;
      mount(panel,
        data.options.map((option) => h("section", { class: `download-option${option.available ? "" : " is-off"}` },
          h("h4", {}, option.label), h("p", { class: "hint" }, option.description),
          option.available
            ? h("div", { class: "row" }, option.formats.map((f) => h("a", { class: "btn btn-sm btn-secondary", href: fileHref(option.kind, f.id), download: "" }, f.label)))
            : null)),
        data.links.length ? h("section", { class: "download-option" }, h("h4", {}, "PDF e páginas abertas"),
          h("div", { class: "row" }, data.links.map((l) => {
            const safe = Lib.safeHttpUrl(l.url);
            return safe ? h("a", { class: "btn btn-sm btn-secondary", href: safe, target: "_blank", rel: "noopener noreferrer" }, [icon("external"), l.label]) : null;
          }))) : null,
        h("section", { class: "download-option" }, h("h4", {}, "Imprimir ou salvar como PDF"),
          h("p", { class: "hint" }, "Abre a impressão do navegador com o layout limpo desta página."),
          h("button", { type: "button", class: "btn btn-sm btn-secondary", onclick: () => window.print() }, "Imprimir esta página")),
        h("p", { class: "note" }, data.note));
    }
    button.addEventListener("click", () => {
      const open = panel.hidden;
      panel.hidden = !open;
      button.setAttribute("aria-expanded", String(open));
      if (open && !loaded) load();
    });
    panel.addEventListener("keydown", (event) => { if (event.key === "Escape") { panel.hidden = true; button.setAttribute("aria-expanded", "false"); button.focus(); } });
    return wrap;
  }

  // avisos da busca: um so aviso aparece direto; varios ficam recolhidos para nao empurrar os resultados
  function notesBlock(notes) {
    if (!notes.length) return null;
    if (notes.length === 1) return h("p", { class: "note" }, notes[0]);
    return h("details", { class: "notes" }, h("summary", {}, `${notes.length} avisos sobre esta busca`),
      h("ul", {}, notes.map((note) => h("li", {}, note))));
  }

  // Botao unico "Salvar": salva na biblioteca (padrao) e abre o menu para escolher listas ou criar uma nova.
  // Com o artigo ja salvo, o clique abre o mesmo menu (nao remove): remover fica dentro do menu.
  function saveButton(work, { small = true, onChange } = {}) {
    const button = h("button", { type: "button", class: `btn ${small ? "btn-sm " : ""}btn-secondary save-button`, "aria-haspopup": "dialog", "aria-expanded": "false" });
    const picker = h("div", { class: "save-picker", role: "dialog", "aria-label": "Salvar artigo", hidden: "" });
    const wrap = h("span", { class: "save-wrap" }, button, picker);
    const refresh = () => {
      button.setAttribute("aria-pressed", String(Boolean(work.saved)));
      button.replaceChildren(icon("bookmark", work.saved), work.saved ? "Salvo" : "Salvar", icon("chevron"));
    };
    const closePicker = () => { picker.hidden = true; picker.replaceChildren(); button.setAttribute("aria-expanded", "false"); };

    async function renderMenu() {
      mount(picker, loading("Carregando suas listas…"));
      picker.hidden = false;
      button.setAttribute("aria-expanded", "true");
      const data = await guarded(() => api("/api/lists"));
      if (!data) { closePicker(); return; }

      const status = h("div", { class: "save-status" },
        h("span", {}, icon("check"), work.saved ? " Salvo na biblioteca" : " Não está na biblioteca"),
        h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: toggleLibrary }, work.saved ? "Remover" : "Salvar"));

      const rows = data.lists.map((list) => {
        const box = h("input", { type: "checkbox", checked: list.works.some((w) => w.ref === work.ref) });
        box.addEventListener("change", async () => {
          box.disabled = true;
          const path = `/api/lists/${encodeURIComponent(list.id)}/items`;
          const ok = await guarded(() => (box.checked
            ? api(path, { method: "POST", body: { ref: work.ref } })
            : api(`${path}?ref=${encodeURIComponent(work.ref)}`, { method: "DELETE" })));
          box.disabled = false;
          if (ok === undefined) { box.checked = !box.checked; return; }
          toast(box.checked ? `Adicionado a "${list.name}"` : `Removido de "${list.name}"`);
          if (onChange) onChange();
        });
        return h("label", { class: "check list-check" }, box, h("span", {}, list.name), h("small", { class: "muted" }, String(list.works.length)));
      });

      const name = h("input", { type: "text", placeholder: data.lists.length ? "Nome da nova lista" : "Nome da primeira lista (ex.: TCC)", maxlength: "80", "aria-label": "Nome da nova lista" });
      const create = h("button", { type: "button", class: "btn btn-sm btn-primary" }, icon("plus"), "Criar e adicionar");
      const createList = async () => {
        if (!name.value.trim()) { name.focus(); return; }
        create.disabled = true;
        const made = await guarded(() => api("/api/lists", { method: "POST", body: { name: name.value } }));
        if (made && await guarded(() => api(`/api/lists/${encodeURIComponent(made.id)}/items`, { method: "POST", body: { ref: work.ref } }))) {
          toast(`Lista "${made.name}" criada com este artigo`);
          if (onChange) onChange();
          await renderMenu();
          return;
        }
        create.disabled = false;
      };
      create.addEventListener("click", createList);
      name.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); createList(); } });

      mount(picker, status,
        h("p", { class: "save-picker-title" }, data.lists.length ? "Adicionar a uma lista" : "Você ainda não tem listas. Crie a primeira:"),
        rows.length ? h("div", { class: "list-checks" }, rows) : null,
        h("div", { class: "new-list" }, name, create),
        h("button", { type: "button", class: "btn btn-sm btn-ghost close-picker", onclick: () => { closePicker(); button.focus(); } }, "Fechar"));
      (rows.length ? picker.querySelector("input[type=checkbox]") : name).focus();
    }

    async function toggleLibrary() {
      const done = await guarded(async () => {
        if (work.saved) await api(`/api/library?ref=${encodeURIComponent(work.ref)}`, { method: "DELETE" });
        else await api("/api/library", { method: "POST", body: { ref: work.ref } });
        work.saved = !work.saved;
        toast(work.saved ? "Salvo na biblioteca" : "Removido da biblioteca");
        return true;
      });
      refresh();
      if (done) { if (onChange) onChange(); await renderMenu(); }
    }

    picker.addEventListener("keydown", (event) => { if (event.key === "Escape") { closePicker(); button.focus(); } });
    button.addEventListener("click", async () => {
      if (!requireUser("Entre para salvar artigos na sua biblioteca.")) return;
      if (!picker.hidden) { closePicker(); return; }
      if (!work.saved) {
        button.disabled = true;
        const done = await guarded(async () => {
          await api("/api/library", { method: "POST", body: { ref: work.ref } });
          work.saved = true;
          toast("Salvo na biblioteca");
          return true;
        });
        button.disabled = false;
        refresh();
        if (!done) return;
        if (onChange) onChange();
      }
      await renderMenu();
    });
    refresh();
    return wrap;
  }

  // ------------------------------------------------------------------ Início
  const TOPICS = ["diabetes tipo 2", "sepse", "saúde mental", "inteligência artificial na saúde", "mudanças climáticas"];
  const STEPS = [
    ["01", "Busque", "Filtre por ano, tipo de estudo, idioma e acesso aberto. Combine fontes sem ver o mesmo artigo duas vezes."],
    ["02", "Entenda", "Resumo organizado por seções, números com a frase de origem e a nota de confiabilidade explicada critério a critério."],
    ["03", "Organize", "Salve, etiquete, monte listas de leitura, compartilhe por link e exporte as referências para o Zotero, Mendeley ou EndNote (RIS, CSL JSON, BibTeX) ou em ABNT, APA, Vancouver, IEEE, Harvard ou MLA."],
  ];
  const TRUST = [
    ["Sem IA primeiro.", "Trechos copiados do resumo; nada gerado nem interpretado."],
    ["Dado ausente não pune.", "O que a fonte não informa sai do cálculo e reduz a cobertura."],
    ["Limites declarados.", "A nota não mede a execução do estudo nem substitui a leitura crítica."],
  ];
  const AUDIENCE = [
    ["Estudantes", "Achar artigos para o TCC, entender o resumo e citar do jeito certo.", "diabetes tipo 2"],
    ["Professores", "Montar listas de leitura e compartilhar com a turma por link.", "saúde pública"],
    ["Pesquisadores", "Comparar estudos e ver o tipo de evidência antes de ler o texto completo.", "ensaio clínico hipertensão"],
    ["Profissionais", "Encontrar rápido a evidência sobre uma pergunta, com os limites à vista.", "sepse"],
  ];
  const SAMPLE_CRITERIA = [
    ["met", "Integridade (retratação)", "20/20"], ["met", "Desenho do estudo", "22,5/25"], ["met", "Revisão por pares", "10/10"],
    ["unmet", "Tamanho da amostra informado", "0/10"], ["partial", "Resultado principal quantificado", "5/10"],
    ["partial", "Precisão estatística", "5/10"], ["met", "Método descrito no resumo", "10/10"],
  ];

  function renderHome() {
    setTitle("Início");
    const input = h("input", { type: "search", id: "home-q", placeholder: "Tema, título, DOI ou palavra-chave", "aria-label": "Buscar artigos", maxlength: "300", autocomplete: "off" });
    const sourceBox = h("span", { class: "search-source" });
    const sourceCount = h("strong", {}, "2");
    let sourceSelect = null;
    const go = (q) => {
      const fonte = sourceSelect && sourceSelect.value !== "" ? sourceSelect.value : "";
      location.hash = Lib.buildHash("/busca", { q, fonte });
    };
    loadOptions().then((options) => {
      if (options.sources.length < 2) return;
      sourceSelect = h("select", { id: "home-source", "aria-label": "Fonte" },
        options.sources.map((src) => h("option", { value: src.default ? "" : src.id }, src.name)));
      sourceSelect.value = "";  // a primeira opcao ("Todas as fontes") e a padrao
      mount(sourceBox, sourceSelect);
      sourceCount.textContent = String(options.sources.filter((src) => src.id !== "all").length);
    }).catch(() => { /* a busca funciona sem o seletor */ });

    const stat = (value, label) => h("div", { class: "stat" }, value, h("span", {}, label));
    mount($app,
      h("section", { class: "home-hero" },
        h("p", { class: "eyebrow" }, "Navegador de artigos científicos"),
        h("h1", { class: "display" }, "Encontre, entenda e organize a pesquisa."),
        h("p", { class: "lead" }, "Busque em várias fontes ao mesmo tempo, leia o resumo como o autor escreveu e veja, com critérios abertos, o quanto cada artigo merece confiança."),
        h("form", { class: "home-search", role: "search", onsubmit: (e) => { e.preventDefault(); go(input.value.trim()); } },
          input, sourceBox,
          h("button", { type: "submit", class: "btn btn-primary" }, icon("search"), "Buscar")),
        h("p", { class: "examples" }, "Exemplos: ", TOPICS.map((t) => h("a", { href: Lib.buildHash("/busca", { q: t }) }, t)))),

      profileShortcuts(),

      h("section", { class: "stats", "aria-label": "O produto em números" },
        stat(sourceCount, "fontes integradas, com busca combinada"),
        stat(h("strong", {}, "8"), "critérios abertos de confiabilidade"),
        stat(h("strong", {}, "10"), "formatos de citação e exportação"),
        stat(h("strong", {}, "16"), "áreas de análise com IA opcional")),

      h("section", { class: "home-section", "aria-labelledby": "como" },
        h("p", { class: "eyebrow" }, "Como funciona"),
        h("h2", { id: "como" }, "Da pergunta à leitura crítica, em três passos."),
        h("div", { class: "cols-3" }, STEPS.map(([n, title, text]) => h("div", { class: "step" },
          h("span", { class: "num" }, n), h("h3", {}, title), h("p", { class: "muted" }, text))))),

      h("section", { class: "home-section split", "aria-labelledby": "confianca" },
        h("div", {},
          h("p", { class: "eyebrow" }, "Confiança e método"),
          h("h2", { id: "confianca" }, "Uma nota que mostra o próprio cálculo."),
          h("p", { class: "lead" }, "Cada artigo recebe uma pontuação de 0 a 100 baseada em sinais verificáveis. Abra a nota e veja o que contou, o que faltou e a evidência usada."),
          h("ul", { class: "checklist" }, TRUST.map(([title, text]) => h("li", {}, icon("check"), h("span", {}, h("b", {}, `${title} `), text))))),
        h("div", { class: "panel", role: "img", "aria-label": "Exemplo de nota de confiabilidade 78 de 100, com dados fictícios" },
          h("div", { class: "panel-head" }, h("h3", {}, "Exemplo de nota"), h("span", { class: "muted" }, "dados fictícios")),
          h("div", { class: "panel-body" },
            h("div", { class: "score" }, h("strong", {}, "78"), h("span", {}, "/100"), h("span", { class: "band" }, "Alta")),
            h("div", { class: "meter" }, h("i", { class: "w78" })),
            h("ul", { class: "criteria-mini" }, SAMPLE_CRITERIA.map(([status, name, pts]) => h("li", {},
              h("span", { class: `st-${status}` }, icon(STATUS_ICONS[status])), h("span", {}, name), h("span", { class: "pts" }, pts))))))),

      h("section", { class: "home-section", "aria-labelledby": "para-quem" },
        h("p", { class: "eyebrow" }, "Para quem"),
        h("h2", { id: "para-quem" }, "Feito para quem lê ciência todos os dias."),
        h("ul", { class: "audience" }, AUDIENCE.map(([who, what, q]) => h("li", {},
          h("h3", {}, who), h("p", { class: "muted" }, what),
          h("a", { href: Lib.buildHash("/busca", { q }) }, "Começar", icon("arrow")))))),

      h("section", { class: "cta" },
        h("div", {}, h("h2", {}, "Sua biblioteca, no seu ritmo."),
          h("p", { class: "muted" }, "Buscar e ler não exige conta. Crie uma para salvar artigos, montar listas e exportar referências.")),
        h("div", { class: "row" },
          session.user
            ? h("a", { class: "btn btn-primary", href: "#/biblioteca" }, "Abrir minha biblioteca")
            : h("button", { type: "button", class: "btn btn-primary", onclick: () => openAuth("Crie uma conta para salvar artigos e montar listas.") }, "Criar conta ou entrar"),
          h("a", { class: "btn btn-outline", href: "/ia" }, "Conhecer o Laboratório de IA"))));
  }

  // ------------------------------------------------------------------ Busca
  async function renderSearch(params) {
    setTitle("Busca");
    mount($app, h("h1", {}, "Busca"), loading("Preparando a busca…"));
    let options;
    try { options = await loadOptions(); } catch (error) { mount($app, h("h1", {}, "Busca"), errorBox(error.message)); return; }

    const st = Lib.searchStateFromParams(params);
    const defaultSource = options.sources.find((s) => s.default) || options.sources[0];
    if (!options.sources.some((s) => s.id === st.source)) st.source = "";
    const activeSource = () => options.sources.find((s) => s.id === (st.source || defaultSource.id)) || defaultSource;

    const q = h("input", { type: "search", id: "q", value: st.q, placeholder: "tema, título ou palavra-chave", autocomplete: "off", maxlength: "300" });
    const yf = h("input", { type: "number", id: "yf", min: "1800", max: "2100", value: st.yearFrom ?? "", placeholder: "de" });
    const yt = h("input", { type: "number", id: "yt", min: "1800", max: "2100", value: st.yearTo ?? "", placeholder: "até" });
    const oa = h("input", { type: "checkbox", id: "oa", checked: st.oa });
    const lang = h("select", { id: "lang" }, options.languages.map((l) => h("option", { value: l.id, selected: l.id === st.lang }, l.name)));
    const sort = h("select", { id: "sort" }, options.sorts.map((s) => h("option", { value: s.id, selected: s.id === st.sort }, s.name)));
    const source = options.sources.length > 1
      ? h("select", { id: "source" }, options.sources.map((s) => h("option", { value: s.id, selected: s.id === activeSource().id }, s.name)))
      : null;
    const typeBox = h("div", {});
    const results = h("div", { "aria-live": "polite" });

    const renderTypes = () => mount(typeBox, activeSource().studyTypes.map((t) => h("label", { class: "check" },
      h("input", { type: "checkbox", value: t, checked: st.types.includes(t) }), t)));
    renderTypes();

    const readControls = () => {
      st.q = q.value.trim();
      st.yearFrom = Number.parseInt(yf.value, 10) || null;
      st.yearTo = Number.parseInt(yt.value, 10) || null;
      st.oa = oa.checked;
      st.lang = lang.value;
      st.sort = sort.value;
      st.types = [...typeBox.querySelectorAll("input:checked")].map((i) => i.value);
      if (source) st.source = source.value === defaultSource.id ? "" : source.value;
    };

    let controller;
    let run = async () => {
      if (controller) controller.abort();
      controller = new AbortController();
      mount(results, loading("Buscando…"));
      try {
        const data = await api(`/api/discover/search?${Lib.apiParamsFromSearchState(st, PAGE_SIZE)}`, { signal: controller.signal });
        mount(results,
          h("div", { class: "results-head" },
            h("div", {}, h("strong", {}, `${Lib.formatCount(data.total)} ${data.total === 1 ? "resultado" : "resultados"}`),
              h("span", { class: "muted" }, ` · ${activeSource().name}`)),
            h("label", { class: "sort-inline" }, h("span", {}, "Ordenar"), sort)),
          notesBlock(data.notes || []),
          data.works.length
            ? h("ol", { class: "results" }, data.works.map((work) => h("li", { class: "result" },
              h("h3", {}, h("a", { href: articleHref(work) }, highlighted(work.title, st.q))),
              h("div", { class: "meta" }, metaLine(work)),
              badges(work),
              work.snippet ? h("p", { class: "snippet" }, highlighted(work.snippet, st.q)) : null,
              h("div", { class: "row" }, saveButton(work), h("a", { class: "btn btn-sm btn-ghost", href: articleHref(work) }, "Abrir")))))
            : h("div", { class: "empty card" }, h("p", {}, "Nenhum artigo encontrado."), h("p", { class: "muted" }, "Tente menos termos ou limpe os filtros.")),
          data.pages > 1 ? h("nav", { class: "pager", "aria-label": "Páginas" },
            h("button", { type: "button", class: "btn btn-secondary btn-sm", disabled: data.page <= 1, onclick: () => goPage(data.page - 1) }, "Anterior"),
            Lib.pageWindow(data.page, data.pages).map((p) => (p === "…" ? h("span", { class: "muted" }, "…")
              : h("button", { type: "button", class: `btn btn-secondary btn-sm${p === data.page ? " current" : ""}`, "aria-current": p === data.page ? "page" : null, onclick: () => goPage(p) }, p))),
            h("button", { type: "button", class: "btn btn-secondary btn-sm", disabled: data.page >= data.pages, onclick: () => goPage(data.page + 1) }, "Próxima")) : null);
      } catch (error) {
        if (error.name === "AbortError") return;
        mount(results, errorBox(error.message));
      }
    };
    function sync() {
      history.replaceState(null, "", Lib.buildHash("/busca", Lib.paramsFromSearchState(st)));
      run();
    }
    function goPage(page) { st.page = page; sync(); window.scrollTo(0, 0); }
    const apply = () => { readControls(); st.page = 1; sync(); };
    const applyLater = Lib.debounce(apply, 350);

    // barra de busca sempre visivel (no celular fica fixa abaixo do cabecalho)
    const searchBar = h("form", { class: "search-bar", role: "search", onsubmit: (e) => { e.preventDefault(); applyLater.cancel(); apply(); q.blur(); } },
      h("label", { class: "visually-hidden", for: "q" }, "Buscar artigos"), q,
      h("button", { type: "submit", class: "btn btn-primary" }, icon("search"), h("span", { class: "btn-label" }, "Buscar")));

    const filters = h("form", { class: "filters", "aria-label": "Filtros", onsubmit: (e) => { e.preventDefault(); applyLater.cancel(); apply(); } },
      source ? h("div", { class: "field" }, h("label", { for: "source" }, "Fonte"), source) : null,
      h("div", { class: "field" }, h("label", {}, "Ano de publicação"), h("div", { class: "row" }, yf, yt)),
      h("div", { class: "field" }, h("label", {}, "Tipo de estudo"), typeBox),
      h("div", { class: "field" }, h("label", { class: "check" }, oa, "Só acesso aberto")),
      h("div", { class: "field" }, h("label", { for: "lang" }, "Idioma"), lang));
    filters.addEventListener("change", (event) => {
      if (event.target === source) {
        // a fonte muda os tipos de estudo oferecidos: limpa a selecao e redesenha a lista de tipos
        st.source = source.value === defaultSource.id ? "" : source.value;
        st.types = [];
        renderTypes();
      }
      applyLater();
    });
    sort.addEventListener("change", () => apply());
    yf.addEventListener("input", applyLater);
    yt.addEventListener("input", applyLater);

    // filtros ativos como chips removiveis (valem no desktop e no celular)
    const activeBox = h("div", { class: "active-filters", "aria-label": "Filtros ativos" });
    const filterButton = h("button", { type: "button", class: "btn btn-secondary filter-toggle", "aria-haspopup": "dialog", "aria-expanded": "false" });
    function activeFilters() {
      const list = [];
      if (st.yearFrom || st.yearTo) {
        const label = st.yearFrom && st.yearTo ? `${st.yearFrom}–${st.yearTo}` : st.yearFrom ? `desde ${st.yearFrom}` : `até ${st.yearTo}`;
        list.push([label, () => { yf.value = ""; yt.value = ""; }]);
      }
      st.types.forEach((type) => list.push([type, () => { [...typeBox.querySelectorAll("input")].forEach((i) => { if (i.value === type) i.checked = false; }); }]));
      if (st.oa) list.push(["Acesso aberto", () => { oa.checked = false; }]);
      if (st.lang) list.push([(options.languages.find((l) => l.id === st.lang) || {}).name || st.lang, () => { lang.value = ""; }]);
      if (st.source && source) list.push([activeSource().name.split(" (")[0], () => { source.value = defaultSource.id; st.source = ""; st.types = []; renderTypes(); }]);
      return list;
    }
    function renderActive() {
      const list = activeFilters();
      filterButton.replaceChildren(...[icon("filter"), "Filtros", list.length ? h("span", { class: "count-badge" }, String(list.length)) : null].filter(Boolean));
      mount(activeBox, list.map(([label, clear]) => h("span", { class: "chip" }, label,
        h("button", { type: "button", "aria-label": `Remover filtro ${label}`, onclick: () => { clear(); apply(); } }, "×"))));
      activeBox.hidden = list.length === 0;
    }
    const baseRun = run;
    run = () => { renderActive(); return baseRun(); };

    // painel de filtros: coluna lateral no desktop; folha inferior no celular
    const backdrop = h("div", { class: "sheet-backdrop", hidden: "" });
    const sheetTitle = h("div", { class: "sheet-head" }, h("strong", {}, "Filtros"),
      h("button", { type: "button", class: "btn btn-ghost", "aria-label": "Fechar filtros", onclick: () => closeSheet() }, "Fechar"));
    const sheetFoot = h("div", { class: "sheet-foot" },
      h("a", { class: "btn btn-secondary", href: "#/busca", onclick: () => closeSheet() }, "Limpar tudo"),
      h("button", { type: "button", class: "btn btn-primary", onclick: () => closeSheet() }, "Ver resultados"));
    const wrap = h("div", { class: "filters-wrap", role: "dialog", "aria-label": "Filtros da busca" }, sheetTitle, filters, sheetFoot);
    function openSheet() { wrap.classList.add("open"); backdrop.hidden = false; document.body.classList.add("sheet-open"); filterButton.setAttribute("aria-expanded", "true"); }
    function closeSheet() { wrap.classList.remove("open"); backdrop.hidden = true; document.body.classList.remove("sheet-open"); filterButton.setAttribute("aria-expanded", "false"); }
    filterButton.addEventListener("click", () => (wrap.classList.contains("open") ? closeSheet() : openSheet()));
    backdrop.addEventListener("click", closeSheet);
    wrap.addEventListener("keydown", (event) => { if (event.key === "Escape") { closeSheet(); filterButton.focus(); } });
    window.addEventListener("hashchange", closeSheet, { once: true });

    mount($app, h("h1", { class: "visually-hidden" }, "Busca"), searchBar,
      h("div", { class: "search-toolbar" }, filterButton),
      activeBox,
      h("div", { class: "layout" }, wrap, results), backdrop);
    run();
  }

  // ------------------------------------------------------------------ Artigo
  const STATUS_LABELS = { met: "Atendido", partial: "Parcial", unmet: "Não atendido", na: "Não se aplica", unknown: "Desconhecido" };
  const STATUS_ICONS = { met: "check", partial: "half", unmet: "x", na: "minus", unknown: "help" };

  function reliabilityCard(rel) {
    if (!rel) return null;
    const panelId = "reliability-panel";
    const scoreText = rel.score === null ? "—" : `${rel.score}`;
    const button = h("button", { type: "button", class: `reliability-badge band-${rel.band.toLowerCase()}`, "aria-expanded": "false", "aria-controls": panelId },
      h("span", { class: "reliability-score" }, scoreText, rel.score === null ? null : h("small", {}, "/100")),
      h("span", { class: "reliability-text" }, h("strong", {}, `Confiabilidade: ${rel.band}`), h("span", {}, "Toque para ver como a nota é calculada")));
    const rows = rel.criteria.map((c) => h("li", { class: `criterion status-${c.status}` },
      h("div", { class: "criterion-head" },
        h("span", { class: "criterion-icon", "aria-hidden": "true" }, icon(STATUS_ICONS[c.status] || "help")),
        h("strong", {}, c.name),
        h("span", { class: "criterion-points" }, c.status === "na" || c.status === "unknown" ? `${STATUS_LABELS[c.status]} (fora do cálculo)` : `${STATUS_LABELS[c.status]} · ${c.points}/${c.weight}`)),
      h("p", {}, c.detail),
      c.evidence ? h("blockquote", { class: "evidence" }, c.evidence) : null,
      h("p", { class: "hint" }, `Como avaliamos: ${c.how}`)));
    const panel = h("div", { id: panelId, class: "reliability-panel stack", hidden: "" },
      h("p", {}, rel.summary),
      h("p", { class: "hint" }, "A nota é a soma dos pontos dos critérios avaliáveis dividida pelo peso desses critérios, em escala de 0 a 100. Critérios \"desconhecido\" ou \"não se aplica\" ficam fora do cálculo, e a cobertura mostra quanto foi realmente avaliado. Artigo retratado vale 0. Faixas: Alta (75 ou mais), Moderada (50 a 74), Baixa (abaixo de 50)."),
      rel.warnings.map((w) => h("p", { class: "note" }, w)),
      h("ul", { class: "criteria" }, rows),
      h("p", { class: "note" }, rel.disclaimer));
    button.addEventListener("click", () => {
      const open = panel.hasAttribute("hidden");
      if (open) panel.removeAttribute("hidden"); else panel.setAttribute("hidden", "");
      button.setAttribute("aria-expanded", String(open));
    });
    return h("div", { class: "card stack reliability" }, button, panel);
  }

  async function renderArticle(params) {
    const ref = params.get("ref") || "";
    mount($app, loading("Abrindo o artigo…"));
    let data;
    try {
      data = await api(`/api/discover/work?ref=${encodeURIComponent(ref)}`);
    } catch (error) {
      setTitle("Artigo");
      mount($app, h("div", { class: "stack" }, h("a", { href: "#/busca", class: "muted" }, "Voltar à busca"), errorBox(error.message)));
      return;
    }
    const work = data.work;
    setTitle(work.title);
    setCitationMeta(work);

    // citar
    const citationBox = h("div", { "aria-live": "polite" });
    const showCitation = (style) => {
      const text = data.citations[style];
      mount(citationBox, h("div", { class: "citation" }, text),
        h("div", { class: "row" }, h("button", { type: "button", class: "btn btn-sm btn-secondary", onclick: () => copyText(text, `Referência ${style} copiada`) }, "Copiar"),
          h("span", { class: "note" }, "Gerada por código a partir dos metadados do registro (sem IA).")));
    };

    // levar a referência para o Zotero, Mendeley ou EndNote
    const REFERENCE_FORMATS = [["RIS (Zotero, Mendeley, EndNote)", "ris"], ["EndNote (.enw)", "endnote"], ["CSL JSON (Zotero)", "csljson"], ["BibTeX", "bibtex"]];
    function referenceExport(article) {
      const query = (format) => new URLSearchParams({ ref: article.ref, format }).toString();
      const copyBibtex = async () => {
        try {
          const response = await fetch(`/api/discover/cite?${query("bibtex")}`, { credentials: "same-origin" });
          if (!response.ok) throw new Error();
          copyText(await response.text(), "BibTeX copiado");
        } catch { toast("Não foi possível copiar o BibTeX agora."); }
      };
      return h("div", { class: "stack reference-export" },
        h("h3", {}, "Levar para o gerenciador de referências"),
        h("div", { class: "row" },
          REFERENCE_FORMATS.map(([label, format]) => h("a", { class: "btn btn-secondary btn-sm", download: "", href: `/api/discover/cite?${query(format)}` }, label)),
          h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: copyBibtex }, "Copiar BibTeX")),
        h("p", { class: "note" }, "Zotero, Mendeley e EndNote abrem o arquivo RIS (Arquivo, Importar). O Zotero também lê o CSL JSON e, com o conector do navegador instalado, captura esta página direto pelo botão dele."));
    }

    // organizar (etiquetas e listas): só com conta
    const organize = h("div", { class: "stack" });
    async function renderOrganize() {
      if (!session.user) {
        mount(organize, h("p", { class: "muted" }, "Entre na sua conta para etiquetar este artigo e adicioná-lo a listas de leitura."),
          h("div", { class: "row" }, h("button", { type: "button", class: "btn btn-secondary", onclick: () => openAuth("Entre para organizar seus artigos.") }, "Entrar")));
        return;
      }
      mount(organize, loading("Carregando suas listas…"));
      const mine = await guarded(() => Promise.all([api("/api/library"), api("/api/lists")]));
      if (!mine) { mount(organize, h("p", { class: "muted" }, "Não foi possível carregar sua biblioteca agora.")); return; }
      const [library, lists] = mine;
      const item = library.items.find((i) => i.ref === work.ref);
      const tagsBox = h("div", { class: "stack" });
      const drawTags = (tags) => {
        const input = h("input", { type: "text", id: "tag", placeholder: "nova etiqueta (ex.: TCC)", maxlength: "30" });
        const save = async (next) => { const r = await guarded(() => api("/api/library/tags", { method: "PUT", body: { ref: work.ref, tags: next } })); if (r) drawTags(r.tags); };
        mount(tagsBox,
          h("div", { class: "chips" }, tags.map((t) => h("span", { class: "chip" }, t, h("button", { type: "button", "aria-label": `Remover etiqueta ${t}`, onclick: () => save(tags.filter((x) => x !== t)) }, "×")))),
          h("div", { class: "row" }, input, h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: () => input.value.trim() && save([...tags, input.value.trim()]) }, "Adicionar etiqueta")));
      };
      if (item) drawTags(item.tags); else mount(tagsBox, h("p", { class: "muted" }, "Salve o artigo para adicionar etiquetas."));

      const select = h("select", { id: "add-list", "aria-label": "Adicionar a uma lista" },
        h("option", { value: "" }, lists.lists.length ? "Adicionar à lista…" : "Você ainda não tem listas"),
        lists.lists.map((l) => h("option", { value: l.id }, `${l.name} (${l.works.length})`)));
      select.addEventListener("change", async () => {
        if (!select.value) return;
        const ok = await guarded(() => api(`/api/lists/${select.value}/items`, { method: "POST", body: { ref: work.ref } }));
        if (ok) { toast("Adicionado à lista"); renderOrganize(); }
      });
      const newName = h("input", { type: "text", id: "new-list", placeholder: "nome da nova lista", maxlength: "80" });
      const create = async () => {
        if (!newName.value.trim()) return;
        const created = await guarded(() => api("/api/lists", { method: "POST", body: { name: newName.value } }));
        if (!created) return;
        await guarded(() => api(`/api/lists/${created.id}/items`, { method: "POST", body: { ref: work.ref } }));
        toast(`Lista "${created.name}" criada`);
        renderOrganize();
      };
      mount(organize, tagsBox, h("div", { class: "row" }, select),
        h("div", { class: "row" }, newName, h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: create }, "Criar lista com este artigo")));
    }

    // registro de ensaios, citacoes e dados ligados (fontes abertas); carrega depois da pagina
    const openData = h("div", { class: "stack" }, loading("Consultando registros abertos…"));
    async function renderOpenData() {
      let extra;
      try { extra = await api(`/api/discover/enrichment?ref=${encodeURIComponent(work.ref)}`); } catch {
        mount(openData, h("p", { class: "muted" }, "Os registros abertos não responderam agora."));
        return;
      }
      const external = (href, label) => {
        const safe = Lib.safeHttpUrl(href);
        return safe ? h("a", { href: safe, target: "_blank", rel: "noopener noreferrer" }, label) : label;
      };
      const blocks = [];
      if (extra.mentionedTrials.length) {
        blocks.push(h("div", {}, h("h4", {}, "Registro do ensaio"),
          extra.trials.length
            ? h("ul", { class: "plain-list" }, extra.trials.map((t) => h("li", {},
              external(t.url, t.nct), ` · ${t.status}${t.start ? ` · início ${t.start}` : ""}${t.hasResults ? " · resultados publicados" : ""}`,
              h("small", { class: "muted" }, t.title))))
            : h("p", { class: "muted" }, `O resumo cita ${extra.mentionedTrials.join(", ")}, mas o ClinicalTrials.gov não confirmou o registro.`)));
      }
      if (extra.citations !== null) {
        blocks.push(h("div", {}, h("h4", {}, "Citações (OpenCitations)"), h("p", {}, Lib.formatCount(extra.citations))));
      }
      if (extra.relatedData.length) {
        blocks.push(h("div", {}, h("h4", {}, "Dados e materiais ligados"),
          h("ul", { class: "plain-list" }, extra.relatedData.map((d) => h("li", {},
            external(d.url, d.title), h("small", { class: "muted" }, [d.kind, d.publisher].filter(Boolean).join(" · ")))))));
      }
      mount(openData, blocks.length ? blocks
        : h("p", { class: "muted" }, "Nenhum registro de ensaio, citação ou dado ligado foi encontrado nas fontes abertas."),
      h("p", { class: "note" }, "Fontes: ClinicalTrials.gov, OpenCitations e DataCite (inclui Zenodo)."));
    }

    // analises salvas do Laboratorio de IA para este artigo (so com conta)
    const analysesBox = h("div", { class: "stack" });
    async function renderAnalyses() {
      if (!session.user) {
        mount(analysesBox, h("p", { class: "muted" }, "Entre na sua conta para guardar aqui as análises do Laboratório de IA."));
        return;
      }
      const data = await guarded(() => api(`/api/analyses?ref=${encodeURIComponent(work.ref)}`));
      if (!data) { mount(analysesBox, h("p", { class: "muted" }, "Não foi possível carregar suas análises agora.")); return; }
      mount(analysesBox,
        data.analyses.length
          ? h("ul", { class: "analysis-list" }, data.analyses.map((item) => analysisRow(item, { onChange: renderAnalyses })))
          : h("p", { class: "muted" }, "Nenhuma análise salva. No Laboratório, gere uma análise e clique em \"Salvar no artigo\"."),
        h("a", { class: "btn btn-sm btn-outline", href: Lib.aiLabHref(work.pmid || work.ref) }, "Abrir no Laboratório de IA"));
    }

    // situacao no Brasil: registro na ANVISA e decisoes da Conitec (dados oficiais locais, sem IA) para os medicamentos do resumo
    const brasilBox = h("div", { class: "stack" }, loading("Consultando dados oficiais…"));
    async function renderBrasil() {
      let data;
      try { data = await api(`/api/discover/brasil?ref=${encodeURIComponent(work.ref)}`); } catch {
        mount(brasilBox, h("p", { class: "muted" }, "Os dados oficiais do Brasil não estão disponíveis agora."));
        return;
      }
      const manualResult = h("div", { class: "stack" });
      const manualInput = h("input", { type: "text", placeholder: "Outro medicamento (nome em português)", maxlength: "80", "aria-label": "Buscar medicamento nas bases oficiais" });
      const manualButton = h("button", { type: "button", class: "btn btn-sm btn-secondary" }, "Buscar");
      const runManual = async () => {
        const term = manualInput.value.trim();
        if (term.length < 3) { manualInput.focus(); return; }
        const found = await guarded(() => api(`/api/brasil/medicamento?q=${encodeURIComponent(term)}`));
        if (!found) return;
        mount(manualResult, h("h4", {}, term), situationBlock(found, term.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase()));
      };
      manualButton.addEventListener("click", runManual);
      manualInput.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); runManual(); } });
      const meta = data.meta;
      const source = Lib.safeHttpUrl(meta.conitec.paginaUrl);
      const anvisaSource = Lib.safeHttpUrl(meta.anvisa.arquivoUrl);
      const renameSource = meta.rename ? Lib.safeHttpUrl(meta.rename.arquivoUrl) : null;
      const stale = [meta.anvisa.defasado ? `ANVISA (extraída em ${fmtDate(meta.anvisa.extraidoEm)})` : "", meta.conitec.defasado ? `Conitec (extraída em ${fmtDate(meta.conitec.extraidoEm)})` : "", meta.rename && meta.rename.defasado ? `Rename (extraída em ${fmtDate(meta.rename.extraidoEm)})` : ""].filter(Boolean);
      mount(brasilBox,
        data.candidatos.length
          ? [h("p", { class: "hint" }, "Medicamentos que o resumo parece citar. A correspondência de nomes é automática: confirme."),
            data.candidatos.map((c) => h("div", { class: "conitec-drug" },
              h("h4", {}, c.pt, h("span", { class: "muted" }, ` · no texto: ${c.en} (${METHODS[c.metodo] || c.metodo})`)),
              situationBlock(c, c.pt.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase())))]
          : h("p", { class: "muted" }, "Não identificamos, no resumo, medicamentos nas bases oficiais. Busque pelo nome em português:"),
        h("div", { class: "new-list" }, manualInput, manualButton), manualResult,
        stale.length ? h("p", { class: "note" }, `Atenção: dados possivelmente desatualizados: ${stale.join("; ")}.`) : null,
        h("p", { class: "note" }, "Fontes: registros de medicamentos da ", anvisaSource ? h("a", { href: anvisaSource, target: "_blank", rel: "noopener noreferrer" }, "ANVISA (dados abertos)") : "ANVISA",
          ` (extraídos em ${fmtDate(meta.anvisa.extraidoEm)}) e decisões da `, source ? h("a", { href: source, target: "_blank", rel: "noopener noreferrer" }, "Conitec") : "Conitec",
          ` (extraídas em ${fmtDate(meta.conitec.extraidoEm)})`, meta.rename ? [" e a ", renameSource ? h("a", { href: renameSource, target: "_blank", rel: "noopener noreferrer" }, "Rename 2024") : "Rename 2024", ` (extraída do PDF oficial em ${fmtDate(meta.rename.extraidoEm)}, licença CC BY-NC-SA 4.0)`] : null,
          ". Constar na Rename indica medicamento essencial; registro ativo na ANVISA permite comercializar; decisão da Conitec trata da incorporação ao SUS. Nenhum dos três indica disponibilidade na sua unidade de saúde: consulte a Secretaria de Saúde."));
    }

    // artigos semelhantes: carregam depois da pagina e ficam no fim dela
    const similarBox = h("div", { class: "similar-grid" }, loading("Procurando artigos semelhantes…"));
    const similarNote = h("p", { class: "hint" });
    const similarSection = h("section", { class: "similar-section", "aria-labelledby": "similar-title" },
      h("h2", { id: "similar-title" }, "Artigos semelhantes"), similarNote, similarBox);
    async function renderSimilar() {
      let data;
      try { data = await api(`/api/discover/similar?ref=${encodeURIComponent(work.ref)}`); } catch {
        mount(similarBox, h("p", { class: "muted" }, "Não foi possível buscar artigos semelhantes agora."));
        return;
      }
      similarNote.textContent = data.terms.length ? `Buscamos na mesma fonte por: ${data.terms.join(", ")}.` : "";
      mount(similarBox, data.works.length
        ? data.works.map((w) => h("article", { class: "similar-card" },
          h("h3", {}, h("a", { href: articleHref(w) }, w.title)),
          h("p", { class: "meta" }, metaLine(w)),
          badges(w),
          h("div", { class: "row" }, saveButton(w), h("a", { class: "btn btn-sm btn-ghost", href: articleHref(w) }, "Abrir"))))
        : h("p", { class: "muted" }, "Não encontramos artigos semelhantes nesta fonte."));
    }

    const oaHref = Lib.safeHttpUrl(work.oaUrl);
    const doiHref = work.doi ? Lib.safeHttpUrl(`https://doi.org/${work.doi}`) : "";
    const pmidHref = /^\d+$/.test(work.pmid) ? `https://pubmed.ncbi.nlm.nih.gov/${work.pmid}/` : "";
    const meta = [
      ["Tipo de estudo", (work.studyTypes || []).join(", ") || "Não informado pelo registro"],
      ["Periódico", [work.journal, work.volume && `v. ${work.volume}`, work.issue && `n. ${work.issue}`, work.pages && `p. ${work.pages}`].filter(Boolean).join(", ") || "—"],
      ["Ano", work.year || "—"],
      ["DOI", doiHref ? h("a", { href: doiHref, target: "_blank", rel: "noopener noreferrer" }, work.doi) : "—"],
      ["PubMed", pmidHref ? h("a", { href: pmidHref, target: "_blank", rel: "noopener noreferrer" }, `PMID ${work.pmid}`) : "—"],
      ["Idioma", work.language ? work.language.toUpperCase() : "—"],
      ["Fonte", work.source || "—"],
      ["Citações", work.citedBy > 0 ? Lib.formatCount(work.citedBy) : "—"],
    ];

    mount($app,
      h("article", { class: "article-page" },
        h("a", { href: "#/busca", class: "back-link" }, "Voltar à busca"),
        h("header", { class: "article-head" },
          h("h1", {}, work.title),
          h("p", { class: "byline" }, metaLine(work)),
          badges(work),
          h("div", { class: "row actions" },
            saveButton(work, { small: false, onChange: renderOrganize }),
            oaHref ? h("a", { class: "btn btn-secondary", href: oaHref, target: "_blank", rel: "noopener noreferrer" }, [icon("external"), "Versão aberta"])
              : h("span", { class: "note" }, "Sem versão aberta conhecida"),
            downloadMenu(work),
            h("a", { class: "btn btn-secondary", href: Lib.aiLabHref(work.pmid || work.ref), title: "Resumos e análises com IA, opcionais e com avisos" }, [icon("spark"), "Analisar com IA", h("span", { class: "opt" }, " (opcional)")]))),
        h("div", { class: "article-layout" },
          h("div", { class: "article-main" },
            h("section", { class: "block" }, h("h2", {}, "Resumo, com as seções originais"),
              !work.abstract ? h("p", { class: "muted" }, "Este registro não traz resumo.")
                : data.sections.length
                  ? h("dl", { class: "sections" }, data.sections.map((s) => h("div", { class: "sec" },
                    h("dt", {}, s.label && s.label.toLowerCase() !== s.heading.toLowerCase() ? `${s.heading} (rótulo original: ${s.label})` : s.heading),
                    h("dd", {}, s.text))))
                  : [h("p", { class: "note" }, "Este resumo não tem seções rotuladas; texto original completo:"), h("p", {}, work.abstract)]),
            h("section", { class: "block" }, h("h2", {}, "Números e dados estatísticos"),
              data.findings.length
                ? data.findings.map((f) => h("blockquote", { class: "finding" }, h("small", {}, f.tags.join(" · ")), f.sentence))
                : h("p", { class: "muted" }, "Nenhum dado estatístico foi encontrado no resumo."),
              h("p", { class: "note" }, "Frases copiadas do resumo; nada foi gerado nem interpretado. A seleção é por palavras-chave e pode omitir frases. Lido apenas o resumo, não o texto completo.")),
            h("section", { class: "block" }, h("h2", {}, "Citar"),
              h("div", { class: "row", role: "group", "aria-label": "Estilo da citação" }, Object.keys(data.citations).map((st) => h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: () => showCitation(st) }, st))),
              citationBox,
              referenceExport(work))),
          h("aside", { class: "article-aside", "aria-label": "Avaliação e detalhes" },
            reliabilityCard(data.reliability),
            h("section", { class: "card stack" }, h("h3", {}, "Detalhes"),
              h("table", {}, h("tbody", {}, meta.map(([k, v]) => h("tr", {}, h("th", { scope: "row" }, k), h("td", {}, v))))),
              work.keywords.length ? h("div", { class: "kw" }, work.keywords.map((k) => h("a", { href: Lib.buildHash("/busca", { q: k }) }, k))) : null),
            h("section", { class: "card stack" }, h("h3", {}, "Registro e dados"), openData),
            showHealth() ? h("section", { class: "card stack" }, h("h3", {}, "Situação no Brasil"), brasilBox) : null,
            h("section", { class: "card stack" }, h("h3", {}, "Análises do Laboratório"), analysesBox),
            h("section", { class: "card stack" }, h("h3", {}, "Organizar"), organize),
          )),
        similarSection));
    renderOrganize();
    renderAnalyses();
    renderOpenData();
    if (showHealth()) renderBrasil();
    renderSimilar();
  }

  // ------------------------------------------------------------------ Biblioteca
  async function renderLibrary(params) {
    setTitle("Biblioteca");
    if (!session.user) {
      mount($app, h("h1", {}, "Biblioteca"), h("div", { class: "empty card" },
        h("p", {}, "Entre na sua conta para ver seus artigos salvos e suas listas de leitura."),
        h("button", { type: "button", class: "btn btn-primary", onclick: () => openAuth("Entre para acessar sua biblioteca.") }, "Entrar")));
      return;
    }
    mount($app, h("h1", {}, "Biblioteca"), loading());
    const data = await guarded(() => api("/api/library"));
    if (!data) { mount($app, h("h1", {}, "Biblioteca"), errorBox("Não foi possível carregar sua biblioteca.")); return; }
    const saved = await guarded(() => api("/api/analyses"));
    const reports = await guarded(() => api("/api/reports"));
    const activeTag = params.get("tag") || "";
    const allTags = [...new Set(data.items.flatMap((i) => i.tags))].sort();
    const shown = data.items.filter((i) => !activeTag || i.tags.includes(activeTag));

    const listName = h("input", { type: "text", id: "list-name", placeholder: "nome da lista (ex.: Leituras da semana 3)", maxlength: "80" });
    const createList = async () => {
      if (!listName.value.trim()) return;
      if (await guarded(() => api("/api/lists", { method: "POST", body: { name: listName.value } }))) renderLibrary(params);
    };

    mount($app,
      h("h1", {}, "Biblioteca"),
      h("p", { class: "lead" }, `${data.items.length} ${data.items.length === 1 ? "artigo salvo" : "artigos salvos"}. Etiquete, exporte e monte listas para compartilhar.`),
      data.items.length ? h("div", { class: "library-toolbar" },
        allTags.length ? h("div", { class: "chips", role: "group", "aria-label": "Filtrar por etiqueta" },
          h("a", { class: `chip${activeTag ? "" : " active"}`, href: "#/biblioteca" }, "Todas"),
          allTags.map((t) => h("a", { class: `chip${t === activeTag ? " active" : ""}`, href: Lib.buildHash("/biblioteca", { tag: t }) }, t))) : h("span", {}),
        exportMenu()) : null,
      !data.items.length
        ? h("div", { class: "empty card" }, h("p", {}, "Sua biblioteca está vazia."), h("a", { class: "btn btn-primary", href: "#/busca" }, "Buscar artigos"))
        : h("div", { class: "table-wrap" }, h("table", { class: "library-table" },
          h("thead", {}, h("tr", {},
            h("th", { scope: "col" }, "Artigo"), h("th", { scope: "col", class: "col-year" }, "Ano"),
            h("th", { scope: "col", class: "col-type" }, "Tipo"), h("th", { scope: "col" }, "Etiquetas"),
            h("th", { scope: "col", class: "col-actions" }, h("span", { class: "visually-hidden" }, "Ações")))),
          h("tbody", {}, shown.map((item) => h("tr", {},
            h("td", { class: "col-title" }, h("a", { href: articleHref(item) }, item.title), h("div", { class: "meta" }, [item.authors, item.journal].filter(Boolean).join(" · "))),
            h("td", { class: "col-year" }, item.year || "—"),
            h("td", { class: "col-type" }, (item.studyTypes || [])[0] || "Artigo"),
            h("td", {}, item.tags.length ? h("div", { class: "chips" }, item.tags.map((t) => h("span", { class: "chip" }, t))) : h("span", { class: "muted" }, "—")),
            h("td", { class: "col-actions" }, h("button", { type: "button", class: "btn btn-sm btn-ghost", "aria-label": `Remover ${item.title} da biblioteca`, onclick: async () => {
              if (await guarded(() => api(`/api/library?ref=${encodeURIComponent(item.ref)}`, { method: "DELETE" }))) renderLibrary(params);
            } }, "Remover"))))))),
      h("h2", {}, "Listas de leitura"),
      h("div", { class: "row" }, listName, h("button", { type: "button", class: "btn btn-primary", onclick: createList }, "Criar lista")),
      data.lists.length ? data.lists.map((list) => renderListCard(list, params))
        : h("p", { class: "muted" }, "Nenhuma lista ainda. Crie uma e adicione artigos pela página de cada artigo."),
      h("h2", {}, "Relatórios de tema"),
      reportRows(reports, () => renderLibrary(params)),
      h("h2", {}, "Análises salvas"),
      saved && saved.analyses.length
        ? h("ul", { class: "analysis-list" }, saved.analyses.map((item) => analysisRow(item, { showTitle: true, onChange: () => renderLibrary(params) })))
        : h("p", { class: "muted" }, "Nenhuma análise salva ainda. No Laboratório de IA, clique em \"Salvar no artigo\" depois de gerar uma análise."));
  }

  // listas abertas sobrevivem aos redesenhos da biblioteca (tirar artigo, compartilhar...)
  const openLists = new Set();

  function renderListCard(list, params) {
    const linkBox = h("div", { class: "stack" });
    const showLink = (token) => {
      const url = `${location.origin}/#/lista/${token}`;
      mount(linkBox, h("div", { class: "citation" }, url),
        h("div", { class: "row" },
          h("button", { type: "button", class: "btn btn-sm btn-secondary", onclick: () => copyText(url, "Link copiado") }, "Copiar link"),
          h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: async () => {
            if (await guarded(() => api(`/api/lists/${list.id}/share`, { method: "DELETE" }))) { toast("Compartilhamento desativado"); renderLibrary(params); }
          } }, "Desativar link"),
          h("span", { class: "note" }, "Qualquer pessoa com o link pode ver esta lista (somente leitura).")));
    };
    if (list.shareToken) showLink(list.shareToken);
    const bodyId = `list-${list.id}`;
    const expanded = openLists.has(list.id);
    const toggle = h("button", { type: "button", class: "list-toggle", "aria-expanded": String(expanded), "aria-controls": bodyId },
      icon("chevron"), h("span", { class: "list-name" }, list.name),
      h("span", { class: "muted count" }, `${list.works.length} ${list.works.length === 1 ? "artigo" : "artigos"}`));
    const body = h("div", { id: bodyId, class: "list-body stack", hidden: expanded ? null : "" },
      list.works.length ? h("ul", { class: "list-items" }, list.works.map((w) => h("li", {},
        h("a", { href: articleHref(w) }, w.title),
        h("button", { type: "button", class: "btn btn-sm btn-ghost", "aria-label": `Tirar ${w.title} da lista`, onclick: async () => {
          if (await guarded(() => api(`/api/lists/${list.id}/items?ref=${encodeURIComponent(w.ref)}`, { method: "DELETE" }))) renderLibrary(params);
        } }, "Tirar")))) : h("p", { class: "muted" }, "Lista vazia."),
      h("div", { class: "row list-actions" },
        h("button", { type: "button", class: "btn btn-secondary btn-sm", disabled: !list.works.length, onclick: async () => {
          const shared = await guarded(() => api(`/api/lists/${list.id}/share`, { method: "POST", body: {} }));
          if (shared) { showLink(shared.token); copyText(`${location.origin}/#/lista/${shared.token}`, "Link copiado"); }
        } }, "Compartilhar por link"),
        h("button", { type: "button", class: "btn btn-secondary btn-sm", disabled: !list.works.length, onclick: () => createReportFromList(list) }, "Criar relatório"),
        list.works.length ? exportMenu(list.id) : null,
        h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: async () => {
          if (await guarded(() => api(`/api/lists/${list.id}`, { method: "DELETE" }))) renderLibrary(params);
        } }, "Excluir lista")),
      linkBox);
    toggle.addEventListener("click", () => {
      const open = body.hidden;
      body.hidden = !open;
      toggle.setAttribute("aria-expanded", String(open));
      if (open) openLists.add(list.id); else openLists.delete(list.id);
    });
    return h("section", { class: "list-block" }, h("h3", {}, toggle), body);
  }

  // cartões da situação no Brasil (artigo e relatório): dados oficiais locais, sem IA
  const METHODS = { sinonimo: "sinônimo conhecido", cognato: "nome parecido" };
  const CATEGORY_PLURAL = { Genérico: "genéricos", Similar: "similares", Novo: "novos", Biológico: "biológicos", Específico: "específicos", Fitoterápico: "fitoterápicos", Dinamizado: "dinamizados", Radiofármaco: "radiofármacos" };
  const fmtDate = (iso) => { const d = new Date(`${iso}T12:00:00`); return Number.isNaN(d.getTime()) ? "" : d.toLocaleDateString("pt-BR"); };
  const fmtMonth = (ym) => (/^\d{4}-\d{2}$/.test(ym) ? `${ym.slice(5)}/${ym.slice(0, 4)}` : "");
  function conitecRows(records) {
    const rowFor = (r) => h("li", { class: "conitec-row" },
      h("div", {}, h("strong", {}, `${r.year || "—"} · ${r.recommendation || "—"}`),
        r.decisionMs && r.decisionMs !== r.recommendation ? h("span", { class: "muted" }, ` · decisão do MS: ${r.decisionMs}`) : null),
      r.indication ? h("p", { class: "conitec-indication" }, r.indication.length > 160 ? `${r.indication.slice(0, 157)}…` : r.indication) : null,
      h("small", { class: "muted" }, [r.ordinance, r.publishedAt ? fmtDate(r.publishedAt) : "", r.technicalReport ? `Relatório técnico ${r.technicalReport}` : ""].filter(Boolean).join(" · ")));
    const first = records.slice(0, 3);
    const rest = records.slice(3);
    return [h("ul", { class: "plain-list" }, first.map(rowFor)),
      rest.length ? h("details", { class: "more-records" }, h("summary", {}, `Ver as outras ${rest.length} decisões`), h("ul", { class: "plain-list" }, rest.map(rowFor))) : null];
  }
  function anvisaSummary(s) {
    const cats = Object.entries(s.categories).slice(0, 4).map(([name, n]) => `${Lib.formatCount(n)} ${CATEGORY_PLURAL[name] || name.toLowerCase()}`).join(" · ");
    return h("li", { class: "anvisa-row" },
      h("div", {}, h("strong", {}, `${s.name}: ${Lib.formatCount(s.active)} ${s.active === 1 ? "registro ativo" : "registros ativos"}`),
        s.inactive ? h("span", { class: "muted" }, ` · ${Lib.formatCount(s.inactive)} inativos`) : null),
      h("small", { class: "muted" }, [cats, s.companies ? `${s.companies} ${s.companies === 1 ? "empresa" : "empresas"}` : "",
        s.validUntil ? `validade mais distante ${fmtMonth(s.validUntil)}` : "", s.classes.length ? `classe: ${s.classes.join(", ")}` : ""].filter(Boolean).join(" · ")));
  }
  function anvisaBlock(list, key) {
    if (!list.length) return h("p", { class: "muted" }, "ANVISA: nenhum registro de medicamento com esta substância.");
    const exact = list.find((s) => s.key === key) || list[0];
    const others = list.filter((s) => s !== exact);
    return [h("h5", {}, "Registro na ANVISA"), h("ul", { class: "plain-list" }, anvisaSummary(exact)),
      others.length ? h("details", { class: "more-records" }, h("summary", {}, `Associações e outras formas (${others.length})`), h("ul", { class: "plain-list" }, others.map(anvisaSummary))) : null];
  }
  function renameSummary(r) {
    const rows = r.presentations.map((a) => h("li", {}, `${a.text} · ${a.component}`, h("span", { class: "muted" }, ` (p. ${a.page} do PDF)`)));
    const more = r.totalPresentations - r.presentations.length;
    return h("li", { class: "anvisa-row" },
      h("div", {}, h("strong", {}, `${r.name}: consta na Rename 2024`), h("span", { class: "muted" }, ` · componente ${r.components.join(", ").toLowerCase()}`)),
      h("details", { class: "more-records" }, h("summary", {}, `Apresentações listadas (${r.totalPresentations})`),
        h("ul", { class: "plain-list" }, rows, more > 0 ? h("li", { class: "muted" }, `e mais ${more} no PDF`) : null)));
  }
  function renameBlock(list, key) {
    if (!list.length) return h("p", { class: "muted" }, "Rename 2024: a substância não consta na relação nacional de medicamentos essenciais.");
    const exact = list.find((r) => r.key === key) || list[0];
    const others = list.filter((r) => r !== exact);
    return [h("h5", {}, "Rename 2024 (medicamentos essenciais)"), h("ul", { class: "plain-list" }, renameSummary(exact)),
      others.length ? h("details", { class: "more-records" }, h("summary", {}, `Associações e outras formas (${others.length})`), h("ul", { class: "plain-list" }, others.map(renameSummary))) : null];
  }
  function situationBlock(item, key) {
    return [renameBlock(item.rename || [], key), anvisaBlock(item.anvisa, key),
      h("h5", {}, "Decisões da Conitec (incorporação ao SUS)"),
      item.conitec.length ? conitecRows(item.conitec) : h("p", { class: "muted" }, "A Conitec não tem decisão registrada para esta substância.")];
  }

  // ------------------------------------------------------------------ perfil de uso
  // O perfil só escolhe o que fica em destaque e liga o pacote "Saúde no Brasil"; nenhuma função do núcleo é bloqueada.
  const showHealth = () => session.healthPack !== false;
  const PROFILE_SHORTCUTS = {
    estudante: [["Procurar artigos para o seu trabalho", "#/busca"], ["Montar uma lista e criar o relatório de tema", "#/biblioteca"], ["Exportar as referências em ABNT, APA ou Vancouver", "#/biblioteca"]],
    pesquisador: [["Acompanhar temas e receber avisos de artigos novos", "#/perfil/interesses"], ["Levar as referências para o Zotero, Mendeley ou EndNote", "#/biblioteca"], ["Criar um relatório de tema com o método declarado", "#/biblioteca"]],
    saude: [["Ver a situação de um medicamento no Brasil (ANVISA, Conitec, Rename)", Lib.buildHash("/busca", { q: "metformina" })], ["Acompanhar especialidades e receber avisos", "#/perfil/interesses"], ["Criar um relatório com a situação regulatória dos medicamentos", "#/biblioteca"]],
    consultoria: [["Criar um relatório de tema com método e histórico", "#/biblioteca"], ["Acompanhar os temas dos seus clientes", "#/perfil/interesses"], ["Exportar as referências para o cliente", "#/biblioteca"]],
  };
  const PROFILE_SKIP_KEY = () => `bdd.profile.skip:${session.user}`;
  let profileOptionsPromise;
  const loadProfileOptions = () => {
    profileOptionsPromise ||= api("/api/profile/options").catch((error) => { profileOptionsPromise = undefined; throw error; });
    return profileOptionsPromise;
  };

  function profileShortcuts() {
    const items = session.user && PROFILE_SHORTCUTS[session.profile];
    if (!items) return null;
    return h("section", { class: "home-section profile-shortcuts", "aria-labelledby": "para-voce" },
      h("p", { class: "eyebrow" }, "Para você"),
      h("h2", { id: "para-voce" }, "Por onde começar"),
      h("ul", { class: "plain-list shortcut-list" }, items.map(([label, href]) => h("li", {}, h("a", { href }, label)))),
      h("p", { class: "note" }, h("a", { href: "#/perfil/uso" }, "Mudar perfil e preferências")));
  }

  /** Formulário do perfil (usado na pergunta da primeira entrada e na tela de perfil). */
  function profileForm({ onSaved, onSkip } = {}) {
    const box = h("div", { class: "stack" }, loading());
    loadProfileOptions().then(({ profiles }) => {
      let chosen = session.profile || "";
      const healthBox = h("input", { type: "checkbox", id: "profile-health" });
      healthBox.checked = session.healthPack !== false;
      const group = h("div", { class: "stack", role: "radiogroup", "aria-label": "O que você faz" });
      const paintGroup = () => mount(group, profiles.map((p) => {
        const input = h("input", { type: "radio", name: "profile", id: `profile-${p.key}`, value: p.key });
        input.checked = chosen === p.key;
        input.addEventListener("change", () => { chosen = p.key; healthBox.checked = p.healthPack; paintGroup(); });
        return h("label", { class: `profile-option${chosen === p.key ? " is-chosen" : ""}`, for: `profile-${p.key}` }, input,
          h("span", {}, h("strong", {}, p.label), h("small", { class: "muted" }, p.description)));
      }));
      paintGroup();
      const status = h("p", { class: "note", role: "status" });
      const save = h("button", { type: "button", class: "btn btn-primary" }, "Salvar");
      save.addEventListener("click", async () => {
        if (!chosen) { status.textContent = "Escolha uma das opções."; return; }
        save.disabled = true;
        const saved = await guarded(() => api("/api/profile", { method: "PUT", body: { profile: chosen, healthPack: healthBox.checked } }));
        save.disabled = false;
        if (!saved) return;
        session.profile = saved.profile;
        session.healthPack = saved.healthPack;
        toast("Perfil salvo.");
        if (onSaved) onSaved(saved);
      });
      mount(box, group,
        h("label", { class: "report-include", for: "profile-health" }, healthBox,
          h("span", {}, h("strong", {}, "Mostrar a situação de medicamentos no Brasil"), h("small", { class: "muted" }, " ANVISA, Conitec e Rename, nos artigos e nos relatórios"))),
        status,
        h("div", { class: "row" }, save, onSkip ? h("button", { type: "button", class: "btn btn-ghost", onclick: onSkip }, "Agora não") : null));
    }).catch(() => mount(box, errorBox("Não foi possível carregar as opções agora.")));
    return box;
  }

  function askProfile() {
    if (!session.user || session.profile) return;
    try { if (localStorage.getItem(PROFILE_SKIP_KEY())) return; } catch { /* modo privado: pergunta de novo */ }
    if (document.getElementById("profile-dialog")) return;
    const dialogEl = h("dialog", { id: "profile-dialog", "aria-labelledby": "profile-title" });
    const close = () => { dialogEl.close(); dialogEl.remove(); };
    dialogEl.addEventListener("close", () => dialogEl.remove());
    dialogEl.append(h("div", { class: "auth-card stack" },
      h("h2", { id: "profile-title" }, "Como você vai usar o Biomedical Data Digger?"),
      h("p", { class: "hint" }, "Isso só escolhe o que fica em destaque. Você pode mudar quando quiser em Perfil e preferências, e nada fica bloqueado."),
      profileForm({
        onSaved: () => { close(); render(); },
        onSkip: () => { try { localStorage.setItem(PROFILE_SKIP_KEY(), "1"); } catch { /* sem armazenamento */ } close(); },
      })));
    document.body.append(dialogEl);
    if (typeof dialogEl.showModal === "function") dialogEl.showModal();
  }

  async function syncProfile() {
    if (!session.user) { session.profile = ""; session.healthPack = true; profileLink.hidden = true; return; }
    profileLink.hidden = false;
    try {
      const data = await api("/api/profile");
      session.profile = data.profile || "";
      session.healthPack = data.healthPack;
    } catch { return; }
    askProfile();
    render();
  }

  // ------------------------------------------------------------------ Feed de novidades acadêmicas
  const FEED_REFRESH_MS = 8000;
  const FEED_MAX_RETRIES = 4;
  let feedAreasPromise;
  const loadFeedAreas = () => {
    feedAreasPromise ||= api("/api/interests/options").then((data) => data.areas).catch(() => { feedAreasPromise = undefined; return []; });
    return feedAreasPromise;
  };

  function feedWhen(item) {
    if (!item.dateKnown) return "data não informada";
    const hours = Math.floor((Date.now() - new Date(item.publishedAt).getTime()) / 3600000);
    if (hours < 1) return "agora há pouco";
    if (hours < 24) return `há ${hours} h`;
    if (hours < 48) return "ontem";
    return fmtDate(item.publishedAt.slice(0, 10));
  }

  function feedCard(item) {
    const internal = item.internal === true;
    const link = h("a", internal
      ? { href: item.url }
      : { href: item.url, target: "_blank", rel: "noopener noreferrer nofollow" }, item.title, internal ? null : icon("external"));
    return h("article", { class: "feed-card" },
      h("div", { class: "feed-meta" },
        h("span", { class: `feed-tier tier-${item.source.tier}` }, item.source.tierLabel),
        h("span", { class: "feed-source" }, item.source.name),
        h("span", { class: "muted" }, ` · ${feedWhen(item)}`, item.source.language && !["pt", "un"].includes(item.source.language) ? ` · ${item.source.language.toUpperCase()}` : "")),
      h("h3", {}, link),
      item.snippet ? h("p", { class: "feed-snippet" }, item.snippet) : null,
      item.matched.length ? h("div", { class: "chips" }, item.matched.map((m) => h("span", { class: "chip" }, m))) : null,
      internal ? h("a", { class: "feed-open", href: item.url }, "Ver o artigo e a nota de confiabilidade")
        : h("a", { class: "feed-open", href: item.url, target: "_blank", rel: "noopener noreferrer nofollow" }, `Ler em ${item.source.name}`, icon("external")));
  }

  async function renderFeed(params) {
    setTitle("Feed");
    const state = {
      mode: params.get("modo") === "tudo" ? "tudo" : "voce", kind: ["artigos", "noticias"].includes(params.get("tipo")) ? params.get("tipo") : "todos",
      area: (params.get("area") || "").replace(/[^a-z-]/g, "").slice(0, 30), lang: ["pt", "en"].includes(params.get("lang")) ? params.get("lang") : "",
    };
    const go = (changes) => { location.hash = Lib.buildHash("/feed", { modo: state.mode === "tudo" ? "tudo" : "", tipo: state.kind === "todos" ? "" : state.kind, area: state.area, lang: state.lang, ...changes }); };
    const list = h("div", { class: "feed-list", "aria-live": "polite" });
    const more = h("div", { class: "row" });
    const status = h("p", { class: "note" });
    const controls = h("div", { class: "feed-controls card" });
    mount($app, h("h1", {}, "Feed"),
      h("p", { class: "lead" }, "Novidades de revistas, instituições de pesquisa e divulgação científica, em todas as áreas do conhecimento. Ao clicar, você vai para a fonte."),
      controls, list, more, status, feedSourcesPanel());

    const areas = await loadFeedAreas();
    let page = 1;
    let retries = 0;
    let hasInterests = false;
    const chip = (label, active, onclick) => h("button", { type: "button", class: "pick", "aria-pressed": String(active), onclick }, label);
    const paintControls = () => mount(controls,
      hasInterests ? h("div", { class: "pick-row", role: "group", "aria-label": "Mostrar" },
        chip("Para você", state.mode === "voce", () => go({ modo: "" })), chip("Tudo", state.mode === "tudo", () => go({ modo: "tudo" }))) : null,
      h("div", { class: "pick-row", role: "group", "aria-label": "Tipo" },
        [["todos", "Tudo"], ["artigos", "Artigos"], ["noticias", "Notícias"]].map(([key, label]) => chip(label, state.kind === key, () => go({ tipo: key === "todos" ? "" : key })))),
      h("div", { class: "row" },
        h("select", { "aria-label": "Área do conhecimento", onchange: (event) => go({ area: event.target.value }) },
          h("option", { value: "" }, "Todas as áreas"), areas.map((a) => h("option", { value: a.key, selected: a.key === state.area ? "" : null }, a.label))),
        h("select", { "aria-label": "Idioma", onchange: (event) => go({ lang: event.target.value }) },
          [["", "Qualquer idioma"], ["pt", "Português"], ["en", "Inglês"]].map(([value, label]) => h("option", { value, selected: value === state.lang ? "" : null }, label)))));

    async function load(reset) {
      if (reset) { page = 1; mount(list, loading("Carregando as novidades…")); mount(more); }
      const query = new URLSearchParams({ mode: state.mode, kind: state.kind, page: String(page) });
      if (state.area) query.set("area", state.area);
      if (state.lang) query.set("lang", state.lang);
      let data;
      try { data = await api(`/api/feed?${query}`); } catch (error) { mount(list, errorBox(error.message)); return; }
      hasInterests = data.hasInterests;
      paintControls();
      if (reset) mount(list);
      list.append(...data.items.map(feedCard));
      if (!list.children.length) {
        if (data.refreshing && retries < FEED_MAX_RETRIES) {
          mount(list, loading("Buscando as primeiras novidades nas fontes (pode levar cerca de um minuto)…"));
          retries += 1;
          setTimeout(() => { if (location.hash.startsWith("#/feed")) load(true); }, FEED_REFRESH_MS);
          return;
        }
        mount(list, h("div", { class: "empty card" },
          h("p", {}, data.personalized ? "Nenhuma novidade sobre os seus interesses por enquanto." : "Nenhuma novidade com esses filtros."),
          h("div", { class: "row" },
            data.personalized ? h("button", { type: "button", class: "btn btn-secondary", onclick: () => go({ modo: "tudo" }) }, "Ver tudo") : null,
            session.user && !data.hasInterests ? h("a", { class: "btn btn-primary", href: "#/perfil/interesses" }, "Escolher interesses") : null,
            !session.user ? h("button", { type: "button", class: "btn btn-primary", onclick: () => openAuth("Entre para ver o feed dos seus interesses.") }, "Entrar") : null)));
      }
      mount(more, data.hasMore ? h("button", { type: "button", class: "btn btn-secondary", onclick: () => { page += 1; load(false); } }, "Carregar mais") : null);
      status.textContent = data.updatedAt ? `Fontes atualizadas pela última vez em ${fmtDate(data.updatedAt.slice(0, 10))}.` : "";
      if (!session.user) status.append(" Entre na sua conta para ver só o que combina com os seus interesses.");
    }
    paintControls();
    load(true);
  }

  function feedSourcesPanel() {
    const body = h("div", { class: "stack" });
    let loaded = false;
    const details = h("details", { class: "more-records feed-sources" }, h("summary", {}, "Fontes e critérios do feed"), body);
    details.addEventListener("toggle", async () => {
      if (!details.open || loaded) return;
      loaded = true;
      mount(body, loading());
      let data;
      try { data = await api("/api/feed/sources"); } catch { loaded = false; mount(body, h("p", { class: "muted" }, "Não foi possível carregar as fontes agora.")); return; }
      mount(body,
        h("p", { class: "note" }, "O feed mostra só o título, um trecho curto e o link: o conteúdo é da fonte, e você é levado a ela ao clicar. Notícias e comunicados não passam pela nota de confiabilidade dos artigos. O tipo da fonte ajuda a julgar:"),
        h("ul", { class: "plain-list" }, data.tiers.map((t) => h("li", {}, h("strong", {}, `${t.label}: `), t.description))),
        h("ul", { class: "plain-list feed-source-list" }, data.sources.map((s) => h("li", {},
          h("a", { href: s.site, target: "_blank", rel: "noopener noreferrer" }, s.name),
          h("small", { class: "muted" }, ` · ${s.tierLabel} · ${s.language.toUpperCase()} · ${s.areas.join(", ")}${s.failing ? " · fora do ar na última busca" : ""}`)))));
    });
    return details;
  }

  // ------------------------------------------------------------------ aba Perfil (visão geral, perfil de uso, interesses, conta e dados)
  const PROFILE_SECTIONS = [["", "Visão geral"], ["uso", "Perfil de uso"], ["interesses", "Interesses e alertas"], ["notificacoes", "Notificações"], ["conta", "Conta e dados"]];

  function profileTabs(active) {
    return h("nav", { class: "profile-tabs", "aria-label": "Seções do perfil" }, PROFILE_SECTIONS.map(([key, label]) =>
      h("a", { class: "profile-tab", href: key ? `#/perfil/${key}` : "#/perfil", "aria-current": key === active ? "page" : null }, label)));
  }

  async function profileOverview(content) {
    mount(content, loading());
    const [account, options] = await Promise.all([guarded(() => api("/api/account")), loadProfileOptions().catch(() => ({ profiles: [] }))]);
    if (!account) { mount(content, errorBox("Não foi possível carregar o seu perfil agora.")); return; }
    const chosen = options.profiles.find((p) => p.key === (account.profile && account.profile.profile));
    const since = account.createdAt ? fmtDate(account.createdAt.slice(0, 10)) : "";
    const stat = (value, label, href) => h("a", { class: "account-stat", href }, h("strong", {}, Lib.formatCount(value)), h("span", {}, label));
    const interests = account.interests || {};
    const checked = interests.lastChecked ? fmtDate(interests.lastChecked.slice(0, 10)) : "";
    mount(content,
      h("section", { class: "card account-head" },
        h("span", { class: "avatar", "aria-hidden": "true" }, account.email.slice(0, 1).toUpperCase()),
        h("div", {}, h("strong", { class: "account-email" }, account.email), since ? h("p", { class: "muted" }, `Membro desde ${since}`) : null)),
      h("div", { class: "account-stats" },
        stat(account.counts.library, account.counts.library === 1 ? "artigo salvo" : "artigos salvos", "#/biblioteca"),
        stat(account.counts.lists, account.counts.lists === 1 ? "lista" : "listas", "#/biblioteca"),
        stat(account.counts.reports, account.counts.reports === 1 ? "relatório" : "relatórios", "#/biblioteca"),
        stat(account.counts.analyses, account.counts.analyses === 1 ? "análise salva" : "análises salvas", "#/biblioteca")),
      h("section", { class: "card stack" }, h("h2", {}, "Perfil de uso"),
        chosen ? h("p", {}, h("strong", {}, chosen.label), h("span", { class: "muted" }, ` · pacote Saúde no Brasil ${account.profile.healthPack ? "ligado" : "desligado"}`))
          : h("p", { class: "muted" }, "Você ainda não escolheu. Isso só define o que fica em destaque; nada é bloqueado."),
        h("div", { class: "row" }, h("a", { class: "btn btn-secondary btn-sm", href: "#/perfil/uso" }, chosen ? "Alterar" : "Escolher"))),
      h("section", { class: "card stack" }, h("h2", {}, "Interesses e alertas"),
        interests.topics || interests.terms
          ? h("p", {}, `${interests.topics} ${interests.topics === 1 ? "tema" : "temas"}, ${interests.terms} ${interests.terms === 1 ? "palavra-chave" : "palavras-chave"}`,
            h("span", { class: "muted" }, ` · ${interests.unread} ${interests.unread === 1 ? "aviso não lido" : "avisos não lidos"}${checked ? ` · última verificação em ${checked}` : ""}`))
          : h("p", { class: "muted" }, "Você ainda não escolheu o que acompanhar. Escolha áreas, subtemas e idiomas e avisamos quando sair artigo novo."),
        h("div", { class: "row" }, h("a", { class: "btn btn-secondary btn-sm", href: "#/perfil/interesses" }, interests.topics || interests.terms ? "Gerenciar" : "Escolher interesses"))),
      h("div", { class: "row" }, h("button", { type: "button", class: "btn btn-outline", onclick: () => logoutButton.click() }, "Sair da conta")));
  }

  async function profileNotifications(content) {
    mount(content, loading());
    const data = await guarded(() => api("/api/notifications/prefs"));
    if (!data) { mount(content, errorBox("Não foi possível carregar as notificações agora.")); return; }
    const rows = data.kinds.map((kind) => {
      const input = h("input", { type: "checkbox", id: `notif-${kind.key}` });
      input.checked = kind.enabled;
      input.addEventListener("change", async () => {
        const saved = await guarded(() => api("/api/notifications/prefs", { method: "PUT", body: { kinds: { [kind.key]: input.checked } } }));
        if (saved) toast(input.checked ? `Avisos de “${kind.label}” ligados.` : `Avisos de “${kind.label}” desligados.`);
        else input.checked = !input.checked;
      });
      return h("label", { class: "profile-option", for: `notif-${kind.key}` }, input,
        h("span", {}, h("strong", {}, kind.label, kind.priority >= 2 ? h("span", { class: "alert-kind" }, "Importante") : null), h("small", { class: "muted" }, kind.description)));
    });
    mount(content,
      h("p", { class: "lead" }, "Escolha o que aparece no sininho. Por enquanto o aviso chega só no site; e-mail e outros canais virão depois."),
      h("section", { class: "card stack" }, h("h2", {}, "O que avisar"), rows),
      h("section", { class: "card stack" }, h("h2", {}, "Como funciona"),
        h("ul", { class: "plain-list" },
          h("li", {}, "As verificações rodam quando você abre o site, no máximo a cada 6 horas."),
          h("li", {}, "Retratação: cada artigo que você guarda (biblioteca, listas e relatórios) é reconferido na fonte uma vez por semana. Só detectamos quando a fonte informa (Europe PMC, PubMed e OpenAlex); correções não são detectadas."),
          h("li", {}, "Mudança regulatória: vale para as substâncias que você confirmou em relatórios. Comparamos com o que havia na última verificação."),
          h("li", {}, "O primeiro aviso de cada tipo só guarda o estado de hoje; você é avisado do que mudar depois.")),
        h("div", { class: "row" }, h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: () => runCheck(true) }, "Verificar agora"))));
  }

  function profileUse(content) {
    mount(content,
      h("p", { class: "lead" }, "Diga o que você faz para destacarmos as ferramentas certas na página inicial e ligar ou desligar o pacote de saúde. Nada do núcleo (busca, biblioteca, alertas, relatórios e exportação) é bloqueado por esta escolha."),
      h("section", { class: "card stack" }, profileForm({ onSaved: () => renderProfile("uso") })));
  }

  function profileAccount(content) {
    const passwordStatus = h("p", { class: "note", role: "status" });
    const field = (id, label, autocomplete) => {
      const input = h("input", { type: "password", id, autocomplete, maxlength: "128", required: "" });
      return [h("div", { class: "field" }, h("label", { for: id }, label), input), input];
    };
    const [currentField, currentInput] = field("pw-current", "Senha atual", "current-password");
    const [newField, newInput] = field("pw-new", "Nova senha (mínimo de 8 caracteres)", "new-password");
    const [repeatField, repeatInput] = field("pw-repeat", "Repita a nova senha", "new-password");
    const saveButton = h("button", { type: "submit", class: "btn btn-primary" }, "Trocar senha");
    const passwordForm = h("form", { class: "stack", onsubmit: async (event) => {
      event.preventDefault();
      passwordStatus.textContent = "";
      if (newInput.value !== repeatInput.value) { passwordStatus.textContent = "As senhas novas não são iguais."; return; }
      saveButton.disabled = true;
      try {
        await api("/api/account/password", { method: "POST", body: { current: currentInput.value, new: newInput.value } });
        passwordForm.reset();
        toast("Senha alterada.");
        passwordStatus.textContent = "Senha alterada. Outros aparelhos já conectados continuam conectados até a sessão expirar (7 dias).";
      } catch (error) { passwordStatus.textContent = error.message; } finally { saveButton.disabled = false; }
    } }, currentField, newField, repeatField, passwordStatus, h("div", { class: "row" }, saveButton));

    const deleteBox = h("div", { class: "stack" });
    const showDelete = () => {
      const input = h("input", { type: "password", id: "delete-password", autocomplete: "current-password", maxlength: "128", "aria-label": "Sua senha, para confirmar" });
      const status = h("p", { class: "note", role: "alert" });
      const confirmButton = h("button", { type: "button", class: "btn btn-danger" }, "Excluir definitivamente");
      confirmButton.addEventListener("click", async () => {
        if (!input.value) { status.textContent = "Digite a sua senha para confirmar."; input.focus(); return; }
        confirmButton.disabled = true;
        try {
          await api("/api/account", { method: "DELETE", body: { password: input.value } });
          setUser("");
          toast("Conta excluída.");
          location.hash = "#/";
          render();
        } catch (error) { status.textContent = error.message; confirmButton.disabled = false; }
      });
      mount(deleteBox,
        h("p", { class: "note" }, "Isso apaga a conta e tudo o que ela guardou, sem volta. Baixe os seus dados antes, se quiser."),
        h("div", { class: "field" }, h("label", { for: "delete-password" }, "Sua senha"), input), status,
        h("div", { class: "row" }, confirmButton, h("button", { type: "button", class: "btn btn-ghost", onclick: () => mount(deleteBox, startDelete) }, "Cancelar")));
      input.focus();
    };
    const startDelete = h("button", { type: "button", class: "btn btn-outline btn-danger-outline", onclick: showDelete }, "Excluir minha conta…");
    mount(deleteBox, startDelete);

    mount(content,
      h("section", { class: "card stack" }, h("h2", {}, "Senha"), passwordForm),
      h("section", { class: "card stack" }, h("h2", {}, "Seus dados"),
        h("p", {}, "Baixe uma cópia de tudo o que a sua conta guarda: biblioteca, listas, análises salvas, relatórios, interesses, avisos e perfil. A senha não entra no arquivo."),
        h("div", { class: "row" }, h("a", { class: "btn btn-secondary", href: "/api/account/export", download: "" }, icon("download"), "Baixar meus dados (JSON)"))),
      h("section", { class: "card stack danger-zone" }, h("h2", {}, "Excluir conta"),
        h("p", {}, "Apaga a conta e todos os dados dela: biblioteca, listas (inclusive os links compartilhados), análises salvas, relatórios, interesses, avisos e perfil. Não há como desfazer."),
        deleteBox));
  }

  function renderProfile(section = "") {
    const active = PROFILE_SECTIONS.some(([key]) => key === section) ? section : "";
    setTitle(active ? `Perfil: ${PROFILE_SECTIONS.find(([key]) => key === active)[1]}` : "Perfil");
    if (!session.user) {
      mount($app, h("h1", {}, "Perfil"), h("div", { class: "empty card" },
        h("p", {}, "Entre na sua conta para ver o seu perfil, escolher interesses e gerenciar os seus dados."),
        h("button", { type: "button", class: "btn btn-primary", onclick: () => openAuth("Entre para acessar o seu perfil.") }, "Entrar")));
      return;
    }
    const content = h("div", { class: "stack profile-content" });
    mount($app, h("h1", {}, "Perfil"), profileTabs(active), content);
    if (active === "uso") profileUse(content);
    else if (active === "interesses") renderInterests(content);
    else if (active === "notificacoes") profileNotifications(content);
    else if (active === "conta") profileAccount(content);
    else profileOverview(content);
  }

  // ------------------------------------------------------------------ Relatório de tema
  const REPORT_DOWNLOADS = [["Página web (.html)", "html"], ["Word (.docx)", "docx"], ["Markdown (.md)", "md"]];

  async function createReportFromList(list) {
    const created = await guarded(() => api("/api/reports", { method: "POST", body: { list_id: list.id } }));
    if (created) { toast("Relatório criado. Revise os estudos e o método."); location.hash = `#/relatorio/${created.id}`; }
  }

  function reportRows(reports, onChange) {
    if (!reports || !reports.reports.length) return h("p", { class: "muted" }, "Nenhum relatório ainda. Abra uma lista e clique em “Criar relatório”.");
    return h("ul", { class: "analysis-list" }, reports.reports.map((r) => h("li", { class: "analysis-item" },
      h("a", { href: `#/relatorio/${r.id}`, class: "analysis-article" }, r.title),
      h("small", { class: "muted" }, `${r.included} de ${r.total} estudos · versão ${r.version} · lista “${r.listName}” · ${fmtDate(r.updatedAt.slice(0, 10))}`),
      h("div", { class: "row" },
        h("a", { class: "btn btn-sm btn-secondary", href: `#/relatorio/${r.id}` }, "Abrir"),
        h("button", { type: "button", class: "btn btn-sm btn-ghost", "aria-label": `Excluir o relatório ${r.title}`, onclick: async () => {
          if (await guarded(() => api(`/api/reports/${r.id}`, { method: "DELETE" }))) { toast("Relatório excluído."); onChange(); }
        } }, "Excluir")))));
  }

  // seção "Situação no Brasil" do relatório: o autor confirma as substâncias; os cartões vêm das bases oficiais locais
  const MAX_REPORT_SUBSTANCES = 10;
  const plainTerm = (text) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().trim();

  function reportBrasil(reportId, initial) {
    const box = h("div", { class: "stack" }, loading("Consultando dados oficiais…"));
    const entries = new Map(); // termo -> { nome, hint }
    const picked = new Set(initial);
    const checklist = h("div", { class: "stack", role: "group", "aria-label": "Substâncias para a seção Situação no Brasil" });
    const cards = h("div", { class: "stack" });
    const note = h("p", { class: "note" });
    const manualInput = h("input", { type: "text", placeholder: "Outro medicamento (nome em português)", maxlength: "80", "aria-label": "Adicionar medicamento" });
    const manualButton = h("button", { type: "button", class: "btn btn-secondary btn-sm" }, "Adicionar");

    function paintChecklist() {
      if (!entries.size) {
        mount(checklist, h("p", { class: "muted" }, "Não identificamos substâncias nos resumos dos estudos incluídos. Se o tema é um medicamento, adicione o nome abaixo."));
        return;
      }
      mount(checklist, [...entries].map(([termo, entry]) => {
        const input = h("input", { type: "checkbox", id: `sub-${termo.replace(/\W+/g, "-")}` });
        input.checked = picked.has(termo);
        input.addEventListener("change", () => {
          if (input.checked && picked.size >= MAX_REPORT_SUBSTANCES) { input.checked = false; toast(`Escolha no máximo ${MAX_REPORT_SUBSTANCES} substâncias.`); return; }
          if (input.checked) picked.add(termo); else picked.delete(termo);
        });
        return h("label", { class: "report-include", for: input.id }, input, h("span", {}, h("strong", {}, entry.nome), h("small", { class: "muted" }, ` · ${entry.hint}`)));
      }));
    }

    async function load() {
      let data;
      try { data = await api(`/api/reports/${encodeURIComponent(reportId)}/brasil`); } catch {
        mount(box, h("p", { class: "muted" }, "Os dados oficiais do Brasil não estão disponíveis agora. O relatório pode ser salvo sem esta seção."));
        return;
      }
      for (const s of data.suggestions) {
        entries.set(s.termo, { nome: s.nome, hint: `citada em ${s.studies} ${s.studies === 1 ? "estudo" : "estudos"}; no texto: ${s.en} (${METHODS[s.metodo] || s.metodo}). Confirme` });
      }
      picked.clear();
      for (const c of data.confirmed) {
        picked.add(c.termo);
        if (!entries.has(c.termo)) entries.set(c.termo, { nome: c.nome, hint: "confirmada por você" });
      }
      paintChecklist();
      mount(cards, data.confirmed.map((c) => h("div", { class: "conitec-drug" }, h("h4", {}, c.nome), situationBlock(c, c.termo))));
      const meta = data.meta;
      note.textContent = `Bases consultadas por código, sem IA: ANVISA (extraída em ${fmtDate(meta.anvisa.extraidoEm)}), Conitec (extraída em ${fmtDate(meta.conitec.extraidoEm)}) e Rename 2024 (extraída em ${fmtDate(meta.rename.extraidoEm)}). `
        + "Constar na Rename ou ter registro na ANVISA não significa disponibilidade na unidade de saúde. Os dados ainda não foram revisados por farmacêutico ou médico.";
      mount(box, h("p", { class: "hint" }, "Opcional, para temas de medicamento. Marque as substâncias que o relatório deve tratar: a ligação do nome é automática e só entra no documento o que você confirmar. Salve para ver a situação de cada uma."),
        checklist,
        h("div", { class: "new-list" }, manualInput, manualButton),
        data.confirmed.length ? h("h3", {}, "Como aparecerá no documento") : null, cards, note);
    }

    async function addManual() {
      const query = manualInput.value.trim();
      if (query.length < 3) { manualInput.focus(); return; }
      if (picked.size >= MAX_REPORT_SUBSTANCES) { toast(`Escolha no máximo ${MAX_REPORT_SUBSTANCES} substâncias.`); return; }
      const found = await guarded(() => api(`/api/brasil/medicamento?q=${encodeURIComponent(query)}`));
      if (!found) return;
      if (!found.rename.length && !found.anvisa.length && !found.conitec.length) { toast("Não encontramos essa substância nas bases oficiais."); return; }
      const termo = plainTerm(query);
      entries.set(termo, { nome: query, hint: "adicionada por você" });
      picked.add(termo);
      manualInput.value = "";
      paintChecklist();
    }
    manualButton.addEventListener("click", addManual);
    manualInput.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); addManual(); } });
    load();
    return { node: box, selected: () => [...picked], reload: load };
  }

  // atualizar o relatório (novos na lista, busca de novidades) e histórico de versões
  const LANGUAGE_CHOICES = [["", "Qualquer idioma"], ["pt", "Português"], ["en", "Inglês"], ["es", "Espanhol"]];

  function reportUpdates({ reportId, data, save, rerender }) {
    const box = h("div", { class: "stack" }, loading("Carregando histórico…"));
    const newBox = h("div", { class: "stack" });
    const resultsBox = h("div", { class: "stack", "aria-live": "polite" });
    const versionsBox = h("div", { class: "stack" });
    const logBox = h("div", { class: "stack" });
    const queryInput = h("input", { type: "text", maxlength: "200", placeholder: "Tema ou palavras-chave (ex.: hipertensão e exercício)", "aria-label": "Procurar artigos novos sobre o tema" });
    const languageSelect = h("select", { "aria-label": "Idioma dos artigos" }, LANGUAGE_CHOICES.map(([value, label]) => h("option", { value }, label)));
    const yearInput = h("input", { type: "number", min: "1800", max: "2100", value: String(Math.max(1800, Number(data.createdAt.slice(0, 4)) - 1)), "aria-label": "Artigos desde o ano" });
    const searchButton = h("button", { type: "button", class: "btn btn-secondary btn-sm" }, "Procurar");
    let lastQuery = "";

    // salva o que está na tela antes de mudar a lista de estudos, para não perder edições
    async function addRefs(refs, origin, query = "") {
      if (!(await save())) return;
      const result = await guarded(() => api(`/api/reports/${encodeURIComponent(reportId)}/add`, { method: "POST", body: { refs, origin, query } }));
      if (!result) return;
      toast(result.added ? `${result.added} ${result.added === 1 ? "estudo adicionado" : "estudos adicionados"} ao relatório.` : "Nada novo para adicionar.");
      rerender();
    }

    async function follow() {
      const term = lastQuery.trim();
      if (!term) return;
      const prefs = await guarded(() => api("/api/interests"));
      if (!prefs) return;
      if (prefs.terms.some((t) => t.toLowerCase() === term.toLowerCase())) { toast("Esta busca já está nos seus alertas."); return; }
      if (prefs.terms.length >= 5) { toast("Você já usa as 5 palavras-chave dos alertas. Remova uma em Meus interesses."); return; }
      const saved = await guarded(() => api("/api/interests", { method: "PUT", body: { topics: prefs.topics, languages: prefs.languages, terms: [...prefs.terms, term] } }));
      if (saved) { toast("Pronto: vamos avisar no sininho quando sair artigo novo sobre isso."); syncBell(); }
    }

    async function runSearch() {
      const query = queryInput.value.trim();
      if (query.length < 2) { queryInput.focus(); return; }
      if (!(await save())) return; // a busca fica registrada no histórico, que é uma versão do relatório
      searchButton.disabled = true;
      mount(resultsBox, loading("Procurando em todas as fontes…"));
      const found = await guarded(() => api(`/api/reports/${encodeURIComponent(reportId)}/search`, {
        method: "POST", body: { query, language: languageSelect.value, yearFrom: Number(yearInput.value) || null },
      }));
      searchButton.disabled = false;
      if (!found) { mount(resultsBox); return; }
      lastQuery = query;
      mount(resultsBox,
        found.results.length
          ? [h("p", { class: "hint" }, `${found.results.length} artigos que ainda não estão no relatório (desde ${found.yearFrom}).`),
            found.results.map((work) => h("div", { class: "card stack report-study" },
              h("h3", {}, h("a", { href: articleHref(work) }, work.title)),
              h("p", { class: "meta" }, [metaLine(work), (work.studyTypes || [])[0]].filter(Boolean).join(" · ")),
              h("div", { class: "row" }, h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: () => addRefs([work.ref], "busca", query) }, "Adicionar ao relatório")))),
            h("div", { class: "row" },
              h("button", { type: "button", class: "btn btn-primary btn-sm", onclick: () => addRefs(found.results.map((w) => w.ref), "busca", query) }, "Adicionar todos"),
              h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: follow }, "Acompanhar nos meus alertas"))]
          : [h("p", { class: "muted" }, "Nenhum artigo novo para esta busca."), h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: follow }, "Acompanhar nos meus alertas")]);
    }
    searchButton.addEventListener("click", runSearch);
    queryInput.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); runSearch(); } });

    function paintVersions(history) {
      mount(versionsBox, history.versions.length
        ? h("ul", { class: "plain-list" }, history.versions.map((v) => {
          const row = h("li", { class: "version-row" },
            h("div", {}, h("strong", {}, `Versão ${v.version}`), v.current ? h("span", { class: "badge" }, " atual") : null,
              h("span", { class: "muted" }, ` · ${fmtDate(v.savedAt.slice(0, 10))}`)),
            h("small", { class: "muted" }, v.summary));
          if (!v.current) {
            const ask = h("div", { class: "row" });
            const start = () => mount(ask,
              h("span", { class: "note" }, "Alterações não salvas serão perdidas."),
              h("button", { type: "button", class: "btn btn-sm btn-primary", onclick: async () => {
                if (await guarded(() => api(`/api/reports/${encodeURIComponent(reportId)}/restore`, { method: "POST", body: { version: v.version } }))) { toast(`Versão ${v.version} restaurada.`); rerender(); }
              } }, "Confirmar"),
              h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: () => mount(ask, h("button", { type: "button", class: "btn btn-sm btn-secondary", onclick: start }, "Restaurar")) }, "Cancelar"));
            mount(ask, h("button", { type: "button", class: "btn btn-sm btn-secondary", onclick: start }, "Restaurar"));
            row.append(ask);
          }
          return row;
        }))
        : h("p", { class: "muted" }, "Sem versões registradas ainda. Salve o relatório para criar a primeira."));
    }

    async function load() {
      const history = await guarded(() => api(`/api/reports/${encodeURIComponent(reportId)}/history`));
      if (!history) { mount(box, h("p", { class: "muted" }, "Não foi possível carregar o histórico agora.")); return; }
      mount(newBox,
        !history.listAvailable
          ? h("p", { class: "muted" }, `A lista de origem (“${history.listName}”) não existe mais, então não há como comparar.`)
          : history.newInList.length
            ? [h("p", {}, `${history.newInList.length} ${history.newInList.length === 1 ? "artigo entrou" : "artigos entraram"} na lista “${history.listName}” depois deste relatório:`),
              history.newInList.map((work) => h("div", { class: "row" },
                h("a", { href: articleHref(work) }, work.title),
                h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: () => addRefs([work.ref], "lista") }, "Adicionar"))),
              h("div", { class: "row" }, h("button", { type: "button", class: "btn btn-primary btn-sm", onclick: () => addRefs(history.newInList.map((w) => w.ref), "lista") }, "Adicionar todos"))]
            : h("p", { class: "muted" }, `Nenhum artigo novo na lista “${history.listName}”.`));
      paintVersions(history);
      mount(logBox, history.log.length
        ? h("ul", { class: "plain-list" }, history.log.map((e) => h("li", {}, h("small", { class: "muted" }, fmtDate(e.createdAt.slice(0, 10))), e.text)))
        : h("p", { class: "muted" }, "Nenhuma busca ou adição feita a partir deste relatório."));
      mount(box,
        h("h3", {}, "Novos na lista de origem"), newBox,
        h("h3", {}, "Procurar artigos novos sobre o tema"),
        h("p", { class: "hint" }, "A busca usa todas as fontes, dos mais recentes aos mais antigos, e mostra só o que ainda não está no relatório. Ela fica registrada no histórico e no apêndice de método."),
        h("div", { class: "new-list" }, queryInput,
          h("div", { class: "row" }, languageSelect, h("label", { class: "report-include" }, h("span", {}, "Desde"), yearInput), searchButton)),
        resultsBox,
        h("details", { class: "more-records" }, h("summary", {}, "Versões do relatório"), versionsBox),
        h("details", { class: "more-records" }, h("summary", {}, "Histórico de buscas e adições"), logBox));
    }
    load();
    return { node: box };
  }

  async function renderReport(reportId) {
    setTitle("Relatório");
    if (!session.user) {
      mount($app, h("h1", {}, "Relatório"), h("div", { class: "empty card" },
        h("p", {}, "Entre na sua conta para ver seus relatórios."),
        h("button", { type: "button", class: "btn btn-primary", onclick: () => openAuth("Entre para acessar seus relatórios.") }, "Entrar")));
      return;
    }
    mount($app, h("h1", {}, "Relatório"), loading());
    const data = await guarded(() => api(`/api/reports/${encodeURIComponent(reportId)}`));
    if (!data) { mount($app, h("h1", {}, "Relatório"), errorBox("Não foi possível abrir este relatório."), h("a", { href: "#/biblioteca" }, "Voltar à biblioteca")); return; }
    setTitle(data.title);

    const titleInput = h("input", { type: "text", id: "report-title", maxlength: "200", value: data.title });
    const questionInput = h("textarea", { id: "report-question", rows: "3", maxlength: "2000", placeholder: "Ex.: O exercício físico reduz a pressão arterial em adultos hipertensos?" });
    questionInput.value = data.question;
    const methodInput = h("textarea", { id: "report-method-note", rows: "4", maxlength: "3000", placeholder: "Ex.: Busquei em março de 2026 por “hipertensão e exercício”, só em português e inglês." });
    methodInput.value = data.methodNote;
    const rows = data.items.map((item) => {
      const include = h("input", { type: "checkbox", id: `inc-${item.ref}`, checked: item.included ? "" : null });
      include.checked = item.included;
      const note = h("textarea", { rows: "2", maxlength: "1000", "aria-label": `Sua nota sobre ${item.work.title}`, placeholder: "Sua nota sobre este estudo (opcional)" });
      note.value = item.note;
      const rel = item.reliability;
      const score = rel.score === null ? `confiabilidade ${rel.band.toLowerCase()}` : `confiabilidade ${rel.score}/100 (${rel.band.toLowerCase()})`;
      const card = h("article", { class: "card stack report-study" },
        h("label", { class: "report-include", for: `inc-${item.ref}` }, include, h("span", {}, "Incluir no relatório")),
        h("h3", {}, h("a", { href: articleHref(item.work) }, item.work.title)),
        h("p", { class: "meta" }, [metaLine(item.work), (item.work.studyTypes || [])[0], score].filter(Boolean).join(" · ")),
        item.findings.length ? h("ul", { class: "plain-list" }, item.findings.map((f) => h("li", {}, h("small", { class: "muted" }, f.tags.join(" · ")), f.sentence))) : null,
        note);
      return { item, include, note, card };
    });
    const brasil = showHealth() || (data.substances || []).length ? reportBrasil(reportId, data.substances || []) : null;
    const panoramaBox = h("div", { class: "stack" });
    const paintPanorama = (summary) => {
      const lines = [["Tipo de estudo", summary.types], ["Ano", summary.years], ["Idioma", summary.languages], ["Fonte", summary.sources]]
        .filter(([, pairs]) => pairs.length).map(([label, pairs]) => h("li", {}, h("strong", {}, `${label}: `), pairs.map(([n, c]) => `${n} (${c})`).join("; ")));
      mount(panoramaBox, h("p", {}, `${summary.total} estudos incluídos; ${summary.openAccess} com acesso aberto; ${summary.retracted} retratados; ${summary.withoutAbstract} sem resumo no registro.`),
        h("ul", { class: "plain-list" }, lines));
    };
    paintPanorama(data.panorama);
    const status = h("span", { class: "note", "aria-live": "polite" }, `Versão ${data.version}`);
    const saveButton = h("button", { type: "button", class: "btn btn-primary" }, "Salvar alterações");

    async function save() {
      saveButton.disabled = true;
      const body = {
        title: titleInput.value, question: questionInput.value, methodNote: methodInput.value,
        items: rows.map((r) => ({ ref: r.item.ref, included: r.include.checked, note: r.note.value })),
        substances: brasil ? brasil.selected() : undefined,
      };
      const saved = await guarded(() => api(`/api/reports/${encodeURIComponent(reportId)}`, { method: "PUT", body }));
      saveButton.disabled = false;
      if (!saved) return null;
      status.textContent = `Salvo · versão ${saved.version}`;
      titleInput.value = saved.title;
      paintPanorama(saved.panorama);
      setTitle(saved.title);
      if (brasil) brasil.reload();
      return saved;
    }
    saveButton.addEventListener("click", async () => { if (await save()) toast("Relatório salvo."); });
    const updates = reportUpdates({ reportId, data, save, rerender: () => renderReport(reportId) });
    const download = (format) => async () => {
      if (!(await save())) return; // o arquivo reflete o que está na tela
      location.assign(`/api/reports/${encodeURIComponent(reportId)}/download?format=${format}`);
    };

    mount($app,
      h("p", {}, h("a", { href: "#/biblioteca" }, "← Biblioteca")),
      h("h1", {}, "Relatório de tema"),
      h("p", { class: "lead" }, `Gerado da lista “${data.listName}”. Os estudos foram congelados na criação; escolha quais entram e escreva suas notas. Nada aqui é gerado por IA.`),
      h("section", { class: "card stack" },
        h("div", { class: "field" }, h("label", { for: "report-title" }, "Título"), titleInput),
        h("div", { class: "field" }, h("label", { for: "report-question" }, "Pergunta ou tema"), questionInput)),
      h("h2", {}, "Estudos"),
      h("p", { class: "hint" }, "Desmarque o que não deve entrar. A nota de confiabilidade e as frases estatísticas vêm do resumo do registro."),
      rows.map((r) => r.card),
      h("h2", {}, "Atualizar o relatório"), updates.node,
      h("h2", {}, "Panorama"), panoramaBox,
      brasil ? [h("h2", {}, "Situação no Brasil (medicamentos)"), brasil.node] : null,
      h("h2", {}, "Método"),
      h("p", { class: "hint" }, "O texto abaixo é montado automaticamente e entra no apêndice do documento."),
      h("ul", { class: "plain-list" }, data.method.map((p) => h("li", {}, p))),
      h("details", { class: "more-records" }, h("summary", {}, "Como a nota de confiabilidade é calculada"),
        h("ul", { class: "plain-list" }, data.criteria.map((c) => h("li", {}, h("strong", {}, `${c.name} (peso ${c.weight}): `), c.how)))),
      h("div", { class: "field" }, h("label", { for: "report-method-note" }, "Sua nota sobre o método (opcional)"), methodInput),
      h("div", { class: "report-foot" }, status,
        h("div", { class: "row" }, saveButton,
          REPORT_DOWNLOADS.map(([label, format]) => h("button", { type: "button", class: "btn btn-secondary", onclick: download(format) }, label)))),
      h("p", { class: "note" }, "Para PDF: baixe a página web (.html), abra no navegador e use Imprimir, Salvar como PDF. O relatório não conclui nem recomenda conduta; cabe ao autor interpretar os estudos."));
  }

  // ------------------------------------------------------------------ Lista compartilhada
  async function renderSharedList(token) {
    setTitle("Lista compartilhada");
    mount($app, loading("Abrindo a lista…"));
    let data;
    try { data = await api(`/api/shared/${encodeURIComponent(token)}`); } catch (error) {
      mount($app, h("h1", {}, "Lista compartilhada"), errorBox(error.message), h("p", {}, h("a", { class: "btn btn-primary", href: "#/busca" }, "Buscar artigos")));
      return;
    }
    mount($app,
      h("h1", {}, data.name),
      h("p", { class: "note" }, "Lista compartilhada por link (somente leitura)."),
      data.works.length
        ? h("ul", { class: "results" }, data.works.map((w) => h("li", { class: "result" },
          h("h3", {}, h("a", { href: articleHref(w) }, w.title)), h("div", { class: "meta" }, metaLine(w)), badges(w))))
        : h("div", { class: "empty card" }, "Esta lista está vazia."),
      h("div", { class: "row" }, h("button", { type: "button", class: "btn btn-primary", disabled: !data.works.length, onclick: async (event) => {
        if (!requireUser("Entre para salvar estes artigos na sua biblioteca.")) return;
        event.target.disabled = true;
        let saved = 0;
        for (const work of data.works) {
          const ok = await guarded(() => api("/api/library", { method: "POST", body: { ref: work.ref } }));
          if (ok) saved += 1; else break;
        }
        event.target.disabled = false;
        toast(`${saved} de ${data.works.length} artigos salvos na sua biblioteca`);
      } }, "Salvar todos na minha biblioteca")));
  }

  // ------------------------------------------------------------------ roteador
  // ------------------------------------------------------------------ interesses
  async function renderInterests(target = $app) {
    if (!session.user) {
      mount(target, h("h2", {}, "Interesses e alertas"), h("div", { class: "empty card" },
        h("p", {}, "Entre na sua conta para escolher o que acompanhar e receber avisos de artigos novos."),
        h("button", { type: "button", class: "btn btn-primary", onclick: () => openAuth("Entre para escolher seus interesses.") }, "Entrar")));
      return;
    }
    mount(target, h("h2", {}, "Interesses e alertas"), loading());
    let catalog; let saved;
    try { [catalog, saved] = await Promise.all([api("/api/interests/options"), api("/api/interests")]); } catch (error) {
      if (error.status === 401) { setUser(""); renderInterests(target); return; }
      mount(target, h("h2", {}, "Interesses e alertas"), errorBox(error.message));
      return;
    }
    // area -> Set de subtemas (conjunto vazio = a area inteira)
    const chosen = new Map(saved.topics.map((t) => [t.area, new Set(t.subtopics)]));
    const languages = new Set(saved.languages);
    let terms = [...saved.terms];
    const limits = catalog.limits;
    const total = () => [...chosen.values()].reduce((sum, subs) => sum + (subs.size || 1), 0);
    const summary = h("p", { class: "hint", "aria-live": "polite" });
    const areaBox = h("div", { class: "stack" });
    const termBox = h("div", { class: "chips" });
    const langBox = h("div", { class: "pick-row", role: "group", "aria-label": "Idiomas dos artigos" });
    const input = h("input", { type: "text", maxlength: String(limits.termChars), placeholder: "ex.: metformina em idosos", "aria-label": "Adicionar palavra-chave" });
    const saveButton = h("button", { type: "button", class: "btn btn-primary" }, "Salvar interesses");

    const pick = (label, pressed, onclick) => h("button", { type: "button", class: "pick", "aria-pressed": pressed ? "true" : "false", onclick }, label);
    const withinLimit = (extra) => {
      if (total() + extra > limits.topics) { toast(`Escolha no máximo ${limits.topics} temas.`); return false; }
      return true;
    };
    function paint() {
      const langText = languages.size ? `${languages.size} ${languages.size === 1 ? "idioma" : "idiomas"}` : "todos os idiomas";
      summary.textContent = `${total()} de ${limits.topics} temas escolhidos · ${langText} · ${terms.length} ${terms.length === 1 ? "palavra-chave" : "palavras-chave"}`;
      mount(langBox, catalog.languages.map((lang) => pick(lang.label, languages.has(lang.code), () => {
        if (languages.has(lang.code)) languages.delete(lang.code);
        else if (languages.size >= limits.languages) { toast(`Escolha no máximo ${limits.languages} idiomas.`); return; } else languages.add(lang.code);
        paint();
      })));
      mount(areaBox, catalog.areas.map((area) => {
        const subs = chosen.get(area.key);
        const count = subs ? subs.size || 1 : 0;
        const countText = subs && subs.size ? `${subs.size} ${subs.size === 1 ? "subtema" : "subtemas"}` : "toda a área";
        return h("details", { class: "area-card", open: Boolean(subs) || null, "data-area": area.key },
          h("summary", {}, h("span", {}, area.label), count ? h("span", { class: "area-count" }, countText) : null),
          h("div", { class: "pick-row" },
            pick("Toda a área", Boolean(subs) && subs.size === 0, () => {
              if (subs && subs.size === 0) chosen.delete(area.key);
              else { if (!withinLimit(1 - (subs ? subs.size || 1 : 0))) return; chosen.set(area.key, new Set()); }
              paint();
            }),
            area.subtopics.map((sub) => pick(sub.label, Boolean(subs) && subs.has(sub.key), () => {
              const current = chosen.get(area.key);
              if (current && current.has(sub.key)) { current.delete(sub.key); if (!current.size) chosen.delete(area.key); } else {
                // marcar um subtema troca "toda a área" (que valia 1) por subtemas (1 cada)
                if (!withinLimit(current && current.size === 0 ? 0 : 1)) return;
                if (current) current.add(sub.key); else chosen.set(area.key, new Set([sub.key]));
              }
              paint();
            }))));
      }));
      mount(termBox, terms.map((t) => h("span", { class: "chip" }, t, h("button", { type: "button", "aria-label": `Remover ${t}`, onclick: () => { terms = terms.filter((x) => x !== t); paint(); } }, "×"))));
    }
    function addTerm() {
      const text = input.value.replace(/\s+/g, " ").trim();
      if (!text) return;
      if (terms.length >= limits.terms) { toast(`Use no máximo ${limits.terms} palavras-chave.`); return; }
      if (!terms.some((t) => t.toLowerCase() === text.toLowerCase())) terms.push(text);
      input.value = "";
      paint();
    }
    input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); addTerm(); } });
    saveButton.addEventListener("click", async () => {
      saveButton.disabled = true;
      const body = { topics: [...chosen].map(([area, subs]) => ({ area, subtopics: [...subs] })), languages: [...languages], terms };
      const result = await guarded(() => api("/api/interests", { method: "PUT", body }));
      saveButton.disabled = false;
      if (!result) return;
      toast(result.topics.length || result.terms.length ? "Interesses salvos. Vamos avisar quando sair artigo novo." : "Interesses removidos. Você não receberá avisos.");
      syncBell();
    });
    paint();

    mount(target,
      h("h2", {}, "Interesses e alertas"),
      h("p", { class: "lede" }, "Escolha as áreas, os subtemas e os idiomas que você quer acompanhar. Quando aparecer um artigo novo sobre eles, o sininho no canto superior avisa."),
      h("section", { class: "card stack" }, h("h2", {}, "Idiomas"),
        h("p", { class: "hint" }, "Sem escolher nenhum, aceitamos todos os idiomas. Para artigos em português, buscamos também pelo nome em português."), langBox),
      h("section", { class: "stack" }, h("h2", {}, "Áreas e subtemas"),
        h("p", { class: "hint" }, "Abra uma área e marque os subtemas, ou marque “Toda a área”."), areaBox),
      h("section", { class: "card stack" }, h("h2", {}, "Palavras-chave"),
        h("p", { class: "hint" }, "Para acompanhar algo mais específico, como um medicamento ou uma doença."),
        h("div", { class: "new-list" }, input, h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: addTerm }, "Adicionar")), termBox),
      h("div", { class: "interests-foot" }, summary, h("div", { class: "row" }, saveButton)),
      h("p", { class: "note" }, "Como funciona: ao salvar, guardamos os artigos recentes que já existem e avisamos só dos que surgirem depois. Procuramos quando você abre o site, no máximo a cada 6 horas. Ainda não enviamos e-mail."));
  }

  function render() {
    const { view, rest, params } = Lib.parseRoute(location.hash);
    clearCitationMeta();
    closePanel();
    renderNav(view);
    if (view === "busca") renderSearch(params);
    else if (view === "artigo") renderArticle(params);
    else if (view === "biblioteca") renderLibrary(params);
    else if (view === "feed") renderFeed(params);
    else if (view === "interesses") location.replace("#/perfil/interesses");
    else if (view === "perfil") renderProfile(rest[0] || "");
    else if (view === "relatorio" && rest[0]) renderReport(rest[0]);
    else if (view === "lista" && rest[0]) renderSharedList(rest[0]);
    else renderHome();
    if (view !== "busca") window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", () => { render(); $app.focus({ preventScroll: true }); });
  render();
  askProfile();
})();
