/* Lógica pura da maquete (sem DOM): busca, filtros, extração sem IA, citações, exportação e listas.
   Roda no navegador (window.Nav) e no Node (module.exports), onde é testada em tests/lib.test.js. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.Nav = api;
})(typeof self !== "undefined" ? self : globalThis, function () {
  "use strict";

  // ------------------------------------------------------------------ texto
  const normalize = (text) =>
    String(text || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  const tokenize = (query) =>
    [...new Set(normalize(query).split(/[^a-z0-9]+/).filter((t) => t.length > 1))];

  const SENTENCE_SPLIT = /(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9(\[])|\n+/;
  const splitSentences = (text) => String(text || "").split(SENTENCE_SPLIT).map((s) => s.trim()).filter(Boolean);

  // ------------------------------------------------------------------ busca
  function haystacks(article) {
    return {
      title: normalize(article.title),
      keywords: normalize(article.keywords.join(" ")),
      abstract: normalize(article.abstract),
      other: normalize(article.authors.map((a) => `${a.given} ${a.family}`).join(" ") + " " + article.journal),
    };
  }

  /** Pontuação de relevância; 0 se algum termo não aparecer em lugar nenhum (busca E). */
  function score(article, terms) {
    if (!terms.length) return 0;
    const h = haystacks(article);
    let total = 0;
    for (const term of terms) {
      let term_score = 0;
      if (h.title.includes(term)) term_score += 5;
      if (h.keywords.includes(term)) term_score += 3;
      if (h.abstract.includes(term)) term_score += 1;
      if (h.other.includes(term)) term_score += 1;
      if (term_score === 0) return 0;
      total += term_score;
    }
    return total;
  }

  function matchesFilters(article, f) {
    if (f.yearFrom && article.year < f.yearFrom) return false;
    if (f.yearTo && article.year > f.yearTo) return false;
    if (f.types && f.types.length && !f.types.includes(article.type)) return false;
    if (f.oaOnly && !article.oa) return false;
    if (f.area && f.area !== "Todas" && article.area !== f.area) return false;
    if (f.lang && f.lang !== "todos" && article.lang !== f.lang) return false;
    return true;
  }

  const SORTERS = {
    relevancia: (a, b) => b._score - a._score || b.citations - a.citations || b.year - a.year,
    recentes: (a, b) => b.year - a.year || b.citations - a.citations,
    citados: (a, b) => b.citations - a.citations || b.year - a.year,
  };

  /** Busca + filtros + ordenação. Sem consulta, "relevância" cai para mais citados. */
  function search(data, params = {}) {
    const terms = tokenize(params.q);
    const sort = SORTERS[params.sort] ? params.sort : "relevancia";
    const results = data
      .map((article) => ({ ...article, _score: score(article, terms) }))
      .filter((a) => (terms.length ? a._score > 0 : true) && matchesFilters(a, params));
    results.sort(SORTERS[sort]);
    return { results, total: results.length, terms };
  }

  /** Contagens por faceta considerando só a consulta (para mostrar números ao lado de cada filtro). */
  function facets(data, q) {
    const terms = tokenize(q);
    const base = data.filter((a) => (terms.length ? score(a, terms) > 0 : true));
    const count = (key) => {
      const out = {};
      for (const a of base) out[a[key]] = (out[a[key]] || 0) + 1;
      return out;
    };
    return { type: count("type"), area: count("area"), lang: count("lang"), oa: base.filter((a) => a.oa).length };
  }

  /** Trechos de texto marcando os termos buscados (para montar <mark> sem innerHTML). */
  function splitHighlight(text, terms) {
    const source = String(text || "");
    if (!terms.length) return [{ text: source, hit: false }];
    const plain = normalize(source); // normalize preserva o comprimento em texto sem combinações exóticas
    if (plain.length !== source.length) return [{ text: source, hit: false }];
    const marks = new Array(source.length).fill(false);
    for (const term of terms) {
      let from = 0;
      for (;;) {
        const at = plain.indexOf(term, from);
        if (at < 0) break;
        for (let i = at; i < at + term.length; i++) marks[i] = true;
        from = at + term.length;
      }
    }
    const parts = [];
    let start = 0;
    for (let i = 1; i <= source.length; i++) {
      if (i === source.length || marks[i] !== marks[start]) {
        parts.push({ text: source.slice(start, i), hit: marks[start] });
        start = i;
      }
    }
    return parts;
  }

  function similar(data, article, limit = 3) {
    const own = new Set(article.keywords.map(normalize));
    return data
      .filter((other) => other.id !== article.id)
      .map((other) => ({
        other,
        score: other.keywords.filter((k) => own.has(normalize(k))).length * 2 + (other.area === article.area ? 1 : 0),
      }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score || b.other.citations - a.other.citations)
      .slice(0, limit)
      .map((x) => x.other);
  }

  // ------------------------------------------------------------------ extração sem IA
  const SECTION_LABELS = {
    Contexto: ["background", "introduction", "context", "rationale", "introdução", "introducao", "introducción", "contexto", "antecedentes"],
    Objetivo: ["objectives", "objective", "aims", "aim", "purpose", "goal", "objetivos", "objetivo"],
    "Métodos": ["materials and methods", "material y métodos", "methodology", "methods", "method", "design", "participants", "patients", "métodos", "metodos", "método", "metodologia", "desenho"],
    Resultados: ["results", "result", "findings", "resultados", "resultado", "achados"],
    "Conclusões": ["conclusions", "conclusion", "interpretation", "conclusões", "conclusoes", "conclusão", "conclusiones", "conclusión"],
    "Limitações": ["limitations", "limitação", "limitações"],
  };
  const LABEL_TO_HEADING = {};
  for (const [heading, labels] of Object.entries(SECTION_LABELS)) for (const label of labels) LABEL_TO_HEADING[label] = heading;
  const LABEL_ALT = Object.keys(LABEL_TO_HEADING)
    .sort((a, b) => b.length - a.length)
    .map((l) => l.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  const COLON_RE = new RegExp(`(^|[.!?]\\s+)(${LABEL_ALT})\\s*:\\s*`, "gi");
  const DOT_RE = new RegExp(`(^|[.!?]\\s+)(${LABEL_ALT})\\.\\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])`, "gi");

  /** Divide o resumo pelos rótulos originais; menos de 2 rótulos (3 com ponto) = sem estrutura. */
  function splitSections(abstract) {
    const text = String(abstract || "").trim();
    let matches = [...text.matchAll(COLON_RE)];
    if (matches.length < 2) {
      matches = [...text.matchAll(DOT_RE)].filter((m) => /^[A-ZÁÉÍÓÚÂÊÔÃÕÇ]/.test(m[2]));
      if (matches.length < 3) return [];
    }
    const sections = [];
    const first = matches[0];
    const preamble = text.slice(0, first.index + (first[1] ? 1 : 0)).trim();
    if (preamble) sections.push({ heading: "Texto inicial", label: "", text: preamble });
    matches.forEach((m, i) => {
      const start = m.index + m[0].length;
      const next = matches[i + 1];
      const end = next ? next.index + (next[1] ? 1 : 0) : text.length;
      const body = text.slice(start, end).trim();
      if (body) sections.push({ heading: LABEL_TO_HEADING[normalizeLabel(m[2])] || m[2], label: m[2], text: body });
    });
    return sections;
  }
  const normalizeLabel = (label) => label.toLowerCase();

  const NUM = "-?\\d+(?:[.,]\\d+)?";
  const FINDING_PATTERNS = [
    ["tamanho da amostra", new RegExp("\\b[nN]\\s*=\\s*\\d[\\d.,]*|\\b\\d[\\d.,]*\\s+(?:adult|patient|participant|subject|individual|women|men|children|infant|case|person|people|student|stud(?:y|ies)|trial|pacient|particip|adulto|crian|mulher|homem|indiv|caso|estudante|estudos?|ensaios|control)", "i")],
    ["medida de efeito", new RegExp(`\\b(?:a?HR|a?OR|a?RR|IRR|SMD|RRR|ARR|NNT|NNH|RMa?|raz[aã]o de (?:prevalência|risco|chances))\\b\\s*(?:[=:]|of|de)?\\s*${NUM}`, "i")],
    ["intervalo de confiança", new RegExp(`\\b(?:(?:90|95|99)\\s*%\\s*(?:CI|IC)|(?:CI|IC)\\s*(?:90|95|99)\\s*%?)[^0-9\\-]{0,12}${NUM}\\s*(?:-|–|—|to|a|,)\\s*${NUM}`, "i")],
    ["valor de p", /\bp\s*(?:value\s*)?[<>=≤≥]\s*0?[.,]?\d+/i],
    ["seguimento", new RegExp(`(?:followed|follow-up|seguimento|acompanhad\\w*)[^.;]{0,60}?${NUM}\\s*(?:years?|months?|weeks?|days?|anos?|meses|semanas|dias)`, "i")],
    ["percentual", new RegExp(`${NUM}\\s*%`)],
  ];
  const CI_LABEL = /\b(?:CI|IC)\s*(?:90|95|99)\s*%|\b(?:90|95|99)\s*%\s*(?:CI|IC)\b/gi;

  /** Frases com dados estatísticos, copiadas do resumo, com o tipo de dado encontrado. */
  function findings(abstract) {
    const out = [];
    for (const sentence of splitSentences(abstract)) {
      const tags = FINDING_PATTERNS.filter(([tag, re]) => re.test(tag === "percentual" ? sentence.replace(CI_LABEL, " ") : sentence)).map(([tag]) => tag);
      if (tags.length) out.push({ sentence, tags });
    }
    return out.slice(0, 15);
  }

  // ------------------------------------------------------------------ citações
  const initials = (given) => (given || "").split(/[\s.\-]+/).filter(Boolean).map((p) => p[0].toUpperCase());
  const cleanTitle = (t) => String(t || "").replace(/<[^>]+>/g, "").replace(/\s+/g, " ").trim().replace(/\.$/, "");
  const pagesWith = (pages, dash) => String(pages || "").replace(/\s*[-–—]\s*/, dash);

  function abnt(a) {
    const name = (x) => `${x.family.toUpperCase()}, ${initials(x.given).map((i) => i + ".").join(" ")}`.trim().replace(/,$/, "");
    let head = a.authors.length > 3 ? `${name(a.authors[0])} et al.` : a.authors.map(name).join("; ");
    if (head && !head.endsWith(".")) head += ".";
    const tail = [a.journal, a.volume && `v. ${a.volume}`, a.issue && `n. ${a.issue}`, a.pages && `p. ${pagesWith(a.pages, "-")}`, a.year && String(a.year)].filter(Boolean).join(", ");
    return [head, `${cleanTitle(a.title)}.`, tail && `${tail}.`, a.doi && `DOI: ${a.doi}.`].filter(Boolean).join(" ");
  }

  function apa(a) {
    const name = (x) => `${x.family}, ${initials(x.given).map((i) => i + ".").join(" ")}`.trim().replace(/,$/, "");
    const names = a.authors.slice(0, 20).map(name);
    const head = names.length <= 1 ? names[0] || "" : `${names.slice(0, -1).join(", ")}, & ${names[names.length - 1]}`;
    let source = a.journal || "";
    if (a.volume) source += `, ${a.volume}${a.issue ? `(${a.issue})` : ""}`;
    if (a.pages) source += `, ${pagesWith(a.pages, "–")}`;
    return [`${head} (${a.year}).`, `${cleanTitle(a.title)}.`, source && `${source}.`, a.doi && `https://doi.org/${a.doi}`].filter(Boolean).join(" ");
  }

  function vancouver(a) {
    const name = (x) => `${x.family} ${initials(x.given).join("")}`.trim();
    const head = a.authors.slice(0, 6).map(name).join(", ") + (a.authors.length > 6 ? ", et al" : "");
    let locator = String(a.year);
    if (a.volume) locator += `;${a.volume}${a.issue ? `(${a.issue})` : ""}`;
    if (a.pages) locator += `:${pagesWith(a.pages, "-")}`;
    return [head && `${head}.`, `${cleanTitle(a.title)}.`, a.journal && `${a.journal}.`, `${locator}.`, a.doi && `doi:${a.doi}`].filter(Boolean).join(" ");
  }

  const CITATION_STYLES = { ABNT: abnt, APA: apa, Vancouver: vancouver };

  // ------------------------------------------------------------------ exportação
  const bibEscape = (v) => String(v).replace(/([&%#_$])/g, "\\$1");
  const bibKey = (a, used) => {
    const family = normalize(a.authors[0] ? a.authors[0].family : "anon").replace(/[^a-z0-9]/g, "");
    const word = (normalize(a.title).match(/[a-z]{4,}/) || ["artigo"])[0];
    let key = `${family}${a.year}${word}`;
    while (used.has(key)) key += "x";
    used.add(key);
    return key;
  };

  function toBibtex(articles) {
    const used = new Set();
    return articles
      .map((a) => {
        const fields = [
          ["author", a.authors.map((x) => `${bibEscape(x.family)}, ${bibEscape(x.given)}`).join(" and ")],
          ["title", `{${bibEscape(cleanTitle(a.title))}}`],
          ["journal", bibEscape(a.journal)],
          ["year", String(a.year)],
          ["volume", a.volume],
          ["number", a.issue],
          ["pages", a.pages && pagesWith(a.pages, "--")],
          ["doi", a.doi],
        ].filter(([, v]) => v);
        return `@article{${bibKey(a, used)},\n${fields.map(([k, v]) => `  ${k} = {${v}}`).join(",\n")}\n}`;
      })
      .join("\n\n");
  }

  function toRis(articles) {
    return articles
      .map((a) => {
        const [sp, ep] = String(a.pages || "").split(/\s*[-–—]\s*/);
        const lines = ["TY  - JOUR", ...a.authors.map((x) => `AU  - ${x.family}, ${x.given}`), `TI  - ${cleanTitle(a.title)}`,
          `JO  - ${a.journal}`, `PY  - ${a.year}`];
        if (a.volume) lines.push(`VL  - ${a.volume}`);
        if (a.issue) lines.push(`IS  - ${a.issue}`);
        if (sp) lines.push(`SP  - ${sp}`);
        if (ep) lines.push(`EP  - ${ep}`);
        if (a.doi) lines.push(`DO  - ${a.doi}`);
        for (const k of a.keywords) lines.push(`KW  - ${k}`);
        lines.push(`AB  - ${a.abstract}`, "ER  - ");
        return lines.join("\n");
      })
      .join("\n\n");
  }

  // ------------------------------------------------------------------ listas compartilháveis
  const MAX_LIST_NAME = 80;

  function encodeList(name, ids) {
    return new URLSearchParams({ nome: name, ids: ids.join(",") }).toString();
  }

  /** Lê uma lista da URL aceitando só IDs conhecidos e limpando o nome (a URL é entrada não confiável). */
  function decodeList(search, knownIds) {
    const params = new URLSearchParams(search);
    const name = (params.get("nome") || "Lista sem nome").replace(/[\u0000-\u001f\u007f]/g, " ").trim().slice(0, MAX_LIST_NAME) || "Lista sem nome";
    const known = new Set(knownIds);
    const ids = [...new Set((params.get("ids") || "").split(",").map((s) => s.trim()))].filter((id) => known.has(id));
    return { name, ids };
  }

  // ------------------------------------------------------------------ modo teste
  /** Resume o registro de eventos do teste de usabilidade. */
  function summarizeEvents(events) {
    const counts = {};
    for (const e of events) counts[e.type] = (counts[e.type] || 0) + 1;
    const saved = events.filter((e) => e.type === "save").length - events.filter((e) => e.type === "unsave").length;
    return { counts, netSaved: Math.max(0, saved), total: events.length };
  }

  return {
    normalize, tokenize, splitSentences, score, search, facets, splitHighlight, similar,
    splitSections, findings, citations: CITATION_STYLES, toBibtex, toRis, encodeList, decodeList, summarizeEvents,
    MAX_LIST_NAME,
  };
});
