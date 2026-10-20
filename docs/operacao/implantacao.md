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
| Banco | PostgreSQL gerenciado do Render, definido no mesmo `render.yaml` (`DATABASE_URL` vem do banco por `fromDatabase`) |
| Plano | O Blueprint usa plano pago (web `starter` sempre ligado e banco com backup). No plano gratuito o serviço **hiberna após ~15 minutos sem acesso** e o disco é efêmero: não use com usuários reais |

Variáveis de ambiente: ver [Configuração](configuracao.md). Em `render.yaml`, `SESSION_SECRET` é gerado pelo Render; `DATABASE_URL` vem do banco criado pelo próprio Blueprint; `APP_BASE_URL`, `SMTP_*`, `GROQ_API_KEY`, `ALERTS_CRON_TOKEN` e `ADMIN_TOKEN` são informados no painel (`sync: false`).

## Dois Blueprints: gratuito e pago
- **`render.yaml` (gratuito, o padrão):** só o serviço web no plano `free`. O banco é um PostgreSQL gratuito do **Neon** (o gratuito do Render expira em 30 dias) e a URL vai em `DATABASE_URL`. Passo a passo em [Tutorial: primeiro deploy](tutorial-primeiro-deploy.md).
- **`render.pago.yaml` (para quando houver receita):** serviço `starter` sempre ligado mais PostgreSQL gerenciado com backup, na mesma região. Para usá-lo, informe esse caminho ao criar o Blueprint.

A descrição abaixo é do desenho **pago**; no gratuito, troque "banco do Render" por "banco do Neon".

## O Blueprint pago (`render.pago.yaml`)
Cria, na mesma região (`virginia`), o **PostgreSQL** (`biomedical-data-digger-db`, plano pago com backup) e o **serviço web** (plano `starter`, sempre ligado), liga `DATABASE_URL` ao banco, gera `SESSION_SECRET`, define o *health check* em `/healthz` e lista as variáveis que você preenche no painel (`ADMIN_EMAILS`, `LEGAL_CONTROLLER`, `LEGAL_CONTACT`, `PIX_KEY`, `PIX_NAME`, `APP_BASE_URL`, `SMTP_*`, `GROQ_API_KEY`, `ALERTS_CRON_TOKEN`, `ADMIN_TOKEN`). **Confirme os nomes dos planos no painel do Render antes de aplicar** (eles mudam).

### Banco pronto antes do primeiro tráfego
1. Aplique o Blueprint (*New → Blueprint*) e espere o banco ficar disponível.
2. Rode o verificador apontando para o banco (use a *External Database URL* temporariamente, só na sua máquina):
   ```bash
   DATABASE_URL="postgresql://..." python scripts/verificar_banco.py
   ```
   Ele conecta, cria as 29 tabelas que faltarem (só `CREATE TABLE IF NOT EXISTS`), confere se todas existem e faz uma escrita e leitura de teste sem deixar rastro. Saída esperada: "Banco pronto."
3. O serviço também cria as tabelas na subida e **falha rápido** se o banco estiver fora (melhor do que falhar no primeiro login).
4. Confirme o **backup automático** do plano contratado e teste uma restauração (ver *Backup e recuperação* abaixo).

## Primeira implantação
1. Aplicar o Blueprint (cria banco e serviço) e preencher as variáveis marcadas no painel: **`LEGAL_CONTROLLER` e `LEGAL_CONTACT` (sem elas o serviço não sobe)**, `APP_BASE_URL`, `SMTP_*` (e-mail), `GROQ_API_KEY` (se usar o Laboratório) e, para a rotina de avisos, `ALERTS_CRON_TOKEN` (≥24 caracteres).
2. Rodar `scripts/verificar_banco.py` (seção acima).
3. Se preferir criar tudo à mão: PostgreSQL na mesma região do serviço, URL **interna** em `DATABASE_URL` e os mesmos valores do Blueprint.
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
