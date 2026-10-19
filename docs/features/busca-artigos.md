# Funcionalidade: Busca em várias fontes

## Objetivo
Permitir que a pessoa pesquise um tema, um título, um DOI ou uma palavra-chave **sem depender de uma única base**. A busca consulta várias fontes abertas em paralelo, remove repetidos e devolve uma lista única com filtros, ordenação e paginação.

## O que a pessoa vê
- Campo de busca no topo e na página inicial, com seletor de **fonte** (padrão: "Todas as fontes").
- Filtros: ano de publicação (de/até), tipo de estudo, somente acesso aberto e idioma (português, inglês, espanhol).
- Ordenação: **Relevância**, **Mais recentes** ou **Mais citados**.
- Cada resultado mostra título (link para a página do artigo), autores, periódico e ano, selos (tipo de estudo, acesso aberto, idioma, fonte, retratado), trecho do resumo com os termos buscados destacados e os botões **Salvar** e **Abrir**.
- Avisos quando uma fonte demorou ou não respondeu ("OpenAIRE demorou demais e ficou de fora desta busca").
- Acima da lista, o [Panorama do tema](panorama-do-tema.md).
- No celular, os resultados são compactos (≈2,5 por tela) e os filtros ficam numa gaveta.

A URL guarda a busca (`#/busca?q=...&yf=...&types=...`), então ela pode ser compartilhada e o botão voltar funciona.

## Fontes
| Fonte | Cobertura | Tipos de estudo | Observações |
|---|---|---|---|
| Europe PMC | Ciências da vida, incluindo preprints | Filtro oficial por tipo de publicação (ensaio randomizado, meta-análise, revisão sistemática, revisão, relato de caso, observacional, multicêntrico, diretriz) | Também resolve PMID, PMCID e DOI; fonte padrão quando só há uma |
| PubMed (NCBI E-utilities) | MEDLINE direto da fonte oficial | Mesmo conjunto de filtros | Duas chamadas por busca (esearch + efetch). Sem chave: 3 req/s; `NCBI_API_KEY` eleva o limite |
| arXiv | Computação, IA, física, matemática | Todos entram como "Preprint" | Sem filtro de tipo de estudo |
| DOAJ | Revistas de acesso aberto de todas as áreas | Não informa | Sem chave |
| OpenAIRE | Pesquisa financiada, com ligação a dados e projetos | Não informa | Sem chave; é a fonte mais lenta |
| OpenAlex | Todas as áreas | Tipo da obra (artigo, revisão, preprint), mais grosseiro | **Opcional:** só entra com `OPENALEX_API_KEY`, pois sem chave o orçamento diário é minúsculo |

## Como funciona

### Uma fonte
`DiscoveryService.search` escolhe o catálogo, aplica o limitador de taxa (30 buscas por minuto por identidade, configurável em `DISCOVERY_CALLS_PER_MINUTE`; acertos de cache não gastam o limite) e guarda o resultado em cache por 10 minutos (`SEARCH_CACHE_TTL = 600`). Cada obra encontrada também entra no cache de obras (1 hora), para a página do artigo reaproveitar o que a busca já trouxe.

### Todas as fontes (padrão com mais de uma fonte)
1. Cada fonte recebe uma fatia da página: `ceil(por_página / nº de fontes)`, no mínimo 2.
2. As fontes rodam **em paralelo** (um `ThreadPoolExecutor`). Quem não oferece o tipo de estudo pedido é pulada, com aviso.
3. **Prazo:** o servidor espera no máximo 8 s (`ALL_DEADLINE`). Assim que 3 fontes respondem (`READY_SOURCES`), as demais ganham só mais 1,5 s (`ALL_GRACE`). A fonte lenta fica de fora com um aviso, mas termina em segundo plano e deixa o resultado no cache para a próxima busca. Medição local: de ≈14 s para 1–3 s.
4. **Junção** (`_merge`): intercala os resultados por posição (respeitando a relevância de cada fonte) ou ordena por citações/ano; **remove repetidos** por DOI, PMID ou título normalizado (≥25 caracteres), ficando com o registro mais rico (o que tem resumo e tipo de estudo oficial).
5. O total é a soma dos totais de cada fonte (aproximado: o mesmo artigo pode estar em várias).
6. A busca só falha se **todas** as fontes falharem; falhas parciais viram avisos.

### Identificadores
A página do artigo (`#/artigo?ref=`) aceita PMID, PMCID, DOI, ID do arXiv e ID do OpenAlex. Se nenhum catálogo resolver, um *fallback* (Crossref, Semantic Scholar, arXiv) tenta devolver ao menos título e resumo.

## Limites
- Os totais são aproximados e a paginação em "Todas as fontes" combina fatias, então páginas profundas são menos precisas que em uma fonte só.
- Filtros de tipo de estudo só existem onde a fonte informa o delineamento (Europe PMC e PubMed).
- Fontes públicas mudam: a lentidão ou a queda de uma delas não derruba a busca, mas reduz a variedade.

## API
`GET /api/discover/options`, `GET /api/discover/search` e `GET /api/discover/panorama`. Ver [Referência da API](../api/referencia.md).

## Arquivos
`discovery.py` (orquestração, junção, cache), `catalog.py` (modelo `Work`, `SearchQuery`), `europepmc_catalog.py`, `pubmed_catalog.py`, `arxiv_catalog.py`, `doaj_catalog.py`, `openaire_catalog.py`, `openalex_catalog.py`, `ratelimit.py`, `cache.py`, `static/browse.js`.
Testes: `tests/test_discovery.py`, `tests/test_more_sources.py`, `tests/test_europepmc_catalog.py`, `tests/test_openalex_catalog.py`, `tests/test_browse_api.py`.

> O antigo índice de relevância bibliográfica (citações, atualidade, metadados) foi substituído pela [nota de confiabilidade](confiabilidade.md) e pelo ordenador por fonte.
