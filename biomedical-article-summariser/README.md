# Nexus Science — aplicação

Código da aplicação web (Python/FastAPI, front-end em JavaScript puro). A documentação completa está em [`../docs/`](../docs/README.md); este arquivo é só um mapa rápido.

## Telas
| Rota | O que é |
|---|---|
| `/` | Navegador de artigos: início, busca, artigo, feed, biblioteca, listas, relatórios e perfil (`#/lista/TOKEN` é pública e somente leitura) |
| `/ia` | Laboratório de IA (opcional) |
| `/healthz` | Verificação de saúde |

## Como rodar
Na raiz do repositório:
```bash
pip install -r requirements-dev.txt
cd biomedical-article-summariser
python biomedical_data_digger.py        # http://localhost:7860
```
Sem `DATABASE_URL`, usa SQLite local. Variáveis de ambiente: [Configuração](../docs/operacao/configuracao.md). Depois de editar JS/CSS, reinicie o servidor.

## Onde está cada coisa
| Pasta/arquivo | Conteúdo |
|---|---|
| `biomedical_data_digger.py` | Ponto de entrada (monta as dependências e sobe o servidor) |
| `web.py`, `browse_api.py`, `account_routes.py` | Rotas e middleware |
| `discovery.py`, `*_catalog.py` | Busca em várias fontes |
| `reliability.py`, `extraction.py` | Nota de confiabilidade e extração do resumo (sem IA) |
| `library_store.py`, `reports.py`, `alerts.py`, `notifications.py`, `feed.py`, `profiles.py` | Dados e serviços por conta |
| `brasil/`, `dados_brasil/` | ANVISA, Conitec e Rename (instantâneos versionados) |
| `workflow.py`, `llm_service.py`, `pages.py`, `prompt_*.py` | Laboratório de IA |
| `static/`, `templates/` | Front-end |

Catálogo completo: [Módulos](../docs/arquitetura/modulos.md). API: [Referência](../docs/api/referencia.md).

## Qualidade
```bash
ruff check biomedical-article-summariser tests evals scripts
mypy
pytest
node --test tests/js/browse-lib.test.js
```
Ver [Testes](../docs/desenvolvimento/testes.md) e [Guia de desenvolvimento](../docs/desenvolvimento/guia-de-desenvolvimento.md).

> Software proprietário e confidencial. Veja o [LICENSE](../LICENSE).
