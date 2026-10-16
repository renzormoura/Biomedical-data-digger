# Biomedical Data Digger

Aplicação web em Gradio para buscar artigos científicos, gerar resumos e executar análises especializadas com Groq ou Ollama.

## Funcionalidades

- Busca de artigos por palavra-chave em Europe PMC, OpenAlex, Semantic Scholar, Crossref e arXiv.
- Busca direta por PMID, PMCID, DOI, arXiv ID, OpenAlex ID, Semantic Scholar ID ou URL.
- Deduplicação e ordenação dos resultados por **Índice de Relevância Bibliográfica**.
- Filtros por áreas médicas, tecnologia, engenharias, química, física, matemática, ciências sociais, psicologia, economia, educação, direito, sustentabilidade e agricultura.
- Resumos gerais, acadêmicos e clínicos, além de análises de PICO, estatística, metodologia, medicamentos, alertas e aplicabilidade brasileira.
- Filtros de público, tom, idioma, nível de detalhe e foco temático.
- Cache em memória dos últimos 20 artigos e histórico das últimas 10 consultas.
- Cadastro e login com SQLite local ou PostgreSQL em produção.

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

Avaliação de fidelidade com LLM real (opcional, consome cota):

```powershell
$env:RUN_LIVE_EVALS = "1"; $env:GROQ_API_KEY = "..."; pytest evals -m live
```

Variáveis opcionais: `RATE_LIMIT_PER_MINUTE` (padrão 8 chamadas de LLM/min por cliente),
`LOGIN_ATTEMPTS_PER_MINUTE` (5), `TRUSTED_PROXY_HOPS` (1, para ler o IP real atrás do proxy do Render).

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
| Apresentação | `ui.py` (páginas declarativas `PageSpec` + fábrica Gradio) |
| Casos de uso | `workflow.py` (`ArticleRepository`, `AnalysisService`; sem Gradio) |
| Domínio | `domain.py` (`Article`, erros tipados), `grounding.py` (checagem numérica) |
| Infraestrutura | `article_services.py` (fontes externas), `llm_service.py` (`LLMBackend`/`LLMRouter`), `account_store.py`, `cache.py`, `ratelimit.py`, `security.py` (anti-SSRF), `config.py` |
| Conteúdo | `prompt_builders.py`, `contexto_brasil.py`, `styles.css` |

## Limitações

- O índice bibliográfico não substitui leitura crítica nem avaliação metodológica.
- A sumarização usa o abstract; a extração de texto completo existe para Europe PMC, mas ainda não está exposta como opção na interface.
- O Render Free pode hibernar após um período sem tráfego.
- Streaming permanece desativado por desempenho no plano Free.
- A aba Contas autentica, mas ainda não restringe funcionalidades (o acesso de visitante é intencional).
- A proteção anti-SSRF valida DNS antes da conexão; não fixa o IP resolvido (ver `security.py`).
