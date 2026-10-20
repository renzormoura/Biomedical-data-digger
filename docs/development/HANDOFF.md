# Passagem de bastão (HANDOFF)

Estado do projeto para quem vai continuar. Atualizado em **19/10/2026**. O panorama completo está em [PROJECT-CONTEXT](../PROJECT-CONTEXT.md) e o plano em [Roadmap](../roadmap/roadmap.md).

## Resumo do estado
- **Em produção** no Render (`https://biomedical-data-digger.onrender.com`). Branch única: `main` (cada push gera deploy).
- Produto: plataforma de pesquisa científica geral + pacote opcional Saúde no Brasil + Laboratório de IA opcional.
- Qualidade: 1.471 testes passando, ruff e mypy limpos, testes de JS; cobertura ≈96%.
- Nenhuma tarefa interrompida.

## O que está pronto mas **ainda não ligado/validado**
| Item | Situação | O que falta |
|---|---|---|
| Rotina agendada (alertas, retratações, feed) | Fluxo e rota prontos | Definir `ALERTS_CRON_TOKEN` no Render e os segredos `APP_URL` e `ALERTS_CRON_TOKEN` no GitHub |
| PostgreSQL | Suíte completa passa em PostgreSQL 16 local (`TEST_POSTGRES_URL`, ver [Testes](../desenvolvimento/testes.md)) | Apontar `DATABASE_URL` de produção, conferir backups e restauração |
| Dados do Brasil | Instantâneos de 17/10/2026 | Revisão por farmacêutico/médico; resolver a licença da Rename |
| Feed | 51 fontes verificadas em 18/10/2026 | Revisar os termos de cada fonte |
| Planos e pagamento por Pix | Implementado (Fase A, conciliação manual); limites desligados (`BILLING_ENFORCED=0`) | Definir preço, chave Pix (`PIX_KEY`, `PIX_NAME`), CNPJ/MEI; ligar `BILLING_ENFORCED`; depois provedor com webhook |
| Termos de Uso e Política de Privacidade | Rascunhos no produto (`#/termos`, `#/privacidade`) com aceite registrado | Revisão jurídica; definir `LEGAL_CONTROLLER` e `LEGAL_CONTACT` no Render (sem eles o serviço não sobe em produção) |
| E-mail (confirmação e recuperação de senha) | Implementado e testado; Render ainda sem provedor | Contratar SMTP, definir `APP_BASE_URL` e `SMTP_*`, configurar SPF/DKIM |
| Banco no Render | `render.yaml` cria PostgreSQL + serviço; `scripts/verificar_banco.py` confere o banco | Aplicar o Blueprint, rodar o verificador, testar backup |
| Validação com usuários | Roteiro pronto | Executar |

## Onde está cada coisa
- Código: `biomedical-article-summariser/` ([catálogo de módulos](../arquitetura/modulos.md)).
- Testes: `tests/` (`tests/js/` para JavaScript); avaliação com modelo real: `evals/`.
- Dados do Brasil: `biomedical-article-summariser/dados_brasil/` + `scripts/atualizar_*.py`.
- Infra: `render.yaml`, `.github/workflows/ci.yml`, `.github/workflows/alertas.yml`.
- Documentação: `docs/` ([índice](../README.md)).

## Como retomar o trabalho
1. [Preparar o ambiente](setup.md) e rodar a suíte (`pytest`, `ruff check`, `mypy`).
2. Ler a [visão geral da arquitetura](../arquitetura/visao-geral.md) e o [guia de desenvolvimento](../desenvolvimento/guia-de-desenvolvimento.md).
3. Escolher o próximo item em [Roadmap > Próximo](../roadmap/roadmap.md#próximo-pré-lançamento-comercial).

## Convenções do trabalho
- **Commits atômicos** com mensagem no estilo `tipo(escopo): descrição` (por exemplo, `feat(feed): …`, `fix(celular): …`, `perf(busca): …`) e o trailer de coautoria quando houver.
- **Atualizar o [Changelog](../changelog/CHANGELOG.md)** e a documentação da funcionalidade a cada mudança de comportamento.
- **Push só com confirmação** do responsável pelo produto.
- Não commitar: `.env`, bancos locais, `.claude/`, `.code-review-graph/`, `tools/`, `biomedical-article_summarizer/` e PDFs de apresentação (ver `git status` antes de `git add`; **sempre adicione arquivos por caminho explícito**).
- Testes não chamam a rede nem o Groq: dependências externas são simuladas.

## Cuidados
- `runtime.txt` e `PYTHON_VERSION=3.11.9`: remover quebra o build no Render.
- Prompts clínicos (`prompt_builders.py`, `prompt_specs.py`): usados em contexto de pronto-socorro; não alterar sem validação clínica.
- Streaming de IA foi implementado e revertido ([ADR-003](../adrs/ADR-003-streaming-revertido.md)): não reimplementar sem plano maior.
- Os caches e limitadores são por processo: rodar **uma** instância.
- Depois de mudar JS/CSS localmente, reiniciar o servidor.
- A política de segurança de conteúdo bloqueia `style` e `<script>` inline: use classes e CSSOM.

## Histórico
Ver o [Changelog](../changelog/CHANGELOG.md) e os [ADRs](../adrs/).
