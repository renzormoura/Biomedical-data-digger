# CHANGELOG

## 2026-10 — Mais fontes e registros abertos

### Adicionado
- Fontes de busca: PubMed (E-utilities), arXiv, DOAJ e OpenAIRE, sem chave. O PubMed aceita `NCBI_API_KEY` opcional.
- Cartão "Registro e dados" no artigo: ClinicalTrials.gov, OpenCitations e DataCite (inclui Zenodo), carregado em segundo plano (`GET /api/discover/enrichment`).
- Leitura de XML da rede com recusa de declarações de entidade (`xmlutil.py`).

### Alterado
- A opção combinada passou a se chamar "Europe PMC + OpenAlex" e só reúne as fontes principais; as novas são escolhidas uma a uma.
- A etiqueta de citações some quando a fonte não informa o número.

### Limitações conhecidas
- medRxiv e bioRxiv não têm busca por palavra-chave na API; seus preprints já aparecem pela Europe PMC.
- arXiv, DOAJ e OpenAIRE não oferecem alguns filtros (tipo de estudo, idioma, acesso aberto, ordenação); a tela avisa quando um filtro não foi aplicado.

## 2026-10 — Nove novas abas no Laboratório de IA

### Adicionado
- Enfermagem, Farmácia, Nutrição, Psicologia, Direito e Políticas, Educação, Agro e Veterinária, Biotecnologia e Para o Paciente, com 23 prompts novos (mesma fábrica, restrição "somente a fonte" e testes de contrato).
- Abas de saúde (Enfermagem, Farmácia, Nutrição, Psicologia, Para o Paciente) são clínicas: sem redução de raciocínio e com avisos de que não substituem orientação profissional. Doses, interações e reações na Farmácia seguem extrativas, sem IA.
- Públicos e focos novos nos filtros; no desktop as abas quebram em linhas.

## 2026-10 — Navegador de artigos (pivô do produto)

### Adicionado
- `/` passa a ser um navegador de artigos: busca com filtros (ano, tipo de estudo oficial, acesso aberto, idioma, ordenação, fonte) e paginação, página do artigo, artigos semelhantes, citações ABNT/APA/Vancouver.
- Biblioteca por conta com etiquetas, listas de leitura, link público revogável (sem expor o e-mail do dono) e exportação BibTeX/RIS/ABNT/APA/Vancouver.
- Fontes: Europe PMC (padrão) e OpenAlex (opcional, com `OPENALEX_API_KEY`). Variável `DISCOVERY_CALLS_PER_MINUTE`.
- Testes de lógica do frontend em Node (`tests/js`) e etapa no CI.

### Alterado
- A interface de IA anterior foi para `/ia`; "Analisar com IA" no artigo abre `/ia?artigo=...` preenchido.

### Corrigido
- `markdown_lite`: byte NUL no texto forjava marcador interno e causava `IndexError`.

### Limitações conhecidas
- Caminho PostgreSQL da biblioteca testado apenas com SQLite; OpenAlex testado só com respostas simuladas e verificação sem chave.

## 2026-10 — Fase 3: camada sem IA e botões clínicos extrativos

### Adicionado
- **"Extrair do artigo (sem IA)"** em todas as abas: resumo organizado em seções com o texto original, números com a frase de origem, tipo de estudo do registro oficial (Europe PMC) e metadados. Zero token, nada gerado.
- **Botões de dose, conduta, interações e reações adversas passam a ser extrativos** (trechos copiados do resumo ou "Nada encontrado"). As versões geradas por IA ficam atrás de `ENABLE_GENERATIVE_CLINICAL=1`, cada uma bloqueada se o resumo não traz o tema.
- **Pré-condição `requires`:** Populações Especiais e Alertas e Contraindicações só chamam o modelo se o resumo trouxer o tema; caso contrário respondem sem gastar token.
- `POST /api/extract`; reconhecimento de rótulos em inglês, português e espanhol (com dois-pontos ou ponto) e de termos em espanhol.
- Aviso clínico próprio para conteúdo extraído (não afirma "gerado por IA").

### Testes
- De 733 para 792 (extração, Europe PMC, serviço sem IA, bloqueio, flag, API, XSS). Validado com um artigo real da Europe PMC, sem nenhuma chamada ao Groq.

## 2026-10 — Fase 2: custo por chamada, injeção e erros do provedor

### Adicionado
- **Opções de geração** (`generation.py`): temperatura 0,2, teto de saída por nível de detalhe e esforço de raciocínio. O raciocínio reduzido (`low`) só vale para 13 botões de baixo risco e **nunca nas abas clínicas** (medido: −54% de saída, −27% do total nesses botões).
- **Resposta cortada** (`finish_reason=length`) recebe aviso e não vai para o cache; resposta vazia vira erro claro.
- **Defesas contra injeção de prompt em código** (`injection.py`): frases do texto-fonte que parecem ordens ao modelo são removidas antes da análise e o usuário é avisado; respostas com menos de 120 caracteres são descartadas. Padrões estreitos para não apagar frases científicas legítimas.
- **Limpeza de boilerplate** de copyright/licença no fim do abstract.
- `scripts/measure_tokens.py` (mede tokens reais por botão e variante) e novos evals ao vivo (resistência do modelo cru e proteção ponta a ponta).

### Alterado
- Prompt de sistema: regras condensadas, mais duas regras (sem percentuais derivados; sem variantes de "Não descrito"); estrutura original preservada.
- **Erros do provedor** viram mensagens seguras: 429 amigável sem expor ID de organização; outros erros HTTP mostram só o código.
- Eval de dosagem passou a aceitar qualquer redação equivalente de "não descrito".

### Achados (ver `docs/roadmap/plano-economia-de-tokens.md`)
- Só o prompt não basta contra injeção: o modelo cru cede em ~20 a 40% das tentativas, inclusive com o prompt original.
- O Groq limita o plano gratuito a 200.000 tokens/dia por modelo; testes ao vivo consomem a cota da produção.

### Testes
- De 667 para 733 (opções, truncamento, injeção, limpeza, erros do provedor).

## 2026-10 — Economia de tokens: medição, cache e cotas (Fases 0 e 1)

### Adicionado
- **Registro de uso de tokens** por chamada, botão e aba (`usage.py`): usa o `usage` informado pelo Groq (estimativa quando ausente), emite uma linha de log estruturada sem conteúdo nem dados pessoais e agrega média, p95 e taxa de acerto de cache. Relatório em `GET /api/admin/usage` (exige `ADMIN_TOKEN`; 404 se não configurado).
- **Cache de resultados** (6 h): repetir a mesma análise custa 0 token e responde em milissegundos. Chave estável entre PMID, URL e DOI do mesmo artigo.
- **Deduplicação de requisições simultâneas** (`SingleFlight`): análises idênticas ao mesmo tempo chamam o modelo uma vez.
- **Cotas diárias de tokens por identidade** (`quota.py`): visitante 60.000 e conta 200.000 por padrão (`DAILY_TOKEN_BUDGET_GUEST` e `DAILY_TOKEN_BUDGET_USER`, 0 = sem limite).
- A interface mostra se o resultado veio do cache, os tokens da chamada e a cota restante.

### Alterado
- `LLMBackend`/`LLMRouter` ganham `complete()` (texto + uso); `generate()` virou atalho.
- `AnalysisService.analyze/audit/compare` retornam `Reply`, uma `str` com `cached`, `tokens` e `quota_remaining`.

### Testes
- De 613 para 667 (uso, cache, concorrência, cotas, API). Verificado no navegador com o Groq real.

## 2026-10 — Gradio substituído por FastAPI e frontend próprio

### Alterado
- **Interface totalmente nova** em preto e laranja (tema claro opcional), responsiva, acessível (foco visível, abas por teclado, `aria-live`) e sem recursos de terceiros em tempo de execução: HTML (Jinja2), CSS e JS próprios; sem CDN nem fontes externas.
- **Backend FastAPI** com API JSON (`/api/analyze`, `audit`, `compare`, `cite`, `search`, `auth/*`) reutilizando `workflow.py` sem alterações. Gradio e ~40 dependências transitivas removidos (ver ADR-006).
- **Contas e sessões reais**: cookie HttpOnly assinado por HMAC; o limite de uso passa a ser por conta (visitantes por IP). `SESSION_SECRET` obrigatório em produção (gerado no `render.yaml`).
- Respostas do modelo renderizadas no servidor por um renderizador de markdown próprio que escapa todo HTML (testado contra payloads de XSS).

### Segurança
- CSP `default-src 'self'`, checagem de `Origin` (CSRF), validação de tamanho em todos os campos, HSTS em produção, `docs`/`openapi` desativados, erros 500 sem vazamento.
- Assets versionados por hash de modificação (cache longo sem JS/CSS desatualizado).

### Testes
- De 548 para 610+: API (autenticação, 429, CSRF, validação, XSS, cabeçalhos), sessões, markdown e invariantes de página. Suíte validada também em um ambiente limpo com apenas as dependências de produção.

## 2026-10 — Novas abas de área

### Adicionado
- **Sete abas de análise** (antes 2): Geral, **Acadêmico**, Medicina, **Ambiental**, **Saúde Pública**, **Tecnologia e IA**, **Engenharias**, além de Pesquisa e Contas.
- **33 prompts novos**, gerados por `prompt_builders.make_builder` a partir de `prompt_specs.py` (dados). A fábrica anexa sempre a restrição "somente a fonte", então nenhum prompt novo pode omiti-la.
- **Referências ABNT, APA e Vancouver sem IA** (`citations.py`): metadados do Crossref (DOI) ou Europe PMC (PMID/PMCID), formatados por código. Campos ausentes são omitidos, nunca inventados.
- Fontes oficiais ambientais no anexo de verificação (MMA, IBAMA, CONAMA, ODS), marcadas como "pendente de revisão" até validação por especialista.
- Novos públicos-alvo e focos por aba, aplicados ao prompt de sistema.
- Medicina ganhou PICO, Crítica Metodológica, Dados Estatísticos, Interações Medicamentosas e Reações Adversas.

### Alterado
- Seção "Educacional" saiu da aba Geral e vive somente em Acadêmico.
- Especificação das abas movida para `pages.py` (dados); `ui.py` ficou com a mecânica de montagem.
- Abas de saúde (Medicina e Saúde Pública) exibem o aviso clínico persistente.
- Testes: de 293 para 548 (invariantes de todas as abas, fábrica de prompts, citações).

## 2026-10 — Refatoração arquitetural, segurança e qualidade

### Segurança
- `security.safe_get`: bloqueio de SSRF (esquema, IPs privados/loopback/metadata, revalidação a cada redirect, limite de redirects e de bytes) em toda busca de página feita a pedido do usuário.
- Rate limiting por cliente (janela deslizante) nas chamadas de LLM e em login/cadastro; IP do cliente lido do último hop confiável de `X-Forwarded-For`.
- Delimitadores do prompt agora são neutralizados na fonte (um abstract hostil não consegue "fechar" o bloco) e a fonte é truncada.
- Contas: validação de e-mail e política de senha, limite máximo (anti-DoS no PBKDF2), custo de hash equalizado para usuário inexistente, mensagem de login genérica.

### Fidelidade ao texto-fonte
- `grounding.py`: números da resposta (doses, %, decimais) ausentes do título/resumo são sinalizados automaticamente.
- Aviso clínico persistente na aba Medicina e nas comparações clínicas.
- Prompts `Resumo Clínico` passaram a declarar explicitamente a restrição "somente a fonte" (descoberto por teste de contrato).
- Avaliação de fidelidade com LLM real em `evals/` (opt-in).

### Arquitetura
- Camadas explícitas: `domain` → `workflow` (casos de uso sem Gradio) → `ui` (páginas declarativas). `biomedical_data_digger.py` reduzido a composição.
- `LLMBackend` (Protocol) com `GroqBackend`/`OllamaBackend` e `LLMRouter`; cliente criado sob demanda.
- `ArticleRepository` com cache LRU+TTL e chave canônica (PMID, URL do PubMed e DOI equivalentes compartilham entrada).
- `account_store` sem efeitos colaterais no import (`get_account_store()`).
- `Article` imutável e erros de domínio tipados (`DiggerError`, `ArticleNotFoundError`, `BackendUnavailableError`).

### Corrigido
- Botões duplicados/enganosos: "Avaliação Crítica", "Explicação para Iniciantes", "Questões de Discussão" e "Impacto na Sociedade" usavam o prompt de outro botão. "Aplicações no Mundo Real" (clone de "Implicações Práticas") foi removido. Um teste impede a regressão.
- `UnboundLocalError` potencial em `_title_lookup`; `resolve_article` sem retorno em entradas não reconhecidas.
- `_normalize_doi` não era idempotente (achado por teste de propriedade).
- Chamadas HTTP sem timeout (Europe PMC); `print` substituído por logging.
- Filtro de área casava substrings ("law" em "flaw"); agora casa início de palavra.
- Auditoria de resposta agora também disponível na aba Medicina.

### Tooling
- `pyproject.toml` (ruff, mypy, pytest, coverage ≥ 80%), `requirements-dev.txt`, CI no GitHub Actions (3.10/3.11), pre-commit.
- Testes: de 41 para 290+ (unitários, contrato de prompts, propriedades, smoke da UI).
- Scripts avulsos de PDF movidos para `tools/pdf/`.

## 2026-09 — Busca e documentação

### Adicionado
- Busca por palavras-chave agregada em Europe PMC, OpenAlex, Semantic Scholar, Crossref e arXiv.
- Filtros de pesquisa para tecnologia, engenharias, química, física, matemática, ciências sociais, psicologia, economia, educação, direito, sustentabilidade e agricultura.
- Índice de Relevância Bibliográfica com impacto por ano, atualidade, completude dos metadados e cobertura da fonte.
- Documentação específica da busca em `docs/features/busca-artigos.md`.
- Testes automatizados para busca multi-fonte, filtros gerais e cálculo do índice.

### Alterado
- README atualizado para refletir Groq, Ollama, Render, testes e fontes atuais.
- A interface passou a exibir "Relevância bibliográfica" em vez de apresentar o indicador como confiabilidade científica.
- A normalização passou a usar corretamente citações e metadados de cada fonte.

## 2026-09 — Sessão atual

### Adicionado
- 6 novos tipos de análise: Crítica Metodológica, Dados Estatísticos, Pergunta PICO, Alertas e Contraindicações, Checklist Pré-Conduta, Aplicabilidade Brasileira
- Sistema de filtros de personalização (público-alvo, tom, idioma, nível de detalhe, foco temático)
- Cache de artigos em memória (evita chamadas duplicadas às fontes externas)
- Histórico de sessão (últimas 10 consultas)
- Função `fetch_full_text()` para extrair texto completo do XML da Europe PMC (implementada, não exposta na UI)
- Documentação técnica completa (docs/)
- 11 novos botões organizados em 6 seções com accordions: Visão Geral, Clínico/PS, Acadêmico/Pesquisa, Contexto Brasileiro, Educacional, Avaliação do Artigo
- Botão "Confiabilidade do Artigo" para análise crítica baseada no conteúdo do artigo
- Redesign visual completo: tema escuro/claro com toggle ☀️/🌙, CSS customizado, fontes Inter + JetBrains Mono, botões com hover e glow azul
- **Sistema universal de busca de artigos:** suporte a PMID, PMCID, DOI, arXiv ID, OpenAlex ID, Semantic Scholar ID e URLs completas
  - `detect_input_type()` — detecção automática do tipo de ID
  - `fetch_by_doi()` — busca via Semantic Scholar + CrossRef fallback
  - `fetch_by_arxiv()` — busca via arXiv API
  - `fetch_by_openalex()` — busca via OpenAlex (reconstrói abstract do índice invertido)
  - `fetch_by_semantic_scholar()` — busca via Semantic Scholar por ID
  - `resolve_article()` — ponto de entrada universal

### Alterado
- Modelo padrão alterado para GPT-OSS 20B (mais rápido no free tier do Render)
- Dropdown de modelos simplificado para mostrar nomes reais da conta Groq
- Botão "Resumo Simples" substituído por "Resumo" (neutro, personalizável via filtros)
- Emojis removidos dos botões (visual mais profissional)
- Layout alterado para 1/3 controles + 2/3 output (mais espaço para leitura)
- Campo de busca aceita qualquer formato — não mais restrito a PMID/PMCID
- INTRO_TXT e INST_TXT atualizados para refletir todos os formatos aceitos

### Revertido
- Streaming de resposta revertido após causar lentidão no Render free tier (ver ADR-003)
- Toggle "Rápido / Completo" implementado e revertido a pedido do usuário — `fetch_full_text()` mantida no código

### Corrigido
- Bug recorrente: `generate_response is not defined` — função sobrescrita por código duplicado nas edições
- Arquivo corrompido com UI duplicada — reconstruído via sub-agente

---

## Histórico anterior

### Funcionalidades originais (pré-sessão atual)
- Busca de artigos via Europe PMC (PMCID e PMID)
- Sumário, Resumo Acadêmico, Resumo Clínico, Resumo Simples
- Botão "Medicamentos / Protocolos"
- Suporte Groq API + Ollama local
- Deploy no Render
- .env + .gitignore para proteção de secrets
