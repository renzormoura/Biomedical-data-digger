# Implantação

## Ambiente de produção
| Item | Valor |
|---|---|
| Hospedagem | **Render** (serviço web Python) |
| Definição | `render.yaml` na raiz (infraestrutura como código) |
| Diretório raiz do serviço | `biomedical-article-summariser` |
| Build | `pip install -r requirements.txt` |
| Início | `python biomedical_data_digger.py` (uvicorn em `0.0.0.0:$PORT`) |
| Python | 3.11.9 (`PYTHON_VERSION`; sem isso o Render usa uma versão nova e o build falha) |
| Banco | PostgreSQL persistente (`DATABASE_URL`) |
| Plano atual | Gratuito/básico: o serviço **hiberna após ~15 minutos sem acesso** (a primeira requisição é lenta) e o disco é efêmero |

Variáveis de ambiente: ver [Configuração](configuracao.md). Em `render.yaml`, `SESSION_SECRET` é gerado pelo Render; `GROQ_API_KEY`, `DATABASE_URL` e `ALERTS_CRON_TOKEN` são informados no painel (`sync: false`).

## Primeira implantação
1. Criar o PostgreSQL no Render (ou outro provedor) e copiar a URL **interna** (mesma região do serviço).
2. Criar o serviço web a partir do repositório (Blueprint com `render.yaml` ou manualmente com os valores acima).
3. Definir `DATABASE_URL`, `GROQ_API_KEY` (se usar o Laboratório) e, para a rotina de avisos, `ALERTS_CRON_TOKEN` (≥24 caracteres).
4. Fazer o deploy. Na subida, cada armazém cria as próprias tabelas (`CREATE TABLE IF NOT EXISTS`).
5. Conferir `GET /healthz` (`{"status": "ok"}`), abrir o site, criar uma conta de teste e executar uma busca.
6. Configurar a rotina agendada (ver [Rotinas agendadas](rotinas-agendadas.md)).

## Fluxo de entrega
1. Alterar o código em ramo local; rodar **lint, tipos e testes** (ver [Guia de desenvolvimento](../desenvolvimento/guia-de-desenvolvimento.md)).
2. Atualizar o [Changelog](../changelog/CHANGELOG.md) e a documentação afetada.
3. Commit atômico com mensagem descritiva e `push` para `main`.
4. O **CI** (`.github/workflows/ci.yml`) roda ruff, mypy, pytest com cobertura mínima de 80% e testes de JavaScript em Python 3.10 e 3.11.
5. O Render detecta o push em `main` e faz o redeploy automático.

Não há ambiente de homologação separado. Para validar mudanças arriscadas, rode localmente com PostgreSQL de teste.

## Reversão (rollback)
- Pelo painel do Render: *Deploys → reimplantar o deploy anterior*.
- Pelo Git: `git revert <commit>` e push para `main`.
- **Dados:** como o esquema só cresce (`CREATE TABLE IF NOT EXISTS`, mudanças aditivas), voltar o código não exige desfazer o banco. Mudanças destrutivas de esquema não existem hoje; se vierem, exigem plano próprio.

## Considerações de escala
- O produto assume **uma instância**: caches, limitadores de taxa, cotas de tokens e travas de atualização vivem na memória do processo. Escalar horizontalmente exige primeiro mover limitadores e cotas para um armazém compartilhado (ver [Roadmap](../roadmap/roadmap.md)).
- O plano gratuito hiberna: para uso comercial, use um plano sempre ligado, o que também deixa a rotina de avisos mais confiável.
- Banco: índices existem nas chaves usadas; consultas pesadas são limitadas por tetos (por exemplo, 800 candidatos do feed, 500 artigos por biblioteca).

## Backup e recuperação
- Os dados de contas ficam no PostgreSQL: usar os **backups automáticos do provedor** (confirmar o plano contratado) e testar a restauração.
- O repositório contém tudo o mais (código, instantâneos do Brasil, lista de fontes do feed).
- Pendência: definir RPO/RTO e testar uma restauração de ponta a ponta antes do lançamento comercial.

## Domínio, TLS e proxies
O Render termina o TLS e injeta `X-Forwarded-For`. O produto assume **um** proxy confiável (`TRUSTED_PROXY_HOPS=1`); se colocar outro serviço na frente (CDN, WAF), ajuste a variável, ou os limitadores usarão o IP errado.
