"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");

require("../data.js");
const Nav = require("../lib.js");

const DATA = globalThis.NAV_DATA;
const byId = (id) => DATA.find((a) => a.id === id);

// ------------------------------------------------------------------ integridade dos dados fictícios
test("dados: ids únicos, campos obrigatórios e marcação de exemplo", () => {
  assert.equal(new Set(DATA.map((a) => a.id)).size, DATA.length);
  for (const a of DATA) {
    for (const field of ["id", "title", "journal", "abstract", "area", "type", "lang", "source"]) assert.ok(a[field], `${a.id}.${field}`);
    assert.ok(a.authors.length > 0 && a.keywords.length > 0 && Number.isInteger(a.year) && a.year >= 2015);
    assert.match(a.title, /\((exemplo|example|ejemplo)\)/i, `${a.id} deve se declarar exemplo`);
    assert.ok(a.doi.startsWith("10.0000/exemplo."), `${a.id} DOI fictício`);
    assert.ok(["pt", "en", "es"].includes(a.lang));
  }
});

test("dados: há variedade de áreas, tipos, idiomas e de acesso aberto", () => {
  assert.ok(new Set(DATA.map((a) => a.area)).size >= 6);
  assert.ok(new Set(DATA.map((a) => a.type)).size >= 8);
  assert.deepEqual([...new Set(DATA.map((a) => a.lang))].sort(), ["en", "es", "pt"]);
  assert.ok(DATA.some((a) => a.oa) && DATA.some((a) => !a.oa));
});

// ------------------------------------------------------------------ busca
test("normalize e tokenize ignoram acentos, caixa e termos de 1 letra", () => {
  assert.equal(Nav.normalize("Hipertensão ÁREA"), "hipertensao area");
  assert.deepEqual(Nav.tokenize("Diabetes, tipo 2 & a"), ["diabetes", "tipo"]);
  assert.deepEqual(Nav.tokenize("  "), []);
});

test("busca é AND, sem acento e retorna os termos usados", () => {
  const r = Nav.search(DATA, { q: "hipertensao exercicio" });
  assert.deepEqual(r.results.map((a) => a.id), ["d001"]);
  assert.deepEqual(r.terms, ["hipertensao", "exercicio"]);
  assert.equal(Nav.search(DATA, { q: "hipertensao dragoes" }).total, 0);
});

test("título pesa mais que resumo na relevância", () => {
  const r = Nav.search(DATA, { q: "metformin" }).results;
  assert.ok(r[0].title.toLowerCase().includes("metformin"));
  assert.ok(r[0]._score > 5);
});

test("sem consulta lista tudo; relevância cai para mais citados", () => {
  const r = Nav.search(DATA, {});
  assert.equal(r.total, DATA.length);
  assert.deepEqual(r.results.map((a) => a.citations), [...r.results.map((a) => a.citations)].sort((a, b) => b - a));
});

test("filtros: ano, tipo, acesso aberto, área e idioma combinam", () => {
  assert.ok(Nav.search(DATA, { yearFrom: 2023 }).results.every((a) => a.year >= 2023));
  assert.ok(Nav.search(DATA, { yearTo: 2019 }).results.every((a) => a.year <= 2019));
  assert.deepEqual(new Set(Nav.search(DATA, { types: ["Meta-análise", "Revisão sistemática"] }).results.map((a) => a.type)),
    new Set(["Meta-análise", "Revisão sistemática"]));
  assert.ok(Nav.search(DATA, { oaOnly: true }).results.every((a) => a.oa));
  assert.ok(Nav.search(DATA, { area: "Ambiental" }).results.every((a) => a.area === "Ambiental"));
  assert.equal(Nav.search(DATA, { area: "Todas" }).total, DATA.length);
  assert.ok(Nav.search(DATA, { lang: "es" }).results.every((a) => a.lang === "es"));
  const combined = Nav.search(DATA, { area: "Medicina", oaOnly: true, yearFrom: 2020, lang: "en" }).results;
  assert.deepEqual(combined.map((a) => a.id), ["d012"]);
});

test("ordenação por recentes e por citados; ordem inválida usa relevância", () => {
  const recent = Nav.search(DATA, { sort: "recentes" }).results.map((a) => a.year);
  assert.deepEqual(recent, [...recent].sort((a, b) => b - a));
  const cited = Nav.search(DATA, { sort: "citados" }).results.map((a) => a.citations);
  assert.deepEqual(cited, [...cited].sort((a, b) => b - a));
  assert.deepEqual(Nav.search(DATA, { sort: "xyz" }).results.map((a) => a.id), Nav.search(DATA, {}).results.map((a) => a.id));
});

test("facetas contam por consulta", () => {
  const f = Nav.facets(DATA, "");
  assert.equal(Object.values(f.area).reduce((s, n) => s + n, 0), DATA.length);
  assert.equal(f.oa, DATA.filter((a) => a.oa).length);
  assert.ok(Nav.facets(DATA, "metformin").area.Medicina >= 1 && !Nav.facets(DATA, "metformin").area.Ambiental);
});

test("destaque preserva o texto original e marca os termos sem acento", () => {
  const text = "Hipertensão e Exercício físico";
  const parts = Nav.splitHighlight(text, ["hipertensao", "exercicio"]);
  assert.equal(parts.map((p) => p.text).join(""), text);
  assert.deepEqual(parts.filter((p) => p.hit).map((p) => p.text), ["Hipertensão", "Exercício"]);
  assert.deepEqual(Nav.splitHighlight(text, []), [{ text, hit: false }]);
});

test("artigos semelhantes: sem o próprio, por palavras-chave em comum", () => {
  const near = Nav.similar(DATA, byId("d002"), 3);
  assert.ok(near.length > 0 && near.every((a) => a.id !== "d002"));
  // sem palavras-chave em comum, desempata por mesma área e depois por mais citações
  assert.equal(Nav.similar(DATA, byId("d012"), 1)[0].id, "d002");
  const shared = Nav.similar(DATA, { ...byId("d012"), id: "novo", keywords: ["biochar"] }, 1);
  assert.equal(shared[0].id, "d006");
});

// ------------------------------------------------------------------ extração sem IA
test("seções: rótulos com dois-pontos, texto copiado e dentro do resumo", () => {
  const sections = Nav.splitSections(byId("d001").abstract);
  assert.deepEqual(sections.map((s) => s.heading), ["Contexto", "Métodos", "Resultados", "Conclusões"]);
  for (const s of sections) assert.ok(byId("d001").abstract.includes(s.text));
});

test("seções: rótulos com ponto em espanhol exigem 3 rótulos", () => {
  const sections = Nav.splitSections(byId("d003").abstract);
  assert.deepEqual(sections.map((s) => s.heading), ["Objetivo", "Métodos", "Resultados", "Conclusões"]);
  assert.deepEqual(Nav.splitSections("Objetivo. Avaliar o efeito. Resultados. Houve melhora clínica."), []);
});

test("seções: resumo sem estrutura devolve vazio", () => {
  assert.deepEqual(Nav.splitSections(byId("d007").abstract), []);
  assert.deepEqual(Nav.splitSections(byId("d013").abstract), []);
  assert.deepEqual(Nav.splitSections(""), []);
});

test("números: frases originais com os tipos de dado", () => {
  const f = Nav.findings(byId("d001").abstract);
  const tags = new Set(f.flatMap((x) => x.tags));
  for (const tag of ["tamanho da amostra", "intervalo de confiança", "valor de p", "percentual"]) assert.ok(tags.has(tag), tag);
  for (const x of f) assert.ok(byId("d001").abstract.includes(x.sentence));
});

test("números: IC95% em espanhol e rótulo do IC não vira percentual", () => {
  const sentence = Nav.findings(byId("d003").abstract).find((x) => x.sentence.includes("OR 3,4"));
  assert.ok(sentence.tags.includes("medida de efeito") && sentence.tags.includes("intervalo de confiança"));
  assert.ok(!sentence.tags.includes("percentual"));
});

test("números: resumo sem estatística não gera achados", () => {
  assert.deepEqual(Nav.findings("Metformina é muito usada. Novos estudos são necessários."), []);
});

// ------------------------------------------------------------------ citações
test("citações: ABNT, APA e Vancouver do artigo d001", () => {
  const a = byId("d001");
  assert.equal(Nav.citations.ABNT(a),
    "MORAES TEIXEIRA, H.; BASTOS, R.; LEMOS, P. C. Efeito do exercício supervisionado sobre a pressão arterial de adultos com hipertensão leve: ensaio clínico randomizado (exemplo). Revista Exemplo de Cardiologia, v. 41, n. 2, p. 112-124, 2023. DOI: 10.0000/exemplo.001.");
  assert.equal(Nav.citations.APA(a),
    "Moraes Teixeira, H., Bastos, R., & Lemos, P. C. (2023). Efeito do exercício supervisionado sobre a pressão arterial de adultos com hipertensão leve: ensaio clínico randomizado (exemplo). Revista Exemplo de Cardiologia, 41(2), 112–124. https://doi.org/10.0000/exemplo.001");
  assert.equal(Nav.citations.Vancouver(a),
    "Moraes Teixeira H, Bastos R, Lemos PC. Efeito do exercício supervisionado sobre a pressão arterial de adultos com hipertensão leve: ensaio clínico randomizado (exemplo). Revista Exemplo de Cardiologia. 2023;41(2):112-124. doi:10.0000/exemplo.001");
});

test("citações: mais de 3 autores vira et al. na ABNT e campos ausentes são omitidos", () => {
  assert.match(Nav.citations.ABNT(byId("d012")), /^WEBER, A\. et al\. /);
  const preprint = Nav.citations.ABNT(byId("d007"));
  assert.ok(!preprint.includes("v. ") && !preprint.includes("p. ") && !preprint.includes("undefined"));
});

// ------------------------------------------------------------------ exportação
test("BibTeX: chaves únicas, campos e escape", () => {
  const dup = [byId("d001"), { ...byId("d001"), id: "copy", title: "Estudo A & B 100% (exemplo)" }];
  const bib = Nav.toBibtex(dup);
  const keys = [...bib.matchAll(/@article\{([^,]+),/g)].map((m) => m[1]);
  assert.equal(new Set(keys).size, 2);
  assert.match(bib, /author = \{Moraes Teixeira, Helena and Bastos, Ricardo and Lemos, Paula Cristina\}/);
  assert.match(bib, /pages = \{112--124\}/);
  assert.match(bib, /A \\& B 100\\%/);
});

test("BibTeX: preprint sem volume não gera campo vazio", () => {
  const bib = Nav.toBibtex([byId("d007")]);
  assert.ok(!bib.includes("volume") && !bib.includes("pages"));
});

test("RIS: tipo, autores, páginas separadas, palavras-chave e terminador", () => {
  const ris = Nav.toRis([byId("d001"), byId("d002")]);
  assert.equal((ris.match(/^TY {2}- JOUR$/gm) || []).length, 2);
  assert.equal((ris.match(/^ER {2}- $/gm) || []).length, 2);
  assert.match(ris, /^SP {2}- 112$/m);
  assert.match(ris, /^EP {2}- 124$/m);
  assert.match(ris, /^KW {2}- hipertensão$/m);
});

// ------------------------------------------------------------------ listas
test("lista: codifica e decodifica com ida e volta", () => {
  const encoded = Nav.encodeList("Saúde Pública & Epidemiologia", ["d003", "d004"]);
  const decoded = Nav.decodeList(encoded, DATA.map((a) => a.id));
  assert.deepEqual(decoded, { name: "Saúde Pública & Epidemiologia", ids: ["d003", "d004"] });
});

test("lista: a URL é entrada não confiável (ids desconhecidos, duplicados, nome longo e controle)", () => {
  const known = DATA.map((a) => a.id);
  const hostile = new URLSearchParams({ nome: `<img src=x onerror=alert(1)>\u0000${"x".repeat(500)}`, ids: "d001,d001,../etc,<script>,d999,d002" });
  const decoded = Nav.decodeList(hostile.toString(), known);
  assert.deepEqual(decoded.ids, ["d001", "d002"]);
  assert.ok(decoded.name.length <= Nav.MAX_LIST_NAME && !decoded.name.includes("\u0000"));
  assert.deepEqual(Nav.decodeList("", known), { name: "Lista sem nome", ids: [] });
});

// ------------------------------------------------------------------ modo teste
test("resumo de eventos conta ações e salvamentos líquidos", () => {
  const events = [{ type: "search" }, { type: "save" }, { type: "save" }, { type: "unsave" }, { type: "save" }, { type: "cite" }];
  assert.deepEqual(Nav.summarizeEvents(events), { counts: { search: 1, save: 3, unsave: 1, cite: 1 }, netSaved: 2, total: 6 });
  assert.deepEqual(Nav.summarizeEvents([]), { counts: {}, netSaved: 0, total: 0 });
});
