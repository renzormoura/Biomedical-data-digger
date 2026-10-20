# Integrações externas

Tudo o que o servidor consulta fora do próprio processo. Para termos de uso e licenças, ver [Licenças e termos das fontes](../legal/licencas-e-termos.md).

## Resumo
| Grupo | Serviços | Chave | Quando é chamado |
|---|---|---|---|
| Busca de artigos | Europe PMC, PubMed (NCBI), arXiv, DOAJ, OpenAIRE, OpenAlex (opcional) | Só OpenAlex (obrigatória) e NCBI (opcional) | A cada busca nova (cache de 10 min) |
| Resolução de artigo | Europe PMC, PubMed, OpenAlex, Crossref, Semantic Scholar, arXiv | Não | Ao abrir um artigo cuja obra não está em cache |
| Enriquecimento | ClinicalTrials.gov, OpenCitations, DataCite | Não | Página do artigo (cache por artigo) |
| Texto completo | Europe PMC (JATS) | Não | Quando a pessoa baixa o texto completo aberto |
| Feed | 51 feeds RSS/Atom públicos | Não | Atualização condicional a cada 3 h por fonte |
| IA | Groq (produção) e Ollama (local) | `GROQ_API_KEY` | Só no Laboratório de IA |
| Brasil | ANVISA, Conitec, Rename | Não | **Nunca em tempo de uso**: só nos scripts de atualização |

## Busca e resolução
| Serviço | Endereço base | Observações |
|---|---|---|
| Europe PMC | `ebi.ac.uk/europepmc/webservices/rest/` | Fonte padrão; busca, metadados oficiais (tipo de publicação, palavras-chave), texto completo aberto (JATS) |
| PubMed (NCBI E-utilities) | `eutils.ncbi.nlm.nih.gov/entrez/eutils/` | `esearch` + `efetch`; 3 req/s sem chave. `NCBI_API_KEY` opcional. XML lido por `xmlutil` |
| arXiv | `export.arxiv.org/api/query` | Atom/XML; preprints marcados como "Preprint" |
| DOAJ | `doaj.org/api/search/articles/` | Revistas de acesso aberto |
| OpenAIRE | `api.openaire.eu/graph/v1/researchProducts` | Pesquisa financiada; a mais lenta (até >20 s) |
| OpenAlex | `api.openalex.org/works` | **Só ativa com `OPENALEX_API_KEY`** (`OPENALEX_MAILTO` opcional) |
| Crossref | `api.crossref.org/works` | *Fallback* de resolução por DOI |
| Semantic Scholar | `api.semanticscholar.org/graph/v1/paper/` | *Fallback* de resolução |

**Resolução de links colados.** O resolvedor entende URLs de páginas de editoras e de resultados do Google Acadêmico colados pela pessoa e tenta extrair o DOI ou o título. Isso usa `security.safe_get` (proteção SSRF) e é um **recurso herdado** do início do projeto: não faz parte da busca e deve ser reavaliado do ponto de vista dos termos de uso antes do lançamento comercial.

## Enriquecimento
| Serviço | Uso |
|---|---|
| ClinicalTrials.gov (API v2) | Confirma registros NCT citados no resumo (título, status, fase) |
| OpenCitations (API v2) | Contagem de citações por DOI |
| DataCite | Dados, códigos e materiais ligados ao DOI (inclui Zenodo e figshare) |

Todos com prazo de 12 s, em paralelo, "melhor esforço": falha vira "sem dados".

## Feed
51 fontes em `feed_sources.py` (`id`, `url`, `site`, idioma, tipo, áreas). Distribuição: 35 em inglês e 16 em português; tipos: divulgação científica 18, instituição 9, jornal 9, revista 7, blog acadêmico 5, preprint 3. Cada busca usa `ETag`/`Last-Modified` (requisição condicional), identifica o robô e respeita o intervalo mínimo de 3 h por fonte. A lista completa e os critérios estão em [Feed](../features/feed.md). Conferência: `python scripts/verificar_feeds.py`.

## Modelos de linguagem
| Backend | Modelos | Uso |
|---|---|---|
| Groq | GPT-OSS 20B (padrão), GPT-OSS 120B, Qwen 3.6 27B, Qwen 3.8 27B | Produção |
| Ollama | Llama (local) | Desenvolvimento, sem chave |

`LLMRouter` escolhe o backend pelo nome do modelo e erros de provedor viram mensagens seguras. Detalhes em [Laboratório de IA](../features/analises-clinicas.md) e [ADR-001](../adrs/ADR-001-llm-backend.md).

## Dados do Brasil (somente atualização)
| Base | Arquivo de origem | Script |
|---|---|---|
| ANVISA | CSV de dados abertos (DATAVISA) | `scripts/atualizar_anvisa.py` |
| Conitec | Planilha Excel de recomendações | `scripts/atualizar_conitec.py` |
| Rename 2024 | PDF oficial do Ministério da Saúde | `scripts/atualizar_rename.py` |

Geram `dados_brasil/*.json`, que são versionados. Ver [Atualização dos dados do Brasil](../operacao/dados-brasil.md).

## Comportamento comum
- **Identificação:** requisições levam `User-Agent: Lastro/1.0`.
- **Prazos:** de 12 s (enriquecimento) a 25 s (PubMed, texto completo); busca combinada limitada a 8 s no total.
- **Falha:** cada serviço falha sozinho; a pessoa vê um aviso (busca) ou "sem dados" (enriquecimento). Erros nunca expõem URLs internas nem credenciais.
- **Cache:** busca 10 min, obra 1 h, enriquecimento por artigo; feed por fonte (3 h).
- **Dependências de disponibilidade:** a indisponibilidade de uma fonte reduz a variedade, não derruba o produto. A de **todas** as fontes de busca devolve a mensagem "Nenhuma fonte de artigos respondeu agora".
