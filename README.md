# Biomedical Data Digger

Plataforma web de pesquisa científica: **encontrar, entender, acompanhar e entregar**. Busca em várias fontes abertas, nota de confiabilidade com critérios abertos, avisos por interesse, feed de novidades, relatórios com método declarado e citações prontas para Zotero, Mendeley e EndNote. Para saúde no Brasil, um pacote opcional cruza medicamentos com ANVISA, Conitec e Rename. Um Laboratório de IA opcional complementa o que é feito sem IA.

> **Software proprietário e confidencial.** Este repositório é privado; todos os direitos reservados. Veja [LICENSE](LICENSE) e [docs/legal/licenca-e-confidencialidade.md](docs/legal/licenca-e-confidencialidade.md).

## Em produção
`https://biomedical-data-digger.onrender.com` (Render, PostgreSQL).

## Documentação
Comece pelo [índice da documentação](docs/README.md).

| Quero… | Documento |
|---|---|
| Entender o produto | [Visão geral](docs/produto/visao-geral.md) · [Guia do usuário](docs/produto/guia-do-usuario.md) |
| Saber como cada funcionalidade funciona | [Funcionalidades](docs/README.md#funcionalidades) |
| Entender a arquitetura | [Arquitetura](docs/arquitetura/visao-geral.md) · [Módulos](docs/arquitetura/modulos.md) · [Dados](docs/arquitetura/dados.md) |
| Consultar a API | [Referência da API](docs/api/referencia.md) |
| Operar o serviço | [Implantação](docs/operacao/implantacao.md) · [Configuração](docs/operacao/configuracao.md) · [Runbook](docs/operacao/runbook.md) |
| Desenvolver | [Ambiente](docs/development/setup.md) · [Guia de desenvolvimento](docs/desenvolvimento/guia-de-desenvolvimento.md) · [Testes](docs/desenvolvimento/testes.md) |
| Avaliar riscos | [Segurança](docs/arquitetura/seguranca.md) · [Licenças das fontes](docs/legal/licencas-e-termos.md) · [Privacidade](docs/legal/privacidade-e-lgpd.md) |
| Ver o plano | [Roadmap](docs/roadmap/roadmap.md) · [Changelog](docs/changelog/CHANGELOG.md) |

## Início rápido (desenvolvimento)
```bash
python -m venv .venv_local && source .venv_local/bin/activate   # Windows: .venv_local\Scripts\Activate.ps1
pip install -r requirements-dev.txt
cd biomedical-article-summariser && python biomedical_data_digger.py   # http://localhost:7860
```
Sem `DATABASE_URL`, usa SQLite local. Variáveis: [Configuração](docs/operacao/configuracao.md).

## Qualidade
```bash
ruff check biomedical-article-summariser tests evals scripts
mypy
pytest                                    # 1.471 testes; cobertura mínima de 80%
node --test tests/js/browse-lib.test.js
```

## Estrutura do repositório
| Caminho | Conteúdo |
|---|---|
| `biomedical-article-summariser/` | Aplicação (Python/FastAPI, front-end em `static/` e `templates/`, dados do Brasil em `dados_brasil/`) |
| `tests/` | Testes (`pytest` e `node:test`) |
| `docs/` | Documentação |
| `scripts/` | Atualização dos dados do Brasil, verificação do feed, medição de tokens |
| `evals/` | Avaliação de fidelidade com modelo real (fora da suíte padrão) |
| `prototype/` | Protótipos de interface |
| `.github/workflows/` | CI e rotina agendada de avisos |
| `render.yaml` | Definição do serviço no Render |

## Contato e suporte
Segurança: [SECURITY.md](SECURITY.md). Demais assuntos: responsável pelo projeto.
