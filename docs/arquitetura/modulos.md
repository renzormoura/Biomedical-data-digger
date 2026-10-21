# Catálogo de módulos

Código em `nexus-science/` (Python, plano). Os módulos não têm estado global além de caches e limitadores em memória, criados em `nexus_science.py`.

## Entrada e web
| Módulo | Responsabilidade |
|---|---|
| `nexus_science.py` | Ponto de entrada: monta as dependências (catálogos, stores, serviços), carrega as bases do Brasil e sobe o `uvicorn` na porta `PORT` (padrão 7860) |
| `web.py` | Fábrica da aplicação FastAPI: sessão por cookie, identidade, páginas e autenticação; instala o endurecimento HTTP e registra os grupos de rotas |
| `browse_api.py` | Monta o `ApiContext` e registra os grupos de rotas do navegador de artigos, na ordem de sempre |
| `routes/` | Rotas por domínio, cada uma com `register_<domínio>_routes(app, ctx)`: `discover` (busca, obra, semelhantes, enriquecimento, downloads, Brasil, panorama), `analyses`, `profile`, `feed`, `reports`, `watch` (interesses, alertas, notificações, rotina agendada), `library` (biblioteca, listas, compartilhamento) `recovery` (recuperação de senha e confirmação de e-mail), `legal` (textos legais), `billing` (planos e Pix do lado da pessoa) e `admin` (painel de administração) e `lab` (Laboratório de IA, consumo). Também `context.py` (dependências), `schemas.py` (modelos de entrada), `payloads.py` (JSON de resposta) e `hardening.py` (cabeçalhos de segurança, checagem de origem e tratamento de erros) |
| `timeutil.py` | Relógio UTC e formato ISO únicos |
| `account_routes.py` | Resumo da conta, troca de senha, exportação de dados e exclusão (LGPD) |
| `config.py` | `Settings` lidas do ambiente, com validação em um só lugar |
| `domain.py` | Exceções de domínio com mensagem segura (`NexusError`, `RateLimitedError`, `NotFoundError`…) e tipos que circulam entre camadas |

## Descoberta e artigo
| Módulo | Responsabilidade |
|---|---|
| `catalog.py` | Modelo de domínio: `Work` (artigo), `SearchQuery`, `SearchResult`, interface `Catalog` |
| `discovery.py` | `DiscoveryService`: busca em uma ou todas as fontes (paralelo, prazo, junção, dedupe), obra com *fallback*, semelhantes, enriquecimento, texto completo |
| `europepmc_catalog.py`, `pubmed_catalog.py`, `arxiv_catalog.py`, `doaj_catalog.py`, `openaire_catalog.py`, `openalex_catalog.py` | Um adaptador por fonte, todos para o mesmo formato `Work` |
| `europepmc.py` | Metadados oficiais da Europe PMC (tipo de publicação, palavras-chave, financiamento) |
| `article_services.py` | Resolução de identificadores (PMID, PMCID, DOI, arXiv, OpenAlex, URL), *fallback* Crossref/Semantic Scholar/arXiv, cache de artigos |
| `extraction.py`, `extraction_view.py` | Extração **sem IA**: divide o resumo em seções, copia frases com dados estatísticos e trechos por tema |
| `reliability.py` | Nota de confiabilidade (8 critérios) |
| `enrichment.py` | ClinicalTrials.gov, OpenCitations e DataCite, em paralelo e com cache |
| `search_overview.py` | Panorama do tema |
| `downloads.py` | Documentos para baixar (txt, md, html, docx, json, xml JATS) e texto completo aberto |
| `citations.py`, `exports.py` | Seis estilos de citação; BibTeX, RIS, EndNote, CSL JSON, CSV, JSON, resumos |

## Conta e dados pessoais
| Módulo | Responsabilidade |
|---|---|
| `account_store.py` | Contas (PBKDF2), existência, troca de senha, exclusão |
| `account_tokens.py` | Tokens de uso único (redefinir senha, confirmar e-mail), guardados como hash, e o estado de confirmação |
| `admin_service.py`, `account_flags.py` | Consultas do painel de administração (visão geral, usuários, detalhe) e contas suspensas |
| `plans.py`, `billing.py`, `pix.py` | Planos e limites; assinaturas e pedidos de pagamento; BR Code do Pix |
| `account_consent.py`, `legal.py`, `legal_texts/` | Registro do aceite dos Termos e da Política (versão e data); renderização dos textos legais com os dados do controlador; os textos em Markdown |
| `mailer.py` | Envio de e-mail transacional: SMTP padrão, modo log em desenvolvimento, desligado em produção sem `SMTP_HOST` |
| `sessions.py` | Cookie assinado por HMAC, sem estado |
| `library_store.py` | Biblioteca, etiquetas, listas de leitura, compartilhamento, análises salvas |
| `reports.py`, `report_brasil.py` | Relatório de tema (itens, notas, versões, histórico, método automático) e a seção "Situação no Brasil" |
| `profiles.py` | Perfil de uso e liga/desliga do pacote Saúde no Brasil |
| `interests.py` | Catálogo de 14 áreas, subtemas e idiomas; validação das preferências; detecção de temas em texto |

## Acompanhamento
| Módulo | Responsabilidade |
|---|---|
| `alerts.py` | Verificação de artigos novos por interesse (linha de base, elegibilidade, filtro de relevância, limites), caixa de avisos |
| `notifications.py` | Avisos de retratação, mudança regulatória e novidades dos relatórios; preferências por tipo |
| `feed.py`, `feed_sources.py` | Feed: leitura de RSS/Atom/RDF, filtros, armazenamento, atualização condicional; lista curada de 51 fontes |
| `xmlutil.py` | Leitura de XML da rede sem entidades externas |

## Brasil
| Módulo | Responsabilidade |
|---|---|
| `brasil/anvisa.py`, `conitec.py`, `rename.py` | Consulta aos instantâneos (sem rede) |
| `brasil/nomes.py` | Normalização e ligação inglês ↔ português |
| `brasil/consulta.py` | Consulta unificada por substância |
| `brasil/*_build.py` | Montagem dos instantâneos a partir das fontes oficiais (usados pelos scripts de atualização) |
| `contexto_brasil.py` | Contexto institucional curado e verificação de fontes externas |
| `dados_brasil/` | `anvisa.json`, `conitec.json`, `rename.json`, `aliases_en_pt.json` |

## Laboratório de IA (opcional)
| Módulo | Responsabilidade |
|---|---|
| `workflow.py` | `AnalysisService` (analisar, auditar, comparar, extrair, citar) e `ArticleRepository`; cache de resultados e *single flight* |
| `pages.py` | Especificação declarativa das 16 áreas, botões, filtros e modelos |
| `prompt_builders.py`, `prompt_specs.py` | Montagem de prompts por botão |
| `llm_service.py` | `LLMRouter`, backends Groq e Ollama |
| `generation.py` | Política de geração (temperatura, esforço de raciocínio, teto de saída) |
| `grounding.py` | Verificação de números contra a fonte |
| `injection.py` | Neutralização de instruções escondidas no texto-fonte |
| `quota.py`, `usage.py` | Cotas diárias de tokens e registro de consumo |
| `presentation.py`, `markdown_lite.py` | Textos de apresentação e Markdown seguro sem dependências |

## Infraestrutura
| Módulo | Responsabilidade |
|---|---|
| `db.py` | `Database`: SQLite ou PostgreSQL com o mesmo SQL, transações |
| `cache.py` | `TTLCache` thread-safe com relógio injetável |
| `ratelimit.py` | Janela deslizante e identificação do cliente atrás de proxies |
| `security.py` | `safe_get`: defesa contra SSRF em buscas de URLs informadas |

## Front-end (`static/` e `templates/`)
| Arquivo | Papel |
|---|---|
| `templates/browse.html` | Página do navegador de artigos (casca da SPA) |
| `templates/ia.html` | Página do Laboratório de IA |
| `templates/_icons.html`, `_footer.html` | Ícones SVG e rodapé compartilhados |
| `static/browse.js` | SPA: roteamento, telas (início, busca, artigo, feed, biblioteca, listas, relatórios, perfil), sininho, autenticação |
| `static/browse-lib.js` | Funções puras testáveis (rotas, parâmetros, paginação) |
| `static/brand.css`, `browse.css` | Identidade visual e estilos do navegador |
| `static/app.js`, `app.css` | Laboratório de IA |

## Fora do pacote
| Pasta | Conteúdo |
|---|---|
| `tests/` | 1.471 testes (pytest) e testes de JS (`tests/js`, `node:test`) |
| `scripts/` | `atualizar_anvisa.py`, `atualizar_conitec.py`, `atualizar_rename.py`, `verificar_feeds.py`, `measure_tokens.py` |
| `evals/` | Avaliação de fidelidade com o modelo real (fora da suíte padrão) |
| `prototype/` | Protótipos de interface do navegador e do redesenho |
| `.github/workflows/` | `ci.yml` (qualidade) e `alertas.yml` (rotina agendada) |
