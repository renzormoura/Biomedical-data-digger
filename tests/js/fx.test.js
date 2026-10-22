"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");

const Fx = require("../../nexus-science/static/fx.js");

const COMMANDS = [
  { id: "search", label: "Buscar artigos", keys: ["pesquisar"] },
  { id: "feed", label: "Abrir o feed de novidades", keys: ["noticias"] },
  { id: "library", label: "Minha biblioteca", keys: ["salvos", "listas"] },
  { id: "reports", label: "Relatórios de tema", keys: ["documento"] },
  { id: "plans", label: "Ver planos", keys: ["assinatura", "pix"] },
  { id: "theme", label: "Alternar tema claro ou escuro", keys: ["escuro"] },
];
const ids = (list) => list.map((c) => c.id);

test("fold tira acento e caixa", () => {
  assert.equal(Fx.fold("  Relatórios DE Tema "), "relatorios de tema");
  assert.equal(Fx.fold(undefined), "");
});

test("filterCommands sem consulta devolve tudo, em cópia", () => {
  const all = Fx.filterCommands(COMMANDS, "");
  assert.deepEqual(ids(all), ids(COMMANDS));
  assert.notEqual(all, COMMANDS);
});

test("filterCommands ignora acento e acha por início de palavra, trecho e palavra-chave", () => {
  assert.deepEqual(ids(Fx.filterCommands(COMMANDS, "relatorio")), ["reports"]);
  assert.deepEqual(ids(Fx.filterCommands(COMMANDS, "BIBLIO")), ["library"]);
  assert.deepEqual(ids(Fx.filterCommands(COMMANDS, "noticias")), ["feed"]);   // so pela palavra-chave
  assert.deepEqual(ids(Fx.filterCommands(COMMANDS, "pix")), ["plans"]);
  assert.deepEqual(ids(Fx.filterCommands(COMMANDS, "xyzzy")), []);
});

test("filterCommands põe o começo do rótulo antes do trecho no meio", () => {
  // "tema" começa "Alternar tema..."? não: começa a palavra "tema" em dois rótulos; o primeiro na ordem original vem antes
  assert.deepEqual(ids(Fx.filterCommands(COMMANDS, "tema")), ["reports", "theme"]);
  assert.deepEqual(ids(Fx.filterCommands(COMMANDS, "buscar")), ["search"]);
  const withPrefix = [{ id: "mid", label: "Todos os artigos", keys: [] }, { id: "start", label: "Artigos salvos", keys: [] }];
  assert.deepEqual(ids(Fx.filterCommands(withPrefix, "artigos")), ["start", "mid"]);
});

test("paletteItems acrescenta a busca livre quando há texto com 2 letras ou mais", () => {
  const href = (text) => `#/busca?q=${encodeURIComponent(text)}`;
  assert.equal(Fx.paletteItems(COMMANDS, "", href).length, COMMANDS.length);
  assert.equal(Fx.paletteItems(COMMANDS, "a", href).some((i) => i.id === "search-text"), false);
  const items = Fx.paletteItems(COMMANDS, "diabetes tipo 2", href);
  assert.deepEqual(ids(items), ["search-text"]);
  assert.equal(items[0].href, "#/busca?q=diabetes%20tipo%202");
  assert.match(items[0].label, /diabetes tipo 2/);
});

test("moveIndex dá a volta nas pontas e aguenta lista vazia", () => {
  assert.equal(Fx.moveIndex(0, 1, 3), 1);
  assert.equal(Fx.moveIndex(2, 1, 3), 0);
  assert.equal(Fx.moveIndex(0, -1, 3), 2);
  assert.equal(Fx.moveIndex(0, 1, 0), 0);
});
