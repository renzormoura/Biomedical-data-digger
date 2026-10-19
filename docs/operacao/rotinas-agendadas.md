# Rotinas agendadas

## Para que servem
Com o site fechado, ninguém dispara as verificações. A **rotina agendada** chama uma rota protegida do servidor que, em uma só execução:
1. verifica artigos novos para as contas com interesses vencidas (alertas);
2. reconfere um lote de artigos na fonte para detectar **retratações** e roda o vigia de **mudanças regulatórias** e **novidades de relatórios**;
3. atualiza **todas as fontes do feed**.

Sem a rotina, tudo isso continua funcionando, mas só quando alguém abre o site (alertas e retratações da própria conta) e o feed só se atualiza quando alguém o abre (até 12 fontes por visita).

## Como está montada
- **Gatilho:** GitHub Actions, `.github/workflows/alertas.yml`, `cron: "17 */6 * * *"` (a cada 6 horas, minuto 17) e execução manual (*workflow_dispatch*).
- **Chamada:** `POST {APP_URL}/api/internal/alerts/run` com `Authorization: Bearer {ALERTS_CRON_TOKEN}`. Como o plano gratuito do Render dorme, o `curl` tem até 4 novas tentativas com 20 s de intervalo (`--retry-all-errors`) e 240 s de limite.
- **Sem segredos configurados, o fluxo termina sem erro** ("nada a fazer").
- **Servidor:** a rota só existe com `ALERTS_CRON_TOKEN` (≥24 caracteres) definido; sem ele responde 404. Compara o token em tempo constante, limita a 10 chamadas por minuto e **não aceita sessão de usuário**.

## Ativação (passo a passo)
1. Gerar um token aleatório com 24+ caracteres (por exemplo, `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
2. No Render: definir `ALERTS_CRON_TOKEN` com esse valor e reimplantar.
3. No GitHub (*Settings → Secrets and variables → Actions*): criar `ALERTS_CRON_TOKEN` (mesmo valor) e `APP_URL` (por exemplo `https://seu-app.onrender.com`, **sem barra no fim**).
4. Rodar o fluxo manualmente (*Actions → Alertas agendados → Run workflow*) e conferir o JSON de retorno.

> **Estado atual:** o fluxo está no repositório, mas **ainda não foi ativado** (segredos pendentes).

## Resposta
```json
{
  "due": 3, "ran": 3, "new": 5, "failed": 0, "...": "...",
  "watch": {"due": 3, "ran": 3, "notified": 1, "failed": 0, "refreshed": 40},
  "feed":  {"due": 51, "refreshed": 49, "failed": 2, "items": 1530, "skipped": 0}
}
```
- Alertas: contas vencidas verificadas, avisos novos, falhas.
- `watch`: contas verificadas, avisos criados, artigos reconferidos (até 40 por execução).
- `feed`: fontes vencidas, atualizadas, com falha e itens guardados. Atualizar as 51 fontes leva cerca de 40 a 60 segundos.
- Cada execução trata até **40 contas**; o que sobrar fica para a próxima (6 h depois).

## Limites e cuidados
- Uma fonte do feed ou uma conta que falha **não derruba as demais**.
- Execuções concorrentes: o feed usa uma trava por processo; uma segunda chamada simultânea é ignorada (`skipped`).
- Para avisos mais frequentes, reduza o intervalo do `cron` (mantendo o respeito às fontes: o feed já limita cada fonte a 1 busca a cada 3 h).
- Futuro: avisos por e-mail ou *push* dependem de um provedor de e-mail e de confirmação de endereço (ver [Roadmap](../roadmap/roadmap.md)).

## Verificações que não são agendadas
`python scripts/verificar_feeds.py` (conferência manual das 51 fontes) e as atualizações dos dados do Brasil (ver [Atualização dos dados do Brasil](dados-brasil.md)) são rodadas por uma pessoa, de vez em quando.
