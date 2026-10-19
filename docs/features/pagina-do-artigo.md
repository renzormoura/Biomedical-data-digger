# Funcionalidade: Página do artigo, enriquecimento e downloads

## Objetivo
Dar a quem abriu um artigo tudo o que dá para saber **sem IA e sem sair do produto**: o resumo organizado, os números com a origem, a nota de confiabilidade, ligações a ensaios, citações e dados, artigos parecidos, a situação no Brasil (opcional) e documentos para baixar.

## O que a pessoa vê
Em `#/artigo?ref=<identificador>`:
1. **Cabeçalho:** título, autores, periódico, ano, selos (tipo de estudo, acesso aberto, retratado, idioma, fonte), identificadores (DOI, PMID, PMCID) com link, botões **Salvar na biblioteca**, **Adicionar a uma lista**, **Citar** e **Baixar**.
2. **Resumo por seções:** o resumo original dividido nas seções que o autor escreveu (Contexto, Métodos, Resultados, Conclusão…), com rótulos padronizados quando o registro os traz.
3. **Números e estatísticas:** as frases do resumo que contêm dado estatístico (amostra, medida de efeito, IC, valor de p, percentual), com a etiqueta do tipo de dado. São **cópias exatas**, nunca reescritas.
4. **Nota de confiabilidade** com os 8 critérios (ver [Nota de confiabilidade](confiabilidade.md)).
5. **Registros abertos** (carregados à parte, sem travar a página): ensaios clínicos citados, contagem de citações e dados/códigos relacionados.
6. **Situação no Brasil** (só com o pacote Saúde no Brasil ativo): ver [Saúde no Brasil](saude-no-brasil.md).
7. **Artigos semelhantes:** até 6 estudos parecidos, carregados depois.
8. **Citações:** o artigo formatado em ABNT, APA, Vancouver, IEEE, Harvard e MLA, com cópia em um clique.

## Como funciona
- **Resolução** (`DiscoveryService.work`): olha o cache de obras (1 h); depois consulta os catálogos na ordem; por fim usa o *fallback* (Crossref/Semantic Scholar/arXiv) para obter ao menos título e resumo. O limitador de taxa vale para consultas novas.
- **Análise** (`_analyze`): divide o resumo em seções (`split_sections`), extrai os achados (`extract_findings`), calcula a nota (`reliability.assess`) e formata as citações (`citations.format_citation`). Tudo determinístico.
- **Enriquecimento** (`Enricher`, `GET /api/discover/enrichment`): consulta em paralelo, com prazo de 12 s por chamada e cache por artigo:
  - **ClinicalTrials.gov** (API v2): confirma os números de registro (NCT) citados no resumo e traz título, status e fase;
  - **OpenCitations**: contagem de citações por DOI;
  - **DataCite** (cobre Zenodo, figshare e outros): dados, códigos e materiais ligados ao DOI.
  Cada fonte falha sozinha e vira "sem dados"; nenhuma derruba a página.
- **Semelhantes** (`similar` / `GET /api/discover/similar`): extrai até 4 termos (palavras-chave do registro, sem termos genéricos como "Humans" ou "Male", ou as palavras mais longas do título), busca por relevância na **mesma fonte** do artigo e remove o próprio artigo. Falhas viram lista vazia.
- **Ficha curta** (`GET /api/discover/brief`): cartão resumido usado pelo Laboratório de IA.

## Downloads
O menu (`GET /api/discover/downloads`) oferece, conforme o que existe:

| Documento | Conteúdo | Formatos |
|---|---|---|
| Apenas o resumo | Título, autores, identificação e resumo com as seções originais | txt, md, html, docx, json |
| Ficha de leitura | Resumo, números com a frase de origem, nota explicada, registro e dados, citações | txt, md, html, docx, json |
| Só a referência | Referência para o gerenciador | BibTeX, RIS, ABNT, APA, Vancouver |
| Texto completo (acesso aberto) | Texto integral com seções e referências, **da Europe PMC e só quando o artigo é aberto**; mostra a licença | txt, md, html, docx, xml (JATS original) |

Além disso, o menu lista links abertos informados pela fonte (versão aberta, PDF na Europe PMC, página do editor via DOI). **PDFs de editoras nunca passam pelo servidor**: o produto apenas leva a pessoa ao link. O texto completo é limitado a 15 MB.

Os documentos são montados em memória a partir de blocos simples (título, metadados, seções, parágrafos, citações), sem dependências externas; o DOCX é gerado diretamente (ZIP/XML).

## Limites
- Sem resumo na fonte, a página mostra só os dados do registro e a nota avisa.
- O enriquecimento é "melhor esforço": serviços externos podem estar fora do ar.
- Artigos semelhantes dependem de termos do registro; sem palavras-chave e com título curto, podem vir poucos.
- O texto completo só existe para artigos abertos com PMCID na Europe PMC.

## Arquivos
`discovery.py`, `extraction.py`, `reliability.py`, `citations.py`, `enrichment.py`, `downloads.py`, `exports.py`, `browse_api.py`, `static/browse.js`. Testes: `tests/test_discovery.py`, `tests/test_downloads.py`, `tests/test_extraction.py`, `tests/test_source_fetchers.py`.
