/* Maquete do navegador de artigos: telas e interação. Dados fictícios, sem rede, sem IA.
   Tudo é montado com DOM (nunca innerHTML) e a biblioteca do usuário fica só no navegador (localStorage). */
(() => {
  "use strict";

  const DATA = window.NAV_DATA;
  const PERSONAS = window.NAV_PERSONAS;
  const Nav = window.Nav;
  const BY_ID = Object.fromEntries(DATA.map((a) => [a.id, a]));
  const PAGE_SIZE = 6;
  const LANG_NAMES = { pt: "Português", en: "Inglês", es: "Espanhol" };
  const TASKS = [
    { id: "t1", persona: "Estudante", text: "Ache 3 artigos sobre diabetes publicados a partir de 2020 e gere a referência ABNT de cada um." },
    { id: "t2", persona: "Professor", text: "Crie uma lista de leitura com 3 artigos de saúde pública e copie o link para compartilhar." },
    { id: "t3", persona: "Pesquisador", text: "Encontre as revisões sistemáticas e meta-análises e diga qual traz o maior número de participantes." },
    { id: "t4", persona: "Profissional", text: "Descubra se há estudo sobre hipoglicemia por interação medicamentosa e leia o essencial." },
    { id: "t5", persona: "Todos", text: "Salve 3 artigos e exporte a biblioteca em BibTeX." },
  ];

  // ------------------------------------------------------------------ utilidades de DOM
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

  /** Troca o conteúdo de `parent`; aceita listas, null e false (que `replaceChildren` imprimiria como texto). */
  function mount(parent, ...kids) {
    parent.replaceChildren(...kids.flat(Infinity)
      .filter((kid) => kid !== null && kid !== undefined && kid !== false)
      .map((kid) => (kid.nodeType ? kid : document.createTextNode(String(kid)))));
  }

  const $app = document.getElementById("app");
  let toastTimer;
  function toast(message) {
    const el = document.getElementById("toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 2200);
  }

  async function copyText(text, okMessage = "Copiado!") {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const area = h("textarea", { "aria-hidden": "true" });
      area.value = text;
      document.body.append(area);
      area.select();
      try { document.execCommand("copy"); } catch { /* sem suporte */ }
      area.remove();
    }
    toast(okMessage);
  }

  function download(filename, text, mime = "text/plain") {
    const url = URL.createObjectURL(new Blob([text], { type: `${mime};charset=utf-8` }));
    const link = h("a", { href: url, download: filename });
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  // ------------------------------------------------------------------ armazenamento local
  const KEYS = { library: "nav.library", events: "nav.events", test: "nav.test", theme: "nav.theme" };
  const read = (key, fallback) => {
    try { const raw = localStorage.getItem(key); return raw ? JSON.parse(raw) : fallback; } catch { return fallback; }
  };
  const write = (key, value) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* modo privado */ } };

  function loadLibrary() {
    const raw = read(KEYS.library, {});
    const items = {};
    for (const [id, item] of Object.entries(raw.items && typeof raw.items === "object" ? raw.items : {})) {
      if (BY_ID[id]) items[id] = { tags: Array.isArray(item.tags) ? item.tags.map(String).slice(0, 12) : [], savedAt: item.savedAt || 0 };
    }
    const lists = (Array.isArray(raw.lists) ? raw.lists : [])
      .filter((l) => l && typeof l.name === "string")
      .map((l) => ({ id: String(l.id), name: l.name.slice(0, Nav.MAX_LIST_NAME), ids: (l.ids || []).filter((id) => BY_ID[id]) }));
    return { items, lists };
  }
  let library = loadLibrary();
  const persist = () => write(KEYS.library, library);
  const isSaved = (id) => Boolean(library.items[id]);

  let events = read(KEYS.events, []);
  function log(type, detail = "") {
    events.push({ t: Date.now(), type, detail: String(detail).slice(0, 120) });
    events = events.slice(-500);
    write(KEYS.events, events);
  }

  function toggleSave(id) {
    if (isSaved(id)) { delete library.items[id]; log("unsave", id); toast("Removido da biblioteca"); }
    else { library.items[id] = { tags: [], savedAt: Date.now() }; log("save", id); toast("Salvo na biblioteca"); }
    persist();
    renderNav();
  }

  // ------------------------------------------------------------------ tema e navegação
  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    document.getElementById("theme-toggle").textContent = theme === "dark" ? "☀️ Claro" : "🌙 Escuro";
  }
  applyTheme(read(KEYS.theme, "dark"));
  document.getElementById("theme-toggle").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    write(KEYS.theme, next);
  });

  function renderNav() {
    const current = location.hash.slice(1).split("?")[0].split("/")[1] || "";
    const items = [["#/", "Início", ""], ["#/busca", "Busca", "busca"], ["#/biblioteca", `Biblioteca (${Object.keys(library.items).length})`, "biblioteca"], ["#/teste", "Modo teste", "teste"]];
    const nav = document.getElementById("mainnav");
    nav.replaceChildren(...items.map(([href, label, key]) => h("a", { href, "aria-current": key === current || (key === "busca" && current === "artigo") ? "page" : null }, label)));
  }

  const hashFor = (path, params = {}) => {
    const query = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== "" && v !== null && v !== undefined && v !== false)).toString();
    return `#${path}${query ? `?${query}` : ""}`;
  };
  const go = (path, params) => { location.hash = hashFor(path, params); };

  // ------------------------------------------------------------------ componentes
  function highlighted(text, terms) {
    return Nav.splitHighlight(text, terms).map((p) => (p.hit ? h("mark", {}, p.text) : p.text));
  }

  function badges(article) {
    return h("div", { class: "badges" },
      h("span", { class: "badge type" }, article.type),
      article.oa ? h("span", { class: "badge oa" }, "Acesso aberto") : h("span", { class: "badge" }, "Acesso restrito"),
      h("span", { class: "badge" }, `${article.citations} citações`),
      h("span", { class: "badge" }, LANG_NAMES[article.lang]),
      h("span", { class: "badge" }, article.area),
    );
  }

  const authorLine = (a) => a.authors.map((x) => `${x.given} ${x.family}`).join(", ");

  function saveButton(id, small = true) {
    const button = h("button", { type: "button", class: `btn ${small ? "btn-sm " : ""}btn-secondary`, "aria-pressed": String(isSaved(id)) });
    const refresh = () => { button.setAttribute("aria-pressed", String(isSaved(id))); button.textContent = isSaved(id) ? "★ Salvo" : "☆ Salvar"; };
    button.addEventListener("click", () => { toggleSave(id); refresh(); });
    refresh();
    return button;
  }

  function resultCard(article, terms) {
    const snippet = article.abstract.length > 260 ? `${article.abstract.slice(0, 260)}…` : article.abstract;
    return h("li", { class: "result" },
      h("h3", {}, h("a", { href: hashFor(`/artigo/${article.id}`), onclick: () => log("open_article", article.id) }, highlighted(article.title, terms))),
      h("div", { class: "meta" }, `${authorLine(article)} · ${article.journal} · ${article.year}`),
      badges(article),
      h("p", { class: "snippet" }, highlighted(snippet, terms)),
      h("div", { class: "row" }, saveButton(article.id), h("a", { class: "btn btn-sm btn-ghost", href: hashFor(`/artigo/${article.id}`), onclick: () => log("open_article", article.id) }, "Abrir")),
    );
  }

  function pageTitle(text) { document.title = `${text} — Navegador de artigos (maquete)`; }

  // ------------------------------------------------------------------ Início
  function renderHome() {
    pageTitle("Início");
    const input = h("input", { type: "search", id: "home-q", placeholder: "Busque por tema, título ou palavra-chave", "aria-label": "Buscar artigos" });
    const form = h("form", { class: "searchbar", onsubmit: (e) => { e.preventDefault(); go("/busca", { q: input.value.trim() }); } },
      input, h("button", { type: "submit", class: "btn btn-primary" }, "Buscar"));
    mount($app, 
      h("section", { class: "hero" },
        h("h1", {}, "Encontre, entenda e organize artigos científicos"),
        h("p", { class: "lead" }, "Um lugar para achar artigos, ver o essencial copiado do próprio texto (sem IA) e montar a sua biblioteca. A IA, quando existir, será um botão opcional."),
        form),
      h("h2", {}, "Por onde você quer começar?"),
      h("div", { class: "grid" }, PERSONAS.map((p) => h("div", { class: "card stack" },
        h("h3", {}, p.title), h("p", { class: "muted" }, p.hint),
        h("button", { type: "button", class: "btn btn-secondary", onclick: () => go("/busca", { q: p.q }) }, `Começar com "${p.q}"`)))),
      h("h2", {}, "O que esta maquete mostra"),
      h("div", { class: "grid" },
        h("div", { class: "card" }, h("h3", {}, "1. Buscar e filtrar"), h("p", { class: "muted" }, "Ano, tipo de estudo, acesso aberto, área e idioma, com ordenação.")),
        h("div", { class: "card" }, h("h3", {}, "2. Ler o essencial"), h("p", { class: "muted" }, "Resumo organizado, números com a frase de origem e citação ABNT, APA e Vancouver.")),
        h("div", { class: "card" }, h("h3", {}, "3. Organizar"), h("p", { class: "muted" }, "Biblioteca com etiquetas, listas compartilháveis por link e exportação BibTeX e RIS."))),
      h("p", { class: "note" }, `${DATA.length} artigos de exemplo, todos fictícios. Seus dados ficam só neste navegador.`),
    );
  }

  // ------------------------------------------------------------------ Busca
  const toInt = (v) => { const n = Number.parseInt(v, 10); return Number.isFinite(n) ? n : null; };

  function renderSearch(params) {
    pageTitle("Busca");
    const state = {
      q: params.get("q") || "", yearFrom: toInt(params.get("yf")), yearTo: toInt(params.get("yt")),
      types: (params.get("types") || "").split(",").filter(Boolean), oaOnly: params.get("oa") === "1",
      area: params.get("area") || "Todas", lang: params.get("lang") || "todos", sort: params.get("sort") || "relevancia",
      page: Math.max(1, toInt(params.get("p")) || 1),
    };
    const areas = [...new Set(DATA.map((a) => a.area))].sort();
    const types = [...new Set(DATA.map((a) => a.type))].sort();
    const typeCounts = {};
    const resultsBox = h("div", { "aria-live": "polite" });

    const q = h("input", { type: "search", id: "q", value: state.q, placeholder: "tema, título ou palavra-chave", autocomplete: "off" });
    const yf = h("input", { type: "number", id: "yf", min: "2015", max: "2026", value: state.yearFrom ?? "", placeholder: "de" });
    const yt = h("input", { type: "number", id: "yt", min: "2015", max: "2026", value: state.yearTo ?? "", placeholder: "até" });
    const oa = h("input", { type: "checkbox", id: "oa", checked: state.oaOnly });
    const area = h("select", { id: "area" }, ["Todas", ...areas].map((a) => h("option", { value: a, selected: a === state.area }, a)));
    const lang = h("select", { id: "lang" }, [["todos", "Todos"], ["pt", "Português"], ["en", "Inglês"], ["es", "Espanhol"]].map(([v, l]) => h("option", { value: v, selected: v === state.lang }, l)));
    const sort = h("select", { id: "sort" }, [["relevancia", "Relevância"], ["recentes", "Mais recentes"], ["citados", "Mais citados"]].map(([v, l]) => h("option", { value: v, selected: v === state.sort }, l)));
    const typeBoxes = types.map((type) => {
      const box = h("input", { type: "checkbox", value: type, checked: state.types.includes(type) });
      const count = h("span", { class: "count" }, "0");
      typeCounts[type] = count;
      return h("label", { class: "check" }, box, type, count);
    });

    function readControls() {
      state.q = q.value.trim();
      state.yearFrom = toInt(yf.value);
      state.yearTo = toInt(yt.value);
      state.oaOnly = oa.checked;
      state.area = area.value;
      state.lang = lang.value;
      state.sort = sort.value;
      state.types = typeBoxes.flatMap((label) => { const box = label.querySelector("input"); return box.checked ? [box.value] : []; });
    }

    let searchLogTimer;
    function sync({ keepPage = false } = {}) {
      if (!keepPage) state.page = 1;
      history.replaceState(null, "", hashFor("/busca", {
        q: state.q, yf: state.yearFrom, yt: state.yearTo, types: state.types.join(","), oa: state.oaOnly ? "1" : "",
        area: state.area === "Todas" ? "" : state.area, lang: state.lang === "todos" ? "" : state.lang,
        sort: state.sort === "relevancia" ? "" : state.sort, p: state.page > 1 ? state.page : "",
      }));
      const facets = Nav.facets(DATA, state.q);
      for (const type of types) typeCounts[type].textContent = String(facets.type[type] || 0);
      const { results, total, terms } = Nav.search(DATA, state);
      const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
      state.page = Math.min(state.page, pages);
      const slice = results.slice((state.page - 1) * PAGE_SIZE, state.page * PAGE_SIZE);
      mount(resultsBox, 
        h("div", { class: "results-head" },
          h("strong", {}, `${total} ${total === 1 ? "resultado" : "resultados"}`),
          h("span", { class: "muted" }, terms.length ? `para: ${terms.join(" + ")}` : "todos os artigos de exemplo")),
        total === 0
          ? h("div", { class: "empty card" }, h("p", {}, "Nenhum artigo encontrado."), h("p", { class: "muted" }, "Tente menos termos ou limpe os filtros."))
          : h("ol", { class: "results" }, slice.map((a) => resultCard(a, terms))),
        pages > 1 && h("div", { class: "pager" },
          h("button", { type: "button", class: "btn btn-secondary", disabled: state.page <= 1, onclick: () => { state.page -= 1; sync({ keepPage: true }); window.scrollTo(0, 0); } }, "← Anterior"),
          h("span", { class: "muted" }, `Página ${state.page} de ${pages}`),
          h("button", { type: "button", class: "btn btn-secondary", disabled: state.page >= pages, onclick: () => { state.page += 1; sync({ keepPage: true }); window.scrollTo(0, 0); } }, "Próxima →")),
      );
      clearTimeout(searchLogTimer);
      if (state.q) searchLogTimer = setTimeout(() => log("search", state.q), 700);
    }

    const onChange = () => { readControls(); sync(); };
    const filters = h("form", { class: "card filters", "aria-label": "Filtros", onsubmit: (e) => e.preventDefault(), oninput: onChange, onchange: onChange },
      h("div", { class: "field" }, h("label", { for: "q" }, "Buscar"), q),
      h("div", { class: "field" }, h("label", {}, "Ano de publicação"), h("div", { class: "row" }, yf, yt)),
      h("div", { class: "field" }, h("label", {}, "Tipo de estudo"), typeBoxes),
      h("div", { class: "field" }, h("label", { class: "check" }, oa, "Só acesso aberto")),
      h("div", { class: "field" }, h("label", { for: "area" }, "Área"), area),
      h("div", { class: "field" }, h("label", { for: "lang" }, "Idioma"), lang),
      h("div", { class: "field" }, h("label", { for: "sort" }, "Ordenar por"), sort),
      h("button", { type: "button", class: "btn btn-ghost", onclick: () => { go("/busca", {}); } }, "↺ Limpar filtros"),
    );
    // No celular os filtros começam recolhidos para os resultados aparecerem na primeira tela.
    const wide = window.matchMedia("(min-width: 901px)").matches;
    const filtersBlock = h("details", { class: "filters-wrap", open: wide },
      h("summary", { class: "btn btn-secondary" }, "Filtros e ordenação"), filters);
    mount($app, h("h1", {}, "Busca"), h("div", { class: "layout" }, filtersBlock, resultsBox));
    sync({ keepPage: true });
  }

  // ------------------------------------------------------------------ Artigo
  function renderArticle(id) {
    const article = BY_ID[id];
    if (!article) {
      pageTitle("Artigo não encontrado");
      mount($app, h("div", { class: "empty card" }, h("h1", {}, "Artigo não encontrado"), h("p", {}, "Este identificador não existe na maquete."), h("a", { class: "btn btn-primary", href: "#/busca" }, "Voltar à busca")));
      return;
    }
    pageTitle(article.title);

    // citação
    const citationBox = h("div", { "aria-live": "polite" });
    const showCitation = (style) => {
      const text = Nav.citations[style](article);
      log("cite", `${style}:${id}`);
      mount(citationBox, 
        h("div", { class: "citation" }, text),
        h("div", { class: "row" }, h("button", { type: "button", class: "btn btn-sm btn-secondary", onclick: () => copyText(text, `Referência ${style} copiada`) }, "Copiar"),
          h("span", { class: "note" }, "Gerada por código a partir dos metadados do registro (sem IA).")));
    };

    // tags
    const tagBox = h("div", { class: "stack" });
    const renderTags = () => {
      if (!isSaved(id)) { mount(tagBox, h("p", { class: "muted" }, "Salve o artigo para adicionar etiquetas.")); return; }
      const input = h("input", { type: "text", id: "tag", placeholder: "nova etiqueta (ex.: TCC)", maxlength: "30" });
      const add = () => {
        const tag = input.value.trim().slice(0, 30);
        if (tag && !library.items[id].tags.includes(tag) && library.items[id].tags.length < 12) { library.items[id].tags.push(tag); persist(); renderTags(); }
      };
      mount(tagBox, 
        h("div", { class: "chips" }, library.items[id].tags.map((t) => h("span", { class: "chip" }, t,
          h("button", { type: "button", "aria-label": `Remover etiqueta ${t}`, onclick: () => { library.items[id].tags = library.items[id].tags.filter((x) => x !== t); persist(); renderTags(); } }, "×")))),
        h("div", { class: "row" }, input, h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: add }, "Adicionar")));
    };

    const save = saveButton(id, false);
    save.addEventListener("click", renderTags);

    // lista
    const listSelect = h("select", { id: "add-list", "aria-label": "Adicionar a uma lista" },
      h("option", { value: "" }, library.lists.length ? "Adicionar à lista…" : "Nenhuma lista (crie abaixo)"),
      library.lists.map((l) => h("option", { value: l.id }, `${l.name} (${l.ids.length})`)));
    listSelect.addEventListener("change", () => {
      const list = library.lists.find((l) => l.id === listSelect.value);
      if (list && !list.ids.includes(id)) { list.ids.push(id); persist(); log("add_to_list", id); toast(`Adicionado a "${list.name}"`); renderArticle(id); }
    });
    const newList = h("input", { type: "text", id: "new-list", placeholder: "nome da nova lista", maxlength: String(Nav.MAX_LIST_NAME) });
    const createList = () => {
      const name = newList.value.trim();
      if (!name) return;
      library.lists.push({ id: `l${Date.now()}`, name, ids: [id] });
      persist(); log("create_list", name); toast(`Lista "${name}" criada`); renderArticle(id);
    };

    const sections = Nav.splitSections(article.abstract);
    const findingsList = Nav.findings(article.abstract);
    const similarList = Nav.similar(DATA, article, 3);

    mount($app, 
      h("article", { class: "article stack" },
        h("a", { href: "#/busca", class: "muted" }, "← voltar à busca"),
        h("h1", {}, article.title),
        h("div", { class: "meta" }, `${authorLine(article)} · ${article.journal}${article.volume ? `, v. ${article.volume}` : ""} · ${article.year}`),
        badges(article),
        h("div", { class: "row" }, save,
          article.oa
            ? h("a", { class: "btn btn-secondary", href: "#", onclick: (e) => { e.preventDefault(); toast("Maquete: na versão real abriria a cópia aberta legal"); } }, "Abrir versão aberta")
            : h("span", { class: "note" }, "Sem versão aberta conhecida"),
          h("button", { type: "button", class: "btn btn-outline", disabled: true, title: "Na versão real: botão opcional, com avisos e limite de uso" }, "Resumir com IA (opcional) — indisponível na maquete")),
        h("div", { class: "card stack" }, h("h3", {}, "Citar"),
          h("div", { class: "row" }, Object.keys(Nav.citations).map((s) => h("button", { type: "button", class: "btn btn-secondary", onclick: () => showCitation(s) }, s))),
          citationBox),
        h("div", { class: "card stack" }, h("h3", {}, "Resumo organizado (texto original)"),
          sections.length
            ? h("dl", { class: "sections" }, sections.map((s) => [h("dt", {}, s.label && s.label.toLowerCase() !== s.heading.toLowerCase() ? `${s.heading} (rótulo original: ${s.label})` : s.heading), h("dd", {}, s.text)]))
            : [h("p", { class: "note" }, "Este resumo não tem seções rotuladas; texto original completo:"), h("p", {}, article.abstract)]),
        h("div", { class: "card stack" }, h("h3", {}, "Números e dados estatísticos (com a frase de origem)"),
          findingsList.length
            ? findingsList.map((f) => h("div", { class: "finding" }, h("div", { class: "tags" }, f.tags.join(" · ")), h("div", {}, f.sentence)))
            : h("p", { class: "muted" }, "Nenhum dado estatístico foi encontrado no resumo."),
          h("p", { class: "note" }, "Frases copiadas do resumo; nada foi gerado nem interpretado. A seleção é por palavras-chave e pode omitir frases.")),
        h("div", { class: "card stack" }, h("h3", {}, "Metadados"),
          h("table", {}, h("tbody", {},
            [["Tipo de estudo", article.type], ["Periódico", article.journal], ["Ano", article.year], ["DOI (fictício)", article.doi], ["Idioma", LANG_NAMES[article.lang]], ["Fonte", article.source], ["Citações", article.citations]]
              .map(([k, v]) => h("tr", {}, h("th", { scope: "row" }, k), h("td", {}, String(v)))))),
          h("div", { class: "kw" }, article.keywords.map((k) => h("a", { href: hashFor("/busca", { q: k }) }, k)))),
        h("div", { class: "card stack" }, h("h3", {}, "Organizar"), tagBox,
          h("div", { class: "row" }, listSelect),
          h("div", { class: "row" }, newList, h("button", { type: "button", class: "btn btn-secondary btn-sm", onclick: createList }, "Criar lista com este artigo"))),
        similarList.length ? h("div", { class: "card stack" }, h("h3", {}, "Artigos semelhantes"),
          h("ul", { class: "stack" }, similarList.map((s) => h("li", {}, h("a", { href: hashFor(`/artigo/${s.id}`) }, s.title), h("span", { class: "muted" }, ` · ${s.type} · ${s.year}`))))) : null,
      ),
    );
    renderTags();
  }

  // ------------------------------------------------------------------ Biblioteca
  function renderLibrary(params) {
    pageTitle("Biblioteca");
    const ids = Object.keys(library.items);
    const allTags = [...new Set(ids.flatMap((id) => library.items[id].tags))].sort();
    const activeTag = params.get("tag") || "";
    const shown = ids.filter((id) => !activeTag || library.items[id].tags.includes(activeTag));
    const articles = ids.map((id) => BY_ID[id]);

    const exportButton = (label, filename, build, mime) => h("button", { type: "button", class: "btn btn-secondary", disabled: !ids.length,
      onclick: () => { download(filename, build(articles), mime); log("export", filename); toast(`${filename} gerado`); } }, label);

    const listName = h("input", { type: "text", id: "list-name", placeholder: "nome da lista (ex.: Leituras da semana 3)", maxlength: String(Nav.MAX_LIST_NAME) });
    const createList = () => {
      const name = listName.value.trim();
      if (!name) return;
      library.lists.push({ id: `l${Date.now()}`, name, ids: [] });
      persist(); log("create_list", name); renderLibrary(params);
    };

    mount($app, 
      h("h1", {}, "Biblioteca"),
      h("p", { class: "lead" }, "Seus artigos salvos ficam só neste navegador (maquete). Etiquete, exporte e monte listas para compartilhar."),
      h("div", { class: "row" },
        exportButton("Exportar BibTeX", "biblioteca.bib", Nav.toBibtex, "application/x-bibtex"),
        exportButton("Exportar RIS", "biblioteca.ris", Nav.toRis, "application/x-research-info-systems"),
        h("button", { type: "button", class: "btn btn-secondary", disabled: !ids.length, onclick: () => {
          log("export", "abnt"); copyText(articles.map(Nav.citations.ABNT).join("\n\n"), "Referências ABNT copiadas"); } }, "Copiar referências ABNT")),
      allTags.length ? h("div", { class: "chips" },
        h("a", { class: `chip${activeTag ? "" : " active"}`, href: hashFor("/biblioteca") }, "todas"),
        allTags.map((t) => h("a", { class: `chip${t === activeTag ? " active" : ""}`, href: hashFor("/biblioteca", { tag: t }) }, t))) : null,
      !ids.length
        ? h("div", { class: "empty card" }, h("p", {}, "Sua biblioteca está vazia."), h("a", { class: "btn btn-primary", href: "#/busca" }, "Buscar artigos"))
        : h("ul", { class: "results" }, shown.map((id) => {
          const a = BY_ID[id];
          return h("li", { class: "result" },
            h("h3", {}, h("a", { href: hashFor(`/artigo/${id}`) }, a.title)),
            h("div", { class: "meta" }, `${authorLine(a)} · ${a.journal} · ${a.year}`),
            h("div", { class: "chips" }, library.items[id].tags.map((t) => h("span", { class: "chip" }, t))),
            h("div", { class: "row" }, h("button", { type: "button", class: "btn btn-sm btn-ghost", onclick: () => { toggleSave(id); renderLibrary(params); } }, "Remover")));
        })),
      h("h2", {}, "Listas de leitura"),
      h("div", { class: "row" }, listName, h("button", { type: "button", class: "btn btn-primary", onclick: createList }, "Criar lista")),
      library.lists.length ? library.lists.map((list) => h("div", { class: "card stack" },
        h("h3", {}, `${list.name} (${list.ids.length})`),
        h("ul", {}, list.ids.map((id) => h("li", {}, h("a", { href: hashFor(`/artigo/${id}`) }, BY_ID[id].title)))),
        h("div", { class: "row" },
          h("button", { type: "button", class: "btn btn-secondary btn-sm", disabled: !list.ids.length, onclick: () => {
            const link = `${location.href.split("#")[0]}#/lista?${Nav.encodeList(list.name, list.ids)}`;
            log("share", list.name); copyText(link, "Link da lista copiado"); } }, "Copiar link para compartilhar"),
          h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: () => { library.lists = library.lists.filter((l) => l.id !== list.id); persist(); renderLibrary(params); } }, "Excluir lista"))))
        : h("p", { class: "muted" }, "Nenhuma lista ainda. Crie uma e adicione artigos pela página de cada artigo."),
    );
  }

  // ------------------------------------------------------------------ Lista compartilhada
  function renderSharedList(search) {
    pageTitle("Lista compartilhada");
    const { name, ids } = Nav.decodeList(search, DATA.map((a) => a.id));
    mount($app, 
      h("h1", {}, name),
      h("p", { class: "note" }, "Lista compartilhada (maquete: o link carrega os dados na própria URL; na versão real seria um endereço curto)."),
      ids.length
        ? h("ul", { class: "results" }, ids.map((id) => h("li", { class: "result" }, h("h3", {}, h("a", { href: hashFor(`/artigo/${id}`) }, BY_ID[id].title)),
          h("div", { class: "meta" }, `${authorLine(BY_ID[id])} · ${BY_ID[id].year}`), badges(BY_ID[id]))))
        : h("div", { class: "empty card" }, "Esta lista não tem artigos válidos."),
      h("div", { class: "row" }, h("button", { type: "button", class: "btn btn-primary", disabled: !ids.length, onclick: () => {
        for (const id of ids) if (!isSaved(id)) library.items[id] = { tags: [], savedAt: Date.now() };
        persist(); log("save_list", name); renderNav(); toast("Artigos salvos na sua biblioteca"); } }, "Salvar todos na minha biblioteca")),
    );
  }

  // ------------------------------------------------------------------ Modo teste
  function renderTest() {
    pageTitle("Modo teste");
    let test = read(KEYS.test, { active: null, results: {} });
    if (!test || typeof test !== "object") test = { active: null, results: {} };
    const save = () => write(KEYS.test, test);
    const summary = Nav.summarizeEvents(events);

    const finish = (task, outcome) => {
      const since = events.filter((e) => e.t >= test.active.start);
      test.results[task.id] = { outcome, seconds: Math.round((Date.now() - test.active.start) / 1000), actions: since.length, netSaved: Nav.summarizeEvents(since).netSaved };
      test.active = null; save(); renderTest();
    };

    mount($app, 
      h("h1", {}, "Modo teste"),
      h("p", { class: "lead" }, "Para conduzir testes de usabilidade com pessoas. Peça que leiam a tarefa em voz alta, cronometre e registre se conseguiram. Os registros ficam só neste navegador."),
      h("div", { class: "card" }, h("table", {},
        h("thead", {}, h("tr", {}, ["Perfil", "Tarefa", "Resultado", ""].map((t) => h("th", {}, t)))),
        h("tbody", {}, TASKS.map((task) => {
          const result = test.results[task.id];
          const running = test.active && test.active.id === task.id;
          return h("tr", {},
            h("td", {}, task.persona), h("td", {}, task.text),
            h("td", {}, result ? `${result.outcome} · ${result.seconds}s · ${result.actions} ações · ${result.netSaved} salvos` : (running ? "em andamento…" : "—")),
            h("td", {}, running
              ? h("div", { class: "row" },
                h("button", { type: "button", class: "btn btn-primary btn-sm", onclick: () => finish(task, "conseguiu") }, "Conseguiu"),
                h("button", { type: "button", class: "btn btn-ghost btn-sm", onclick: () => finish(task, "desistiu") }, "Desistiu"))
              : h("button", { type: "button", class: "btn btn-secondary btn-sm", disabled: Boolean(test.active), onclick: () => { test.active = { id: task.id, start: Date.now() }; save(); renderTest(); } }, "Iniciar")));
        })))),
      h("h2", {}, "Registro de ações"),
      h("div", { class: "card stack" },
        h("p", {}, `${summary.total} ações · ${summary.netSaved} artigos salvos (líquido)`),
        h("div", { class: "chips" }, Object.entries(summary.counts).map(([k, v]) => h("span", { class: "chip" }, `${k}: ${v}`))),
        h("div", { class: "row" },
          h("button", { type: "button", class: "btn btn-secondary", onclick: () => download("teste-navegador.json", JSON.stringify({ results: test.results, events }, null, 2), "application/json") }, "Exportar JSON"),
          h("button", { type: "button", class: "btn btn-ghost", onclick: () => { events = []; write(KEYS.events, events); test = { active: null, results: {} }; save(); renderTest(); toast("Dados do teste apagados"); } }, "Apagar dados do teste"))),
    );
  }

  // ------------------------------------------------------------------ roteador
  function render() {
    renderNav();
    const [path, query = ""] = (location.hash.slice(1) || "/").split("?");
    const params = new URLSearchParams(query);
    const parts = path.split("/").filter(Boolean);
    const view = parts[0] || "";
    if (view === "busca") renderSearch(params);
    else if (view === "artigo" && parts[1]) renderArticle(parts[1]);
    else if (view === "biblioteca") renderLibrary(params);
    else if (view === "lista") renderSharedList(query);
    else if (view === "teste") renderTest();
    else renderHome();
    if (view !== "busca") { window.scrollTo(0, 0); }
  }

  window.addEventListener("hashchange", () => { render(); $app.focus({ preventScroll: true }); });
  render();
})();
