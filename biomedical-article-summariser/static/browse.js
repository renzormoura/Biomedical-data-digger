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
  const session = { user: accountButton.dataset.user || "" };

  function setUser(user) {
    session.user = user || "";
    document.getElementById("account-label").textContent = user || "Entrar";
    logoutButton.hidden = !user;
    dialog.querySelectorAll(".field, [data-auth='login'], [data-auth='register']").forEach((el) => { el.hidden = Boolean(user); });
  }
  setUser(session.user);

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
  function renderNav(view) {
    const items = [["#/", "Início", ""], ["#/busca", "Busca", "busca"], ["#/biblioteca", "Biblioteca", "biblioteca"]];
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
  const metaLine = (work) => [work.authors, work.journal, work.year].filter(Boolean).join(" · ");
  const articleHref = (work) => Lib.buildHash("/artigo", { ref: work.ref });

  // um unico ouvinte fecha qualquer seletor de lista ou painel de download aberto quando o clique cai fora dele
  document.addEventListener("click", (event) => {
    document.querySelectorAll(".save-picker:not([hidden])").forEach((picker) => {
      if (!picker.parentElement.contains(event.target)) { picker.hidden = true; picker.replaceChildren(); }
    });
    document.querySelectorAll(".download-panel:not([hidden])").forEach((panel) => {
      if (!panel.parentElement.contains(event.target)) { panel.hidden = true; panel.parentElement.querySelector("button")?.setAttribute("aria-expanded", "false"); }
    });
  });

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

  function saveButton(work, { small = true, onChange } = {}) {
    const button = h("button", { type: "button", class: `btn ${small ? "btn-sm " : ""}btn-secondary` });
    const picker = h("div", { class: "save-picker", role: "group", "aria-label": "Adicionar a uma lista", hidden: "" });
    const wrap = h("span", { class: "save-wrap" }, button, picker);
    const refresh = () => { button.setAttribute("aria-pressed", String(Boolean(work.saved))); button.replaceChildren(icon("bookmark", work.saved), work.saved ? "Salvo" : "Salvar"); };

    const closePicker = () => { picker.hidden = true; picker.replaceChildren(); };
    // depois de salvar na biblioteca, oferece colocar o artigo em uma lista (so se o usuario tiver listas)
    async function offerLists() {
      const data = await guarded(() => api("/api/lists"));
      if (!data || !data.lists.length) return;
      const select = h("select", { "aria-label": "Lista" }, data.lists.map((l) => h("option", { value: l.id }, `${l.name} (${l.works.length})`)));
      const add = h("button", { type: "button", class: "btn btn-sm btn-primary" }, "Adicionar");
      add.addEventListener("click", async () => {
        add.disabled = true;
        const ok = await guarded(() => api(`/api/lists/${select.value}/items`, { method: "POST", body: { ref: work.ref } }));
        if (ok) {
          toast(`Adicionado à lista "${select.options[select.selectedIndex].text.replace(/ \(\d+\)$/, "")}"`);
          closePicker();
          if (onChange) onChange();
        } else add.disabled = false;
      });
      const skip = h("button", { type: "button", class: "btn btn-sm btn-ghost" }, "Agora não");
      skip.addEventListener("click", () => { closePicker(); button.focus(); });
      mount(picker, h("p", { class: "save-picker-title" }, "Salvo na biblioteca. Adicionar também a uma lista?"),
        select, h("div", { class: "row" }, add, skip));
      picker.hidden = false;
      select.focus();
    }
    picker.addEventListener("keydown", (event) => { if (event.key === "Escape") { closePicker(); button.focus(); } });

    button.addEventListener("click", async () => {
      if (!requireUser("Entre para salvar artigos na sua biblioteca.")) return;
      button.disabled = true;
      closePicker();
      const done = await guarded(async () => {
        if (work.saved) await api(`/api/library?ref=${encodeURIComponent(work.ref)}`, { method: "DELETE" });
        else await api("/api/library", { method: "POST", body: { ref: work.ref } });
        work.saved = !work.saved;
        toast(work.saved ? "Salvo na biblioteca" : "Removido da biblioteca");
        return true;
      });
      button.disabled = false;
      refresh();
      if (done && onChange) onChange();
      if (done && work.saved) await offerLists();
    });
    refresh();
    return wrap;
  }

  // ------------------------------------------------------------------ Início
  const TOPICS = ["diabetes tipo 2", "sepse", "saúde mental", "inteligência artificial na saúde", "mudanças climáticas"];
  const STEPS = [
    ["01", "Busque", "Filtre por ano, tipo de estudo, idioma e acesso aberto. Combine fontes sem ver o mesmo artigo duas vezes."],
    ["02", "Entenda", "Resumo organizado por seções, números com a frase de origem e a nota de confiabilidade explicada critério a critério."],
    ["03", "Organize", "Salve, etiquete, monte listas de leitura, compartilhe por link e exporte as referências em BibTeX, RIS, ABNT, APA ou Vancouver."],
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
      sourceSelect.value = options.sources.some((src) => src.id === "all") ? "all" : "";
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

      h("section", { class: "stats", "aria-label": "O produto em números" },
        stat(sourceCount, "fontes integradas, com busca combinada"),
        stat(h("strong", {}, "8"), "critérios abertos de confiabilidade"),
        stat(h("strong", {}, "5"), "formatos de citação e exportação"),
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
    async function run() {
      if (controller) controller.abort();
      controller = new AbortController();
      mount(results, loading("Buscando…"));
      try {
        const data = await api(`/api/discover/search?${Lib.apiParamsFromSearchState(st, PAGE_SIZE)}`, { signal: controller.signal });
        mount(results,
          h("div", { class: "results-head" },
            h("strong", {}, `${Lib.formatCount(data.total)} ${data.total === 1 ? "resultado" : "resultados"}`),
            h("span", { class: "muted" }, activeSource().name)),
          (data.notes || []).map((note) => h("p", { class: "note" }, note)),
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
    }
    function sync() {
      history.replaceState(null, "", Lib.buildHash("/busca", Lib.paramsFromSearchState(st)));
      run();
    }
    function goPage(page) { st.page = page; sync(); window.scrollTo(0, 0); }
    const apply = () => { readControls(); st.page = 1; sync(); };
    const applyLater = Lib.debounce(apply, 350);

    const filters = h("form", { class: "card filters", "aria-label": "Filtros", onsubmit: (e) => { e.preventDefault(); applyLater.cancel(); apply(); } },
      h("div", { class: "field" }, h("label", { for: "q" }, "Buscar"), q, h("button", { type: "submit", class: "btn btn-primary" }, "Buscar")),
      source ? h("div", { class: "field" }, h("label", { for: "source" }, "Fonte"), source) : null,
      h("div", { class: "field" }, h("label", {}, "Ano de publicação"), h("div", { class: "row" }, yf, yt)),
      h("div", { class: "field" }, h("label", {}, "Tipo de estudo"), typeBox),
      h("div", { class: "field" }, h("label", { class: "check" }, oa, "Só acesso aberto")),
      h("div", { class: "field" }, h("label", { for: "lang" }, "Idioma"), lang),
      h("div", { class: "field" }, h("label", { for: "sort" }, "Ordenar por"), sort),
      h("a", { class: "btn btn-ghost", href: "#/busca" }, "Limpar filtros"));
    filters.addEventListener("change", (event) => {
      if (event.target === source) {
        // a fonte muda os tipos de estudo oferecidos: limpa a selecao e redesenha a lista de tipos
        st.source = source.value === defaultSource.id ? "" : source.value;
        st.types = [];
        renderTypes();
      }
      applyLater();
    });
    yf.addEventListener("input", applyLater);
    yt.addEventListener("input", applyLater);

    const wide = window.matchMedia("(min-width: 901px)").matches;
    mount($app, h("h1", {}, "Busca"),
      h("div", { class: "layout" },
        h("details", { class: "filters-wrap", open: wide }, h("summary", { class: "btn btn-secondary" }, "Filtros e ordenação"), filters),
        results));
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

    // citar
    const citationBox = h("div", { "aria-live": "polite" });
    const showCitation = (style) => {
      const text = data.citations[style];
      mount(citationBox, h("div", { class: "citation" }, text),
        h("div", { class: "row" }, h("button", { type: "button", class: "btn btn-sm btn-secondary", onclick: () => copyText(text, `Referência ${style} copiada`) }, "Copiar"),
          h("span", { class: "note" }, "Gerada por código a partir dos metadados do registro (sem IA).")));
    };

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
            oaHref ? h("a", { class: "btn btn-secondary", href: oaHref, target: "_blank", rel: "noopener noreferrer" }, [icon("external"), "Abrir versão aberta"])
              : h("span", { class: "note" }, "Sem versão aberta conhecida"),
            downloadMenu(work),
            h("a", { class: "btn btn-secondary", href: Lib.aiLabHref(work.pmid || work.ref), title: "Resumos e análises com IA, opcionais e com avisos" }, [icon("spark"), "Analisar com IA (opcional)"]))),
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
              h("div", { class: "row" }, Object.keys(data.citations).map((st) => h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: () => showCitation(st) }, st))),
              citationBox)),
          h("aside", { class: "article-aside", "aria-label": "Avaliação e detalhes" },
            reliabilityCard(data.reliability),
            h("section", { class: "card stack" }, h("h3", {}, "Detalhes"),
              h("table", {}, h("tbody", {}, meta.map(([k, v]) => h("tr", {}, h("th", { scope: "row" }, k), h("td", {}, v))))),
              work.keywords.length ? h("div", { class: "kw" }, work.keywords.map((k) => h("a", { href: Lib.buildHash("/busca", { q: k }) }, k))) : null),
            h("section", { class: "card stack" }, h("h3", {}, "Registro e dados"), openData),
            h("section", { class: "card stack" }, h("h3", {}, "Organizar"), organize),
            data.similar.length ? h("section", { class: "card stack" }, h("h3", {}, "Artigos semelhantes"),
              h("ul", { class: "similar" }, data.similar.map((sim) => h("li", {}, h("a", { href: articleHref(sim) }, sim.title), h("small", { class: "muted" }, `${(sim.studyTypes || [])[0] || "Artigo"} · ${sim.year || "—"}`))))) : null))));
    renderOrganize();
    renderOpenData();
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
    const activeTag = params.get("tag") || "";
    const allTags = [...new Set(data.items.flatMap((i) => i.tags))].sort();
    const shown = data.items.filter((i) => !activeTag || i.tags.includes(activeTag));
    const exportLink = (label, format, listId) => h("a", {
      class: "btn btn-secondary btn-sm", download: "", href: `/api/library/export?${new URLSearchParams({ format, ...(listId ? { list_id: listId } : {}) })}`,
    }, label);
    const formats = [["BibTeX", "bibtex"], ["RIS", "ris"], ["ABNT", "abnt"], ["APA", "apa"], ["Vancouver", "vancouver"], ["Planilha (CSV)", "csv"], ["Dados (JSON)", "json"], ["Resumos (MD)", "resumos"]];

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
        h("div", { class: "row export-row" }, h("span", { class: "muted" }, "Exportar tudo"), formats.map(([l, f]) => exportLink(l, f)))) : null,
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
      data.lists.length ? data.lists.map((list) => renderListCard(list, params, exportLink, formats))
        : h("p", { class: "muted" }, "Nenhuma lista ainda. Crie uma e adicione artigos pela página de cada artigo."));
  }

  function renderListCard(list, params, exportLink, formats) {
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
    return h("section", { class: "list-block stack" },
      h("h3", {}, list.name, h("span", { class: "muted count" }, ` ${list.works.length} ${list.works.length === 1 ? "artigo" : "artigos"}`)),
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
        list.works.length ? formats.map(([l, f]) => exportLink(l, f, list.id)) : null,
        h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: async () => {
          if (await guarded(() => api(`/api/lists/${list.id}`, { method: "DELETE" }))) renderLibrary(params);
        } }, "Excluir lista")),
      linkBox);
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
  function render() {
    const { view, rest, params } = Lib.parseRoute(location.hash);
    renderNav(view);
    if (view === "busca") renderSearch(params);
    else if (view === "artigo") renderArticle(params);
    else if (view === "biblioteca") renderLibrary(params);
    else if (view === "lista" && rest[0]) renderSharedList(rest[0]);
    else renderHome();
    if (view !== "busca") window.scrollTo(0, 0);
  }
  window.addEventListener("hashchange", () => { render(); $app.focus({ preventScroll: true }); });
  render();
})();
