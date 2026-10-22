"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");

const Lib = require("../../nexus-science/static/browse-lib.js");

test("parseRoute reconhece as telas e ignora o desconhecido", () => {
  assert.deepEqual(Lib.parseRoute("#/busca?q=sepsis").view, "busca");
  assert.equal(Lib.parseRoute("#/busca?q=sepsis").params.get("q"), "sepsis");
  assert.equal(Lib.parseRoute("#/interesses").view, "interesses");
  assert.equal(Lib.parseRoute("#/redefinir?token=x").view, "redefinir");
  assert.equal(Lib.parseRoute("#/confirmar?token=x").params.get("token"), "x");
  assert.equal(Lib.parseRoute("#/perfil").view, "perfil");
  assert.deepEqual(Lib.parseRoute("#/perfil/interesses").rest, ["interesses"]);
  assert.equal(Lib.parseRoute("#/perfil/conta").view, "perfil");
  assert.equal(Lib.parseRoute("#/feed?tipo=noticias").view, "feed");
  assert.equal(Lib.parseRoute("#/feed?tipo=noticias").params.get("tipo"), "noticias");
  assert.equal(Lib.parseRoute("").view, "");
  assert.equal(Lib.parseRoute("#/").view, "");
  assert.equal(Lib.parseRoute("#/nada-aqui/segredo").view, "");
  assert.deepEqual(Lib.parseRoute("#/lista/Ab3-xyz").rest, ["Ab3-xyz"]);
  assert.deepEqual(Lib.parseRoute("#/artigo?ref=10.1038%2Fnature").params.get("ref"), "10.1038/nature");
});

test("parseRoute tolera percent-encoding quebrado sem lançar", () => {
  assert.doesNotThrow(() => Lib.parseRoute("#/lista/%E0%A4%A"));
  assert.equal(Lib.parseRoute("#/lista/%E0%A4%A").view, "lista");
});

test("buildHash omite valores vazios e codifica o resto", () => {
  assert.equal(Lib.buildHash("/busca", { q: "a b", yf: 2020, oa: "", lang: null, p: undefined, x: false }), "#/busca?q=a+b&yf=2020");
  assert.equal(Lib.buildHash("/biblioteca"), "#/biblioteca");
});

test("estado da busca: ida e volta pela URL", () => {
  const state = { q: "metformina", yearFrom: 2020, yearTo: 2024, types: ["Meta-análise", "Revisão"], oa: true, lang: "pt", sort: "cited", page: 3, source: "europepmc" };
  const hash = Lib.buildHash("/busca", Lib.paramsFromSearchState(state));
  assert.deepEqual(Lib.searchStateFromParams(Lib.parseRoute(hash).params), state);
});

test("estado da busca trata a URL como entrada não confiável", () => {
  const params = new URLSearchParams({ q: "x".repeat(900), yf: "1500", yt: "abc", types: ",,A, B ,,", lang: "xx", sort: "hack", p: "99999", fonte: "<script>" });
  const state = Lib.searchStateFromParams(params);
  assert.equal(state.q.length, 300);
  assert.equal(state.yearFrom, null);
  assert.equal(state.yearTo, null);
  assert.deepEqual(state.types, ["A", "B"]);
  assert.equal(state.lang, "");
  assert.equal(state.sort, "relevance");
  assert.equal(state.page, 500);
  assert.equal(state.source, "script");
  assert.deepEqual(Lib.searchStateFromParams(new URLSearchParams()), Lib.SEARCH_DEFAULTS);
  assert.equal(Lib.searchStateFromParams(new URLSearchParams({ p: "-4" })).page, 1);
});

test("parâmetros da API só incluem o que foi escolhido", () => {
  assert.equal(Lib.apiParamsFromSearchState(Lib.SEARCH_DEFAULTS).toString(), "per_page=10");
  const params = Lib.apiParamsFromSearchState({ ...Lib.SEARCH_DEFAULTS, q: "a b", oa: true, sort: "recent", page: 2, types: ["Revisão"], lang: "es", yearFrom: 2019 }, 5);
  assert.equal(params.get("q"), "a b");
  assert.equal(params.get("oa"), "true");
  assert.equal(params.get("sort"), "recent");
  assert.equal(params.get("page"), "2");
  assert.equal(params.get("types"), "Revisão");
  assert.equal(params.get("lang"), "es");
  assert.equal(params.get("yf"), "2019");
  assert.equal(params.get("per_page"), "5");
  assert.equal(params.has("yt"), false);
});

test("safeHttpUrl só aceita http e https", () => {
  assert.equal(Lib.safeHttpUrl("https://europepmc.org/articles/PMC1"), "https://europepmc.org/articles/PMC1");
  assert.equal(Lib.safeHttpUrl("http://exemplo.org/a"), "http://exemplo.org/a");
  for (const bad of ["javascript:alert(1)", "data:text/html,<script>", "ftp://x", "//evil.com", "", null, undefined, "not a url", "vbscript:x"]) {
    assert.equal(Lib.safeHttpUrl(bad), "", String(bad));
  }
});

test("formatCount usa separador pt-BR e tolera vazio", () => {
  assert.equal(Lib.formatCount(1234567).replace(/ /g, " "), "1.234.567");
  assert.equal(Lib.formatCount(null), "0");
});

test("pageWindow mostra primeira, última e vizinhas com reticências", () => {
  assert.deepEqual(Lib.pageWindow(1, 1), [1]);
  assert.deepEqual(Lib.pageWindow(1, 3), [1, 2, 3]);
  assert.deepEqual(Lib.pageWindow(5, 20), [1, "…", 4, 5, 6, "…", 20]);
  assert.deepEqual(Lib.pageWindow(2, 20), [1, 2, 3, "…", 20]);
  assert.deepEqual(Lib.pageWindow(20, 20), [1, "…", 19, 20]);
});

test("debounce agrupa chamadas e pode ser cancelado", async () => {
  const calls = [];
  const fn = Lib.debounce((x) => calls.push(x), 20);
  fn(1); fn(2); fn(3);
  await new Promise((r) => setTimeout(r, 60));
  assert.deepEqual(calls, [3]);
  fn(4); fn.cancel();
  await new Promise((r) => setTimeout(r, 60));
  assert.deepEqual(calls, [3]);
});

test("aiLabHref codifica a referência (DOI com barras e símbolos)", () => {
  assert.equal(Lib.aiLabHref("33984217"), "/ia?artigo=33984217#geral");
  assert.equal(Lib.aiLabHref("10.1038/s41586-021-03819-2", "medicina"), "/ia?artigo=10.1038%2Fs41586-021-03819-2#medicina");
  assert.ok(!Lib.aiLabHref("x&y=<z>").includes("<"));
});

test("feedArea escolhe a primeira area conhecida do item e cai em geral", () => {
  assert.equal(Lib.feedArea(["medicina", "biologia"]), "medicina");
  assert.equal(Lib.feedArea(["inexistente", "ambiente"]), "ambiente");
  assert.equal(Lib.feedArea([]), "geral");
  assert.equal(Lib.feedArea(undefined), "geral");
  assert.equal(Lib.FEED_AREAS.length, 14);
});

test("journeyProgress vira 0..1 conforme a seção alta passa pela tela", () => {
  // seção de 2680px numa tela de 812px: só rola 1868px com o palco fixo
  assert.equal(Lib.journeyProgress(100, 2680, 812), 0);      // ainda nao chegou
  assert.equal(Lib.journeyProgress(0, 2680, 812), 0);
  assert.equal(Lib.journeyProgress(-934, 2680, 812), 0.5);
  assert.equal(Lib.journeyProgress(-1868, 2680, 812), 1);
  assert.equal(Lib.journeyProgress(-5000, 2680, 812), 1);    // ja passou
  assert.equal(Lib.journeyProgress(-10, 500, 812), 0);       // seção menor que a tela: sem divisão por zero
});

test("journeyScene troca a cena em 34% e 67%", () => {
  assert.deepEqual([0, 0.33, 0.34, 0.5, 0.66, 0.67, 1].map(Lib.journeyScene), [1, 1, 2, 2, 2, 3, 3]);
});

test("countAt começa em zero, termina no valor e nunca passa dele", () => {
  assert.equal(Lib.countAt(51, 0), 0);
  assert.equal(Lib.countAt(51, 1), 51);
  assert.equal(Lib.countAt(51, 2), 51);
  assert.equal(Lib.countAt(51, -1), 0);
  assert.ok(Lib.countAt(100, 0.5) > 50);  // saída suave: passa da metade antes da metade do tempo
  const seq = [0, 0.2, 0.4, 0.6, 0.8, 1].map((k) => Lib.countAt(214, k));
  assert.deepEqual([...seq].sort((a, b) => a - b), seq);
});

test("stepsSummary conta os passos feitos e aponta o próximo", () => {
  const steps = [{ done: true, label: "A", href: "#a" }, { done: false, label: "B", href: "#b" }, { done: false, label: "C", href: "#c" }];
  assert.deepEqual(Lib.stepsSummary(steps), { done: 1, total: 3, percent: 33, next: steps[1] });
  assert.equal(Lib.stepsSummary(steps.map((s) => ({ ...s, done: true }))).next, null);
  assert.deepEqual(Lib.stepsSummary([]), { done: 0, total: 0, percent: 0, next: null });
});

test("scoreTone traduz a faixa da nota em tom visual", () => {
  assert.equal(Lib.scoreTone({ score: 90, band: "Alta" }), "high");
  assert.equal(Lib.scoreTone({ score: 60, band: "Moderada" }), "mid");
  assert.equal(Lib.scoreTone({ score: 30, band: "Baixa" }), "low");
  assert.equal(Lib.scoreTone({ score: 0, band: "Retratado" }), "bad");
  assert.equal(Lib.scoreTone({ score: null, band: "Indeterminada" }), "none");
  assert.equal(Lib.scoreTone(undefined), "none");
});

const LIB = [
  { ref: "1", title: "Metformina em idosos", authors: "Ana Souza", journal: "Revista Clínica", year: 2020, tags: ["TCC"], rating: { score: 60, band: "Moderada" }, savedAt: "2026-10-01T10:00:00" },
  { ref: "2", title: "Efeitos de dieta", authors: "João Álvares", journal: "Nutrição Hoje", year: 2024, tags: ["Saúde"], rating: { score: 90, band: "Alta" }, savedAt: "2026-10-03T10:00:00" },
  { ref: "3", title: "Aprendizagem de máquina", authors: "Lia Costa", journal: "Computação", year: null, tags: [], rating: { score: null, band: "Indeterminada" }, savedAt: "2026-10-02T10:00:00" },
];
const refs = (list) => list.map((item) => item.ref);

test("filterLibrary combina etiqueta e texto sem acento, todas as palavras", () => {
  assert.deepEqual(refs(Lib.filterLibrary(LIB, "", "")), ["1", "2", "3"]);
  assert.deepEqual(refs(Lib.filterLibrary(LIB, "", "TCC")), ["1"]);
  assert.deepEqual(refs(Lib.filterLibrary(LIB, "alvares", "")), ["2"]);          // autor com acento
  assert.deepEqual(refs(Lib.filterLibrary(LIB, "maquina aprendizagem", "")), ["3"]);
  assert.deepEqual(refs(Lib.filterLibrary(LIB, "nutricao", "")), ["2"]);          // revista
  assert.deepEqual(refs(Lib.filterLibrary(LIB, "saude", "")), ["2"]);             // etiqueta
  assert.deepEqual(refs(Lib.filterLibrary(LIB, "metformina dieta", "")), []);     // todas as palavras
  assert.deepEqual(refs(Lib.filterLibrary(LIB, "metformina", "Saúde")), []);
});

test("sortLibrary ordena sem mexer na lista original e manda o que não tem valor para o fim", () => {
  const before = refs(LIB);
  assert.deepEqual(refs(Lib.sortLibrary(LIB, "recentes")), ["2", "3", "1"]);
  assert.deepEqual(refs(Lib.sortLibrary(LIB, "nota")), ["2", "1", "3"]);
  assert.deepEqual(refs(Lib.sortLibrary(LIB, "ano")), ["2", "1", "3"]);
  assert.deepEqual(refs(Lib.sortLibrary(LIB, "titulo")), ["3", "2", "1"]);
  assert.deepEqual(refs(LIB), before);
  assert.deepEqual(Lib.LIBRARY_SORTS, ["recentes", "nota", "ano", "titulo"]);
});
