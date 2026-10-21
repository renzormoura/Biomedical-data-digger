# Estratégia de testes

## Visão geral
| Camada | Ferramenta | Onde | Quantidade |
|---|---|---|---|
| Unitários e de integração do servidor | `pytest` | `tests/*.py` (57 arquivos) | **1.471 testes** (inclui parametrizados e 15 subtestes) |
| Contrato da API | `pytest` | `tests/test_api_contract.py`, retrato em `tests/golden/api_contract.json` | 96 chamadas cobrindo **todas** as rotas |
| Propriedades | `hypothesis` | `tests/test_properties.py` | Parsing de identificadores, verificação de números, chaves canônicas |
| Front-end (funções puras) | `node --test` | `tests/js/browse-lib.test.js` | 11 testes |
| Fidelidade com modelo real | `pytest -m live` | `evals/test_fidelity_live.py` | Fora da suíte padrão (chama o Groq) |
| Verificação visual | Manual (desktop e celular) | — | Sem teste visual automatizado |

Cobertura mínima de **80%** (`fail_under` em `pyproject.toml`); atual ≈96%. O ponto de entrada (`nexus_science.py`) é excluído da medição.

## Princípios
- **Nunca usar rede real.** Um *fixture* automático (`conftest.py`) faz todo DNS resolver para um IP público fixo; as fontes são simuladas (`FakeCatalog`, respostas HTTP montadas com `make_response`). Testes **não chamam o Groq**.
- **Relógio injetável:** caches, limitadores e vigias recebem `clock`, então os testes avançam o tempo sem esperar.
- **Banco real em arquivo temporário:** os armazéns são testados contra SQLite de verdade (`tmp_path`), exercitando o SQL.
- **Testes de contrato:** prompts (`test_prompt_contract.py`), navegação e página servida (`test_browse_api.py`), regra de "sem emoji" (`test_no_emoji_ui.py`), camada sem IA (`test_no_ai_layer.py`).
- **Segurança:** `test_security.py` (SSRF), `test_injection_guards.py`, `test_sessions.py`, `test_ratelimit.py`, `test_quota.py`, entidades XML maliciosas no feed.

## Mapa dos testes por área
| Área | Arquivos |
|---|---|
| Busca e fontes | `test_discovery.py`, `test_more_sources.py`, `test_europepmc*.py`, `test_openalex_catalog.py`, `test_keyword_search.py`, `test_link_resolution.py`, `test_source_fetchers.py`, `test_search_overview.py` |
| Artigo, extração e nota | `test_extraction.py`, `test_abstract_cleaning.py`, `test_reliability.py`, `test_published_date.py`, `test_downloads.py` |
| Citações e exportação | `test_citations.py`, `test_exports.py`, `test_reference_export.py` |
| Conta e dados | `test_account.py`, `test_account_store.py`, `test_sessions.py`, `test_library_store.py`, `test_profiles.py` |
| Relatórios | `test_reports.py` |
| Acompanhamento | `test_alerts.py`, `test_notifications.py`, `test_feed.py` |
| Brasil | `test_brasil_anvisa.py`, `test_brasil_conitec.py`, `test_brasil_rename.py`, `test_contexto_brasil*.py` |
| Laboratório de IA | `test_workflow.py`, `test_lab_analyses.py`, `test_pages_spec.py`, `test_prompt_*.py`, `test_llm_*.py`, `test_generation_options.py`, `test_grounding.py`, `test_injection_guards.py`, `test_result_cache.py`, `test_singleflight.py`, `test_quota.py`, `test_usage*.py` |
| Infra | `test_cache.py`, `test_ratelimit.py`, `test_security.py`, `test_markdown_lite.py`, `test_web.py`, `test_browse_api.py` |

## Rodar a suíte contra PostgreSQL
Por padrão os testes usam SQLite. Para validar o SQL em PostgreSQL de verdade (o banco de produção), suba um PostgreSQL descartável e defina `TEST_POSTGRES_URL`:
```bash
docker run -d --name nexus-pg-test -e POSTGRES_PASSWORD=nexus_local_test -e POSTGRES_DB=nexus -p 127.0.0.1:55432:5432 postgres:16-alpine
export TEST_POSTGRES_URL="postgresql://postgres:nexus_local_test@127.0.0.1:55432/nexus"
pytest --no-cov
docker rm -f nexus-pg-test        # ao terminar
```
- Cada teste ganha um **schema próprio** (isolamento total, apagado ao fim); `Database(database_url="")` e `AccountStore` apontam para ele. Está em `tests/conftest.py`.
- Use **`127.0.0.1`**, não `localhost`: no Windows, `localhost` demora ~10 s por conexão e a suíte fica inviável.
- Testes que verificam comportamento só do SQLite levam `@pytest.mark.sqlite_only` e são pulados nesse modo.
- A suíte leva ≈6 minutos no PostgreSQL (uma conexão por operação).

## Como rodar
```bash
pytest                                   # tudo, com cobertura
pytest tests/test_reliability.py -q      # um arquivo
pytest -k "feed and not refresh" -q      # por nome
node --test tests/js/browse-lib.test.js  # front-end
pytest -m live                           # avaliação com modelo real (precisa de GROQ_API_KEY; custa tokens)
```

## O que escrever ao mudar o código
| Mudança | Teste esperado |
|---|---|
| Novo critério/peso da nota | Casos por status e o total de pesos (100) |
| Nova fonte de busca | Conversão para `Work`, filtros, erro de rede, paginação |
| Nova rota | Autenticação (401), validação (422), caso feliz e limites |
| Novo armazém ou coluna | Criação idempotente, dono, limite, `delete_user_data`, exportação |
| Mudança em feed | Parsing (RSS, Atom, RDF), datas, filtros, 304, falha isolada |
| Mudança de segurança | Caso de abuso reproduzido como teste |

## CI
`.github/workflows/ci.yml` roda em cada *push* na `main` e em *pull requests*. O job `quality` usa Python 3.10 e 3.11 e o job `postgres` roda a suíte inteira contra PostgreSQL 16 (serviço do próprio CI). O `quality` faz: `ruff check`, `mypy`, `pytest --cov` (falha abaixo de 80%), `node --test` e auditoria de dependências (`pip-audit`, não bloqueante).

## Lacunas conhecidas
- Sem teste de carga e sem teste de restauração de backup.
- Sem teste de carga e sem teste visual automatizado.
- A fidelidade da IA é medida só manualmente com `evals/`.
