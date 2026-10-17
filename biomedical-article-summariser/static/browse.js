/* Navegador de artigos — telas e interação.
   Tudo é montado com DOM (textContent), nunca com innerHTML de dados externos; links só http(s). */
(() => {
  "use strict";

  const Lib = window.BrowseLib;
  const $app = document.getElementById("app");
  const THEME_KEY = "bdd.theme"; // compartilhado com a página de IA
  const PAGE_SIZE = 10;
  const SHORTCUTS = [
    { title: "Sou estudante", hint: "Preciso achar artigos para o TCC e citar certo.", q: "diabetes tipo 2" },
    { title: "Sou professor", hint: "Quero montar uma lista de leitura para a minha turma.", q: "saúde pública" },
    { title: "Sou pesquisador", hint: "Quero comparar estudos e ver o tipo de evidência.", q: "ensaio clínico hipertensão" },
    { title: "Sou profissional", hint: "Preciso achar rápido a evidência sobre uma pergunta.", q: "sepse" },
  ];

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
      h("span", { class: "badge" }, `${Lib.formatCount(work.citedBy)} citações`),
      work.language ? h("span", { class: "badge" }, work.language.toUpperCase()) : null,
      work.source ? h("span", { class: "badge" }, work.source) : null);
  }
  const metaLine = (work) => [work.authors, work.journal, work.year].filter(Boolean).join(" · ");
  const articleHref = (work) => Lib.buildHash("/artigo", { ref: work.ref });

  function saveButton(work, { small = true, onChange } = {}) {
    const button = h("button", { type: "button", class: `btn ${small ? "btn-sm " : ""}btn-secondary` });
    const refresh = () => { button.setAttribute("aria-pressed", String(Boolean(work.saved))); button.replaceChildren(icon("bookmark", work.saved), work.saved ? "Salvo" : "Salvar"); };
    button.addEventListener("click", async () => {
      if (!requireUser("Entre para salvar artigos na sua biblioteca.")) return;
      button.disabled = true;
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
    });
    refresh();
    return button;
  }

  // ------------------------------------------------------------------ Início
  const TOPICS = ["diabetes tipo 2", "sepse", "hipertensão", "câncer de mama", "saúde mental", "COVID-19", "inteligência artificial na saúde", "mudanças climáticas"];
  const STEPS = [
    ["1", "Busque", "Digite um tema, título ou palavra-chave. Filtre por ano, tipo de estudo, idioma e acesso aberto, em uma ou em todas as fontes."],
    ["2", "Entenda", "Veja o resumo organizado por seções, os números com a frase de origem, o tipo de estudo e a nota de confiabilidade explicada."],
    ["3", "Organize", "Salve, etiquete, monte listas de leitura, compartilhe por link e exporte as referências em BibTeX, RIS, ABNT, APA ou Vancouver."],
  ];
  const FEATURES = [
    ["", "Várias fontes em uma busca", "Europe PMC (ciências da vida e saúde) e OpenAlex (todas as áreas), com resultados sem repetição."],
    ["", "Nota de confiabilidade que se explica", "Retratação, tipo de estudo, revisão por pares, amostra e estatística. Toque na nota e veja cada critério e a evidência."],
    ["", "Leitura fiel, sem inventar", "Trechos copiados do próprio resumo. Nada é gerado nem interpretado, então não há lacunas preenchidas por palavras de um modelo."],
    ["", "Versão aberta", "Mostramos quando existe uma cópia gratuita e legal do artigo e levamos você até ela."],
    ["", "Biblioteca e listas", "Etiquetas, listas de leitura e link público somente leitura, que você pode revogar quando quiser."],
    ["", "IA opcional, com cautela", "Resumos e análises no Laboratório de IA, com trava contra instruções maliciosas, checagem de números e avisos claros."],
  ];

  function renderHome() {
    setTitle("Início");
    const input = h("input", { type: "search", id: "home-q", placeholder: "Busque por tema, título ou palavra-chave", "aria-label": "Buscar artigos", maxlength: "300" });
    const go = (q) => { location.hash = Lib.buildHash("/busca", { q }); };
    mount($app,
      h("section", { class: "hero home-hero" },
        h("span", { class: "eyebrow" }, "Navegador de artigos científicos"),
        h("h1", {}, "Encontre, entenda e organize artigos científicos"),
        h("p", { class: "lead" }, "O Biomedical Data Digger reúne milhões de artigos em um só lugar, mostra o essencial do jeito que o autor escreveu e diz, com critérios abertos, o quanto cada artigo merece confiança. Feito para estudantes, professores, pesquisadores e profissionais de saúde."),
        h("form", { class: "searchbar", onsubmit: (e) => { e.preventDefault(); go(input.value.trim()); } },
          input, h("button", { type: "submit", class: "btn btn-primary" }, "Buscar")),
        h("div", { class: "chips topics", role: "group", "aria-label": "Sugestões de busca" },
          h("span", { class: "muted topics-label" }, "Experimente:"),
          TOPICS.map((t) => h("a", { class: "chip", href: Lib.buildHash("/busca", { q: t }) }, t)))),

      h("h2", {}, "Como funciona"),
      h("ol", { class: "steps" }, STEPS.map(([n, title, text]) => h("li", { class: "card step" },
        h("span", { class: "step-number", "aria-hidden": "true" }, n), h("h3", {}, title), h("p", { class: "muted" }, text)))),

      h("h2", {}, "Por que usar"),
      h("div", { class: "grid features" }, FEATURES.map(([icon, title, text]) => h("div", { class: "card feature" },
        h("span", { class: "feature-icon", "aria-hidden": "true" }, icon), h("h3", {}, title), h("p", { class: "muted" }, text)))),

      h("h2", {}, "Por onde você quer começar?"),
      h("div", { class: "grid" }, SHORTCUTS.map((s) => h("div", { class: "card stack" },
        h("h3", {}, s.title), h("p", { class: "muted" }, s.hint),
        h("a", { class: "btn btn-secondary", href: Lib.buildHash("/busca", { q: s.q }) }, `Começar com "${s.q}"`)))),

      h("section", { class: "card cta" },
        h("div", {}, h("h2", {}, "Sua biblioteca, no seu ritmo"),
          h("p", { class: "muted" }, "Buscar e ler não exige conta. Crie uma para salvar artigos, montar listas e exportar referências.")),
        h("div", { class: "row" },
          session.user
            ? h("a", { class: "btn btn-primary", href: "#/biblioteca" }, "Abrir minha biblioteca")
            : h("button", { type: "button", class: "btn btn-primary", onclick: () => openAuth("Crie uma conta para salvar artigos e montar listas.") }, "Criar conta ou entrar"),
          h("a", { class: "btn btn-outline", href: "/ia" }, "Conhecer o Laboratório de IA"))),

      h("p", { class: "note" }, "As informações vêm de fontes públicas (Europe PMC e OpenAlex). A nota de confiabilidade resume sinais verificáveis no registro e no resumo; não substitui a leitura crítica do texto completo nem orientação profissional."));
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
      ["Citações", Lib.formatCount(work.citedBy)],
    ];

    mount($app,
      h("article", { class: "stack" },
        h("a", { href: "#/busca", class: "muted" }, "Voltar à busca"),
        h("h1", {}, work.title),
        h("div", { class: "meta" }, metaLine(work)),
        badges(work),
        reliabilityCard(data.reliability),
        h("div", { class: "row" },
          saveButton(work, { small: false, onChange: renderOrganize }),
          oaHref ? h("a", { class: "btn btn-secondary", href: oaHref, target: "_blank", rel: "noopener noreferrer" }, [icon("external"), "Abrir versão aberta"])
            : h("span", { class: "note" }, "Sem versão aberta conhecida"),
          h("a", { class: "btn btn-outline", href: Lib.aiLabHref(work.pmid || work.ref), title: "Resumos e análises com IA, opcionais e com avisos" }, "Analisar com IA (opcional)")),
        h("div", { class: "card stack" }, h("h3", {}, "Citar"),
          h("div", { class: "row" }, Object.keys(data.citations).map((s) => h("button", { type: "button", class: "btn btn-secondary", onclick: () => showCitation(s) }, s))),
          citationBox),
        h("div", { class: "card stack" }, h("h3", {}, "Resumo organizado (texto original)"),
          !work.abstract ? h("p", { class: "muted" }, "Este registro não traz resumo.")
            : data.sections.length
              ? h("dl", { class: "sections" }, data.sections.map((s) => [h("dt", {}, s.label && s.label.toLowerCase() !== s.heading.toLowerCase() ? `${s.heading} (rótulo original: ${s.label})` : s.heading), h("dd", {}, s.text)]))
              : [h("p", { class: "note" }, "Este resumo não tem seções rotuladas; texto original completo:"), h("p", {}, work.abstract)]),
        h("div", { class: "card stack" }, h("h3", {}, "Números e dados estatísticos (com a frase de origem)"),
          data.findings.length
            ? data.findings.map((f) => h("div", { class: "finding" }, h("div", { class: "tags" }, f.tags.join(" · ")), h("div", {}, f.sentence)))
            : h("p", { class: "muted" }, "Nenhum dado estatístico foi encontrado no resumo."),
          h("p", { class: "note" }, "Frases copiadas do resumo; nada foi gerado nem interpretado. A seleção é por palavras-chave e pode omitir frases. Lido apenas o resumo, não o texto completo.")),
        h("div", { class: "card stack" }, h("h3", {}, "Metadados"),
          h("table", {}, h("tbody", {}, meta.map(([k, v]) => h("tr", {}, h("th", { scope: "row" }, k), h("td", {}, v))))),
          work.keywords.length ? h("div", { class: "kw" }, work.keywords.map((k) => h("a", { href: Lib.buildHash("/busca", { q: k }) }, k))) : null),
        h("div", { class: "card stack" }, h("h3", {}, "Organizar"), organize),
        data.similar.length ? h("div", { class: "card stack" }, h("h3", {}, "Artigos semelhantes"),
          h("ul", { class: "stack" }, data.similar.map((s) => h("li", {}, h("a", { href: articleHref(s) }, s.title), h("span", { class: "muted" }, ` · ${(s.studyTypes || [])[0] || "Artigo"} · ${s.year || "—"}`))))) : null));
    renderOrganize();
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
    const formats = [["BibTeX", "bibtex"], ["RIS", "ris"], ["ABNT", "abnt"], ["APA", "apa"], ["Vancouver", "vancouver"]];

    const listName = h("input", { type: "text", id: "list-name", placeholder: "nome da lista (ex.: Leituras da semana 3)", maxlength: "80" });
    const createList = async () => {
      if (!listName.value.trim()) return;
      if (await guarded(() => api("/api/lists", { method: "POST", body: { name: listName.value } }))) renderLibrary(params);
    };

    mount($app,
      h("h1", {}, "Biblioteca"),
      h("p", { class: "lead" }, `${data.items.length} ${data.items.length === 1 ? "artigo salvo" : "artigos salvos"}. Etiquete, exporte e monte listas para compartilhar.`),
      data.items.length ? h("div", { class: "row" }, h("span", { class: "muted" }, "Exportar tudo:"), formats.map(([l, f]) => exportLink(l, f))) : null,
      allTags.length ? h("div", { class: "chips" },
        h("a", { class: `chip${activeTag ? "" : " active"}`, href: "#/biblioteca" }, "todas"),
        allTags.map((t) => h("a", { class: `chip${t === activeTag ? " active" : ""}`, href: Lib.buildHash("/biblioteca", { tag: t }) }, t))) : null,
      !data.items.length
        ? h("div", { class: "empty card" }, h("p", {}, "Sua biblioteca está vazia."), h("a", { class: "btn btn-primary", href: "#/busca" }, "Buscar artigos"))
        : h("ul", { class: "results" }, shown.map((item) => h("li", { class: "result" },
          h("h3", {}, h("a", { href: articleHref(item) }, item.title)),
          h("div", { class: "meta" }, metaLine(item)),
          h("div", { class: "chips" }, item.tags.map((t) => h("span", { class: "chip" }, t))),
          h("div", { class: "row" },
            h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: async () => {
              if (await guarded(() => api(`/api/library?ref=${encodeURIComponent(item.ref)}`, { method: "DELETE" }))) renderLibrary(params);
            } }, "Remover"))))),
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
    return h("div", { class: "card stack" },
      h("h3", {}, `${list.name} (${list.works.length})`),
      list.works.length ? h("ul", { class: "stack" }, list.works.map((w) => h("li", { class: "row" },
        h("a", { href: articleHref(w) }, w.title),
        h("button", { type: "button", class: "btn btn-sm btn-ghost", "aria-label": `Tirar ${w.title} da lista`, onclick: async () => {
          if (await guarded(() => api(`/api/lists/${list.id}/items?ref=${encodeURIComponent(w.ref)}`, { method: "DELETE" }))) renderLibrary(params);
        } }, "Tirar")))) : h("p", { class: "muted" }, "Lista vazia."),
      h("div", { class: "row" },
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
