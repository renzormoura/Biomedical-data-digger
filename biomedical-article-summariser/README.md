# Biomedical Data Digger

Navegador de artigos científicos (FastAPI + frontend próprio, preto e laranja): busca com filtros, página do artigo com seções originais, números com a frase de origem e citações, biblioteca pessoal com etiquetas, listas de leitura com link público e exportação (BibTeX, RIS, ABNT, APA, Vancouver). As análises com IA (Groq ou Ollama) continuam disponíveis como camada opcional em `/ia`.

## Telas

| Rota | O que é |
|---|---|
| `/` | Navegador: início, busca, artigo, biblioteca, listas (`#/lista/TOKEN` é pública e somente leitura) |
| `/ia` | Laboratório de IA com as abas e botões descritos abaixo; "Analisar com IA" no artigo abre aqui com o campo preenchido |

Fonte padrão: Europe PMC (sem chave). Outras fontes de busca, escolhidas uma a uma no seletor (todas sem chave): **PubMed** (E-utilities; `NCBI_API_KEY` é opcional e eleva o limite), **arXiv** (1 chamada a cada 3 s, como pedem os termos), **DOAJ** e **OpenAIRE**. A opção combinada reúne só as fontes principais (Europe PMC e OpenAlex).

Na página do artigo, o cartão "Registro e dados" consulta, em segundo plano, o **ClinicalTrials.gov** (confirma registros NCT citados no resumo), o **OpenCitations** (citações por DOI) e o **DataCite** (dados e códigos ligados, inclui Zenodo). Se uma fonte não responde, o cartão avisa e tenta de novo na próxima visita.

OpenAlex é opcional e exige uma chave gratuita criada por você em `OPENALEX_API_KEY` (mais `OPENALEX_MAILTO` opcional). `DISCOVERY_CALLS_PER_MINUTE` (30) limita buscas por cliente. A biblioteca usa o mesmo banco das contas (SQLite local, PostgreSQL em produção; o caminho PostgreSQL ainda não foi exercitado em instância real).

## Funcionalidades

- Busca de artigos por palavra-chave em Europe PMC, OpenAlex, Semantic Scholar, Crossref e arXiv.
- Busca direta por PMID, PMCID, DOI, arXiv ID, OpenAlex ID, Semantic Scholar ID ou URL.
- Deduplicação e ordenação dos resultados por **Índice de Relevância Bibliográfica**.
- Filtros por áreas médicas, tecnologia, engenharias, química, física, matemática, ciências sociais, psicologia, economia, educação, direito, sustentabilidade e agricultura.
- Resumos gerais, acadêmicos e clínicos, além de análises de PICO, estatística, metodologia, medicamentos, alertas e aplicabilidade brasileira.
- Filtros de público, tom, idioma, nível de detalhe e foco temático.
- Cache em memória dos últimos 20 artigos e histórico das últimas 10 consultas.
- Cadastro e login com SQLite local ou PostgreSQL em produção.

## Abas

| Aba | Foco |
|---|---|
| Geral | Análise científica universal de qualquer área |
| Acadêmico | Estudar, escrever (fichamento, resenha), referências ABNT/APA/Vancouver (sem IA) e roteiro de seminário |
| Medicina | Resumo clínico; dose, conduta, interações e reações adversas **como trechos copiados do resumo (sem IA)**; segurança e contexto SUS/ANVISA |
| Ambiental | Impacto, poluentes, mitigação, indicadores/ODS e contexto regulatório (CONAMA/IBAMA/MMA) |
| Saúde Pública | Desenho epidemiológico, medidas de associação, vieses, SUS e vigilância |
| Tecnologia e IA | Problema, dados, métricas, reprodutibilidade, validade e riscos éticos |
| Engenharias | Metodologia, parâmetros, desempenho, incertezas, normas e viabilidade |
| Enfermagem | Cuidados descritos, escalas e instrumentos, implicações para a prática (sem recomendar condutas) |
| Farmácia | Fármaco e mecanismo, eficácia e segurança; doses, interações e reações como trechos copiados (sem IA) |
| Nutrição | Intervenção alimentar, desfechos e limites para aplicar o resultado |
| Psicologia | Instrumentos e escalas, amostra e tamanho de efeito, generalização |
| Direito e Políticas | Política avaliada, implicações regulatórias e impacto social (sem parecer jurídico) |
| Educação | Metodologia de ensino, resultados de aprendizagem e aplicação em sala de aula |
| Agro e Veterinária | Espécie e sistema, manejo e resultados, viabilidade e normas (sem recomendar doses ou insumos) |
| Biotecnologia | Organismo e método molecular, dados e acesso, reprodutibilidade e ética |
| Para o Paciente | Linguagem simples: o que o estudo mostra, o que não prova e perguntas para levar ao profissional (não é orientação médica) |
| Pesquisa / Contas | Busca por palavra-chave em 5 fontes e cadastro de usuários |

Para criar uma nova aba: adicione um `PageSpec` em `pages.py` (e, se precisar de prompts novos, um
`PromptSpec` em `prompt_specs.py` mais a linha `make_builder` em `prompt_builders.py`). Os testes
validam que cada botão tem prompt próprio, que nenhum prompt fica sem uso e que filtros e fontes existem.

## Índice de Relevância Bibliográfica

O indicador ajuda a ordenar resultados para descoberta bibliográfica. Ele **não é uma avaliação da qualidade metodológica, da validade clínica ou do risco de viés** do artigo.

O cálculo combina quatro componentes normalizados:

| Componente | Peso | Critério |
|---|---:|---|
| Impacto por ano | 40% | Citações divididas pela idade do artigo; o valor máximo é atingido em 20 citações por ano. |
| Atualidade | 25% | Pontuação decresce linearmente ao longo de 15 anos. |
| Metadados | 20% | Presença de título, revista, ano, DOI/PMID e URL. |
| Cobertura da fonte | 15% | Peso técnico da cobertura e identificação oferecida pela fonte consultada. |

O resultado fica entre `0.00` e `0.99`:

- `0.90` ou mais: alta relevância bibliográfica;
- `0.75` a `0.89`: boa relevância bibliográfica;
- abaixo de `0.75`: relevância bibliográfica moderada.

As citações são lidas de forma compatível com cada API (`citedByCount`, `cited_by`, `citationCount` ou `is-referenced-by-count`). Assim, fontes não médicas não recebem score artificialmente baixo por usarem nomes de campos diferentes.

## Execução local

Requisitos: Python 3.11.9 e Git.

```powershell
python -m venv venv
venv\Scripts\activate
pip install -r biomedical-article-summariser\requirements.txt
```

Crie `biomedical-article-summariser/.env`:

```env
GROQ_API_KEY=sua_chave_aqui
DATABASE_PATH=accounts.sqlite3
```

Execute:

```powershell
cd biomedical-article-summariser
python biomedical_data_digger.py
```

Acesse `http://localhost:7860`.

Sem `GROQ_API_KEY`, o projeto usa Ollama localmente. Nesse caso, o Ollama deve estar instalado e o modelo escolhido precisa estar disponível na máquina.

## Desenvolvimento e qualidade

Na raiz do repositório:

```powershell
pip install -r requirements-dev.txt
ruff check biomedical-article-summariser tests evals   # lint
mypy                                                   # tipos (módulos do núcleo)
pytest --cov                                           # testes + cobertura (mínimo 80%)
```

A suíte combina testes unitários com dublês de rede, testes de contrato de todos os prompts,
testes baseados em propriedades (Hypothesis) e um smoke test que monta a interface completa.
O CI (`.github/workflows/ci.yml`) roda tudo em Python 3.10 e 3.11.

Avaliação de fidelidade com LLM real (opcional; **consome a cota diária da sua chave do Groq, a mesma da produção**, que no plano gratuito é de 200.000 tokens por modelo):

```powershell
$env:RUN_LIVE_EVALS = "1"; $env:GROQ_API_KEY = "..."; pytest evals -m live
```

Em produção é obrigatório definir `SESSION_SECRET` (mín. 32 caracteres; o `render.yaml` gera um valor automaticamente).
`LLM_TEMPERATURE` (padrão 0.2, entre 0 e 2) controla a aleatoriedade das respostas. `ENABLE_GENERATIVE_CLINICAL=1` restaura os botões de dose, conduta, interações e reações adversas gerados por IA na aba Medicina (desligado por padrão; ligue só após validação por especialista).
Variáveis de custo: `DAILY_TOKEN_BUDGET_GUEST` (60000) e `DAILY_TOKEN_BUDGET_USER` (200000) definem a cota diária de tokens (0 = sem limite); `ADMIN_TOKEN` (mín. 24 caracteres) ativa `GET /api/admin/usage` (cabeçalho `Authorization: Bearer ...`), com o consumo por botão.
Variáveis opcionais: `RATE_LIMIT_PER_MINUTE` (padrão 8 chamadas de LLM/min por cliente),
`LOGIN_ATTEMPTS_PER_MINUTE` (5), `TRUSTED_PROXY_HOPS` (1, para ler o IP real atrás do proxy do Render).

Para medir o consumo real por botão (também consome cota): `python scripts/measure_tokens.py --variants baseline,low --reps 2`.

## Deploy no Render

O deploy ocorre automaticamente após `git push` para `main`.

| Configuração | Valor |
|---|---|
| Root Directory | `biomedical-article-summariser` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `python biomedical_data_digger.py` |
| Python | `3.11.9` |
| Ambiente | `APP_ENV=production` |

Em produção, configure `GROQ_API_KEY` e `DATABASE_URL`. O PostgreSQL é necessário para preservar contas, pois o disco do plano Free do Render é efêmero.

## Estrutura principal

Camadas (dependências apontam para baixo; ver `docs/adrs/ADR-004-arquitetura-em-camadas.md`):

| Camada | Módulos |
|---|---|
| Entrada | `biomedical_data_digger.py` (composição das dependências e `launch`) |
| Apresentação | `pages.py` (abas declarativas `PageSpec`) e `web.py` (rotas FastAPI, sessões, limites); `templates/` e `static/` (frontend) |
| Casos de uso | `workflow.py` (`ArticleRepository`, `AnalysisService`; sem framework web) |
| Domínio | `domain.py` (`Article`, erros tipados), `grounding.py` (checagem numérica) |
| Infraestrutura | `article_services.py` (fontes externas), `llm_service.py` (`LLMBackend`/`LLMRouter`), `account_store.py`, `cache.py`, `ratelimit.py`, `security.py` (anti-SSRF), `config.py` |
| Conteúdo | `prompt_builders.py` + `prompt_specs.py`, `citations.py`, `contexto_brasil.py`, `styles.css` |

## Limitações

- O índice bibliográfico não substitui leitura crítica nem avaliação metodológica.
- A sumarização usa o abstract; a extração de texto completo existe para Europe PMC, mas ainda não está exposta como opção na interface.
- O Render Free pode hibernar após um período sem tráfego.
- Streaming permanece desativado por desempenho no plano Free.
- A aba Contas autentica, mas ainda não restringe funcionalidades (o acesso de visitante é intencional).
- A proteção anti-SSRF valida DNS antes da conexão; não fixa o IP resolvido (ver `security.py`).
