/* Funções puras do navegador de artigos (sem DOM): rotas, estado da busca e utilidades.
   Rodam no navegador (window.BrowseLib) e no Node (testes em tests/js/browse-lib.test.js). */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.BrowseLib = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  "use strict";

  const SEARCH_DEFAULTS = Object.freeze({
    q: "", yearFrom: null, yearTo: null, types: [], oa: false, lang: "", sort: "relevance", page: 1, source: "",
  });

  /** "#/busca?q=x" -> { view: "busca", rest: [], params }. Hash vazio ou desconhecido = início. */
  function parseRoute(hash) {
    const raw = String(hash || "").replace(/^#/, "") || "/";
    const [path, ...queryParts] = raw.split("?");
    const params = new URLSearchParams(queryParts.join("?"));
    const parts = path.split("/").filter(Boolean).map((p) => {
      try { return decodeURIComponent(p); } catch { return p; }
    });
    const known = ["busca", "artigo", "biblioteca", "lista", "interesses", "relatorio", "perfil", "feed", "redefinir", "confirmar", "termos", "privacidade", "planos", "admin"];
    const view = known.includes(parts[0]) ? parts[0] : "";
    return { view, rest: view ? parts.slice(1) : [], params };
  }

  const FEED_AREAS = ["medicina", "farmacia", "enfermagem", "odontologia", "nutricao", "biologia", "psicologia", "computacao", "engenharia",
    "exatas", "ambiente", "agrarias", "sociais", "educacao"];

  /** Área que dá cor e ícone ao cartão do feed: a primeira área conhecida do item; sem nenhuma, "geral". */
  function feedArea(keys) {
    return (Array.isArray(keys) ? keys : []).find((key) => FEED_AREAS.includes(key)) || "geral";
  }

  function buildHash(path, params = {}) {
    const query = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== "" && v !== null && v !== undefined && v !== false),
    ).toString();
    return `#${path}${query ? `?${query}` : ""}`;
  }

  const toInt = (value) => {
    const n = Number.parseInt(value, 10);
    return Number.isFinite(n) ? n : null;
  };

  /** Estado da busca a partir da URL (entrada não confiável: valores inválidos viram padrão). */
  function searchStateFromParams(params) {
    const sorts = ["relevance", "recent", "cited"];
    const year = (v) => { const n = toInt(v); return n !== null && n >= 1800 && n <= 2100 ? n : null; };
    return {
      q: (params.get("q") || "").slice(0, 300),
      yearFrom: year(params.get("yf")),
      yearTo: year(params.get("yt")),
      types: (params.get("types") || "").split(",").map((t) => t.trim()).filter(Boolean).slice(0, 10),
      oa: params.get("oa") === "1",
      lang: ["pt", "en", "es"].includes(params.get("lang")) ? params.get("lang") : "",
      sort: sorts.includes(params.get("sort")) ? params.get("sort") : "relevance",
      page: Math.min(500, Math.max(1, toInt(params.get("p")) || 1)),
      source: (params.get("fonte") || "").replace(/[^a-z0-9_-]/gi, "").slice(0, 40),
    };
  }

  /** Parâmetros da URL do navegador (hash) para um estado de busca. */
  function paramsFromSearchState(state) {
    return {
      q: state.q, yf: state.yearFrom, yt: state.yearTo, types: state.types.join(","), oa: state.oa ? "1" : "",
      lang: state.lang, sort: state.sort === "relevance" ? "" : state.sort, p: state.page > 1 ? state.page : "",
      fonte: state.source,
    };
  }

  /** Parâmetros da API /api/discover/search para um estado de busca. */
  function apiParamsFromSearchState(state, perPage = 10) {
    const params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    if (state.yearFrom) params.set("yf", String(state.yearFrom));
    if (state.yearTo) params.set("yt", String(state.yearTo));
    if (state.types.length) params.set("types", state.types.join(","));
    if (state.oa) params.set("oa", "true");
    if (state.lang) params.set("lang", state.lang);
    if (state.sort !== "relevance") params.set("sort", state.sort);
    if (state.page > 1) params.set("page", String(state.page));
    if (state.source) params.set("source", state.source);
    params.set("per_page", String(perPage));
    return params;
  }

  /** Só links http(s) viram âncoras (nunca javascript:, data: etc.). */
  function safeHttpUrl(url) {
    try {
      const parsed = new URL(String(url));
      return parsed.protocol === "https:" || parsed.protocol === "http:" ? parsed.href : "";
    } catch {
      return "";
    }
  }

  const formatCount = (n) => Number(n || 0).toLocaleString("pt-BR");

  function debounce(fn, ms) {
    let timer;
    const wrapped = (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
    wrapped.cancel = () => clearTimeout(timer);
    return wrapped;
  }

  /** Janela de páginas para o paginador: [1, …, 4, 5, 6, …, 20]. */
  function pageWindow(current, total, radius = 1) {
    const pages = new Set([1, total]);
    for (let p = current - radius; p <= current + radius; p++) if (p >= 1 && p <= total) pages.add(p);
    const sorted = [...pages].sort((a, b) => a - b);
    const out = [];
    sorted.forEach((p, i) => {
      if (i > 0 && p - sorted[i - 1] > 1) out.push("…");
      out.push(p);
    });
    return out;
  }

  const RATING_TONES = { Alta: "high", Moderada: "mid", Baixa: "low", Retratado: "bad" };
  /** Tom visual da nota de um cartão: high, mid, low, bad (retratado) ou none (sem base para avaliar). */
  function scoreTone(rating) {
    return (rating && typeof rating.score === "number" && RATING_TONES[rating.band]) || "none";
  }

  const ACCENTS = new RegExp(`[${String.fromCharCode(0x300)}-${String.fromCharCode(0x36f)}]`, "g");  // marcas de acento depois de decompor
  const fold = (text) => String(text || "").normalize("NFD").replace(ACCENTS, "").toLowerCase();
  /** Filtra a biblioteca por etiqueta e por texto (todas as palavras, sem acento, em título, autores, revista e etiquetas). */
  function filterLibrary(items, text, tag) {
    const words = fold(text).split(/\s+/).filter(Boolean);
    return items.filter((item) => {
      if (tag && !(item.tags || []).includes(tag)) return false;
      if (!words.length) return true;
      const haystack = fold([item.title, item.authors, item.journal, ...(item.tags || [])].join(" "));
      return words.every((word) => haystack.includes(word));
    });
  }

  const LIBRARY_SORTS = ["recentes", "nota", "ano", "titulo"];
  /** Ordena a biblioteca sem alterar a lista original; sem valor (nota, ano) vai para o fim; empates mantêm a ordem. */
  function sortLibrary(items, mode) {
    const rank = (item) => (mode === "nota" ? item.rating && typeof item.rating.score === "number" ? item.rating.score : null : item.year ?? null);
    const copy = items.map((item, index) => ({ item, index }));
    copy.sort((a, b) => {
      if (mode === "titulo") return String(a.item.title).localeCompare(String(b.item.title), "pt-BR") || a.index - b.index;
      if (mode === "nota" || mode === "ano") {
        const x = rank(a.item), y = rank(b.item);
        if (x === null && y === null) return a.index - b.index;
        if (x === null) return 1;
        if (y === null) return -1;
        return y - x || a.index - b.index;
      }
      return String(b.item.savedAt || "").localeCompare(String(a.item.savedAt || "")) || a.index - b.index;  // recentes
    });
    return copy.map((entry) => entry.item);
  }

  /** Progresso (0 a 1) da rolagem dentro de uma seção alta com palco fixo: `top` é o topo da seção na tela. */
  function journeyProgress(top, sectionHeight, viewportHeight) {
    const total = sectionHeight - viewportHeight;
    if (!(total > 0)) return 0;
    return Math.max(0, Math.min(1, -top / total));
  }

  /** Cena (1, 2 ou 3) que cada faixa do progresso mostra na "jornada" da página inicial. */
  function journeyScene(progress) {
    return progress < 0.34 ? 1 : progress < 0.67 ? 2 : 3;
  }

  /** Valor do contador no instante `k` (0 a 1) da animação, com saída suave. */
  function countAt(end, k) {
    const x = Math.max(0, Math.min(1, k));
    return Math.round(end * (1 - Math.pow(1 - x, 3)));
  }

  /** Primeiros passos concluídos, em ordem, e quantos faltam: [{done, label, href}] -> {done, total, next}. */
  function stepsSummary(steps) {
    const done = steps.filter((step) => step.done).length;
    return { done, total: steps.length, percent: steps.length ? Math.round((done / steps.length) * 100) : 0, next: steps.find((step) => !step.done) || null };
  }

  /** Caminho da IA com o artigo preenchido: /ia?artigo=REF#geral */
  function aiLabHref(ref, tab = "geral") {
    return `/ia?${new URLSearchParams({ artigo: ref }).toString()}#${tab}`;
  }

  return {
    SEARCH_DEFAULTS, FEED_AREAS, feedArea, parseRoute, buildHash, searchStateFromParams, paramsFromSearchState, apiParamsFromSearchState,
    safeHttpUrl, formatCount, debounce, pageWindow, aiLabHref, journeyProgress, journeyScene, countAt, stepsSummary,
    scoreTone, filterLibrary, sortLibrary, LIBRARY_SORTS,
  };
});
