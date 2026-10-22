# Funcionalidade: Biblioteca, etiquetas e listas de leitura

## Objetivo
Permitir que a pessoa guarde artigos, organize-os e leve-os para fora: a **biblioteca** pessoal, as **etiquetas**, as **listas de leitura** (que podem ser compartilhadas por link público somente leitura) e a **exportação** em vários formatos. Exige conta.

## O que a pessoa vê
- **Salvar:** botão em cada resultado e na página do artigo. O botão mostra se o artigo já está salvo.
- **Biblioteca** (`#/biblioteca`): quatro números no topo (artigos salvos, listas, relatórios e análises, com barra de uso quando a cobrança está ativa); os artigos em **cartões** (padrão) ou em **tabela** (a escolha fica guardada no navegador), cada um com o **anel da nota de confiabilidade**; **filtro por texto** (título, autor, revista e etiquetas, sem acento), **ordem** (salvos há pouco, maior nota, ano, título) e filtro por etiqueta; remoção; as **listas como estantes** (cartão com contador, selo "link ativo" e um leque de cartões); relatórios de tema e as análises do Laboratório de IA salvas.
- **Listas** (`#/lista/<id>`): conjuntos nomeados de artigos, com ordem. Cada lista pode ser compartilhada (gera `#/lista/<token>`) e desfeita a qualquer momento.
- **Relatório de tema:** a partir de uma lista, ver [Relatório de tema](relatorio-de-tema.md).
- **Exportar:** botão com os formatos abaixo.

## Como funciona
- Cada artigo salvo guarda um **retrato** dos metadados (`Work.to_dict`), de modo que a biblioteca abre sem consultar a fonte e sobrevive a mudanças nas APIs. O retrato do resumo é limitado a 4.000 caracteres.
- Toda operação confere o **dono** (e-mail da sessão). Contas diferentes nunca veem os dados umas das outras.
- **Listas compartilhadas:** o link usa um token aleatório (`secrets.token_urlsafe(9)`) e a rota pública `GET /api/shared/{token}` devolve só o nome da lista e os artigos, **sem expor o e-mail do dono**. A rota tem limitador por identidade contra tentativas de adivinhar tokens. Descompartilhar invalida o token.
- Etiquetas são normalizadas (tamanho e quantidade limitados).
- Artigos salvos alimentam o vigia de retratação do [sininho](notificacoes.md).

### Limites por conta
| Item | Limite |
|---|---:|
| Artigos na biblioteca | 500 |
| Listas | 50 |
| Artigos por lista | 200 |
| Etiquetas por artigo | 12 (30 caracteres cada) |
| Nome de lista | 80 caracteres |
| Análises do Laboratório salvas | 200 (60.000 caracteres cada) |

Ao atingir um limite, a API responde com mensagem clara (`LimitReachedError`).

## Exportação
`GET /api/library/export?format=...` (da biblioteca toda ou de uma lista):

| Formato | Arquivo | Uso |
|---|---|---|
| BibTeX | biblioteca.bib | LaTeX, Zotero, Mendeley |
| RIS | biblioteca.ris | Zotero, Mendeley, EndNote |
| EndNote (refer) | biblioteca.enw | EndNote |
| CSL JSON | biblioteca-csl.json | Zotero e processadores CSL |
| ABNT, APA, Vancouver, IEEE, Harvard, MLA | referencias-*.txt | Texto pronto para colar |
| CSV | biblioteca.csv | Planilhas |
| JSON | biblioteca.json | Integrações e cópia de segurança |
| Resumos (Markdown) | resumos.md | Leitura offline |

A referência de **um** artigo (`GET /api/discover/cite`) é pública e não exige conta. Detalhes em [Citações e exportação](citacoes-exportacao.md).

## Privacidade
- Os dados ficam nas tabelas `library_items`, `reading_lists`, `reading_list_items` e `saved_analyses` (ver [Modelo de dados](../arquitetura/dados.md)).
- A pessoa pode baixar todos os dados da conta e excluir a conta, o que apaga também biblioteca e listas (ver [Conta e sessões](conta-e-sessoes.md)).

## Arquivos
`library_store.py`, `exports.py`, `browse_api.py`, `static/browse.js`. Testes: `tests/test_library_store.py`, `tests/test_exports.py`, `tests/test_reference_export.py`, `tests/test_browse_api.py`.
