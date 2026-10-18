# Feature: Citações e exportação para gerenciadores de referências

## Objetivo
Levar um artigo, uma lista ou a biblioteca inteira para o Zotero, Mendeley ou EndNote, e gerar a citação pronta nos estilos mais usados. Tudo é feito por código a partir dos metadados do registro, sem IA e sem gastar token.

## Onde está
- **Página do artigo, seção "Citar":** botões de estilo (ABNT, APA, Vancouver, IEEE, Harvard, MLA) com "Copiar", e o bloco "Levar para o gerenciador de referências", com download em RIS, EndNote (.enw), CSL JSON e BibTeX, além de "Copiar BibTeX". Não exige conta.
- **Biblioteca e listas (exigem conta):** um botão **Exportar** na biblioteca e outro em cada lista, com um menu agrupado (gerenciadores de referências; citações prontas; planilha e dados), com os mesmos formatos mais CSV, JSON e resumos.
- **Conector do navegador:** a página do artigo publica os metadados no padrão `citation_*` (título, autores, revista, volume, número, páginas, DOI, PMID, data, idioma e palavras-chave) no `<head>`. O conector do Zotero (e o do Mendeley) captura o artigo direto pelo botão da extensão. As tags são criadas ao abrir o artigo e removidas ao sair dele.

## Formatos

| Formato | Arquivo | Importa em |
|---|---|---|
| RIS | `.ris` | Zotero, Mendeley, EndNote (Arquivo, Importar) |
| EndNote (Refer) | `.enw` | EndNote, filtro "EndNote Import" |
| CSL JSON | `.json` | Zotero, Pandoc e a maioria dos gerenciadores |
| BibTeX | `.bib` | LaTeX, Zotero, Mendeley, Overleaf |
| ABNT, APA, Vancouver, IEEE, Harvard, MLA | `.txt` | Texto pronto para colar |
| CSV, JSON, Resumos (MD) | | Só pela biblioteca e listas |

Os campos exportados são título, autores, revista, ano (e data completa quando a fonte informa), volume, número, páginas, DOI, URL (DOI ou PubMed), PMID, idioma, palavras-chave e, em RIS, EndNote e CSL JSON, o resumo (em uma linha, para não quebrar a importação).

## API
- `GET /api/discover/cite?ref=&format=` baixa a referência de **um** artigo (público). Aceita `ris`, `endnote`, `csljson`, `bibtex` e os estilos de texto (`abnt`, `apa`, `vancouver`, `ieee`, `harvard`, `mla`); recusa `csv`, `json` e `resumos` (400).
- `GET /api/library/export?format=&list_id=` exporta a biblioteca ou uma lista (exige conta).

## Código
`citations.py` (estilos de citação, funções puras), `exports.py` (formatos de arquivo e o registro `EXPORT_FORMATS`), `browse_api.py` (rotas) e `static/browse.js` (seção Citar, biblioteca e tags `citation_*`).

## Limites
- Todo registro é tratado como artigo de periódico (`Journal Article`/`article-journal`). Preprints e artigos do arXiv saem com o tipo de artigo e a revista "arXiv (preprint)".
- As citações dependem da qualidade do que a fonte informa: autor sem prenome vira só o sobrenome, e páginas ausentes são omitidas.
- ABNT, APA e os demais estilos seguem as regras gerais; conferir com a norma da instituição em trabalhos formais.
- A captura pelo conector depende da extensão instalada e da versão dela; o download dos arquivos funciona sem ela.

## Testes
`tests/test_reference_export.py` (estilos, EndNote, CSL JSON, RIS e BibTeX, rota de um artigo e exportação da biblioteca) e `tests/test_exports.py`, `tests/test_citations.py` (formatos anteriores).
