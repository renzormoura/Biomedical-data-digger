# CHANGELOG

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
