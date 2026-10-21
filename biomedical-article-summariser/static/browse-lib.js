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

  /** Caminho da IA com o artigo preenchido: /ia?artigo=REF#geral */
  function aiLabHref(ref, tab = "geral") {
    return `/ia?${new URLSearchParams({ artigo: ref }).toString()}#${tab}`;
  }

  return {
    SEARCH_DEFAULTS, FEED_AREAS, feedArea, parseRoute, buildHash, searchStateFromParams, paramsFromSearchState, apiParamsFromSearchState,
    safeHttpUrl, formatCount, debounce, pageWindow, aiLabHref,
  };
});
