# Runbook de operação

Guia para diagnosticar e resolver problemas comuns. Para cada sintoma: o que significa, como confirmar e o que fazer.

## Onde olhar primeiro
| O quê | Como |
|---|---|
| O serviço está no ar? | `GET /healthz` deve devolver `{"status":"ok"}` |
| Logs | Painel do Render → *Logs* (formato `loguru`; uma linha por chamada de LLM, com contagens e sem conteúdo) |
| Consumo de IA | `GET /api/admin/usage` com `Authorization: Bearer <ADMIN_TOKEN>` |
| Estado do feed | `GET /api/feed/sources` (última atualização e falha por fonte) |
| Rotina agendada | GitHub → *Actions* → "Alertas agendados" |
| Versão em produção | Painel do Render → último deploy (commit) |

## Sintomas e ações

### O site está lento na primeira visita
**Causa provável:** o plano gratuito hiberna após ~15 min sem acesso. **Ação:** esperar ~30–60 s; para uso comercial, usar plano sempre ligado. A rotina agendada tenta de novo ao acordar o servidor.

### Serviço não sobe após o deploy
1. Ver os logs de build/início.
2. `APP_ENV=production` sem `SESSION_SECRET` (≥32) → "SESSION_SECRET … obrigatória em produção". Defina a variável.
3. Sem `DATABASE_URL` em produção → "DATABASE_URL é obrigatória em produção". Defina a URL do PostgreSQL.
4. `ADMIN_TOKEN` ou `ALERTS_CRON_TOKEN` com menos de 24 caracteres → falha de configuração. Use um valor maior ou deixe vazio.
5. Build falhando por versão de Python → confirmar `PYTHON_VERSION=3.11.9`.
6. Reverter para o deploy anterior (ver [Implantação](implantacao.md#reversão-rollback)).

### "Nenhuma fonte de artigos respondeu agora"
Todas as fontes de busca falharam (rede do provedor ou queda geral). Confirme se as APIs respondem (Europe PMC e PubMed são as principais). Costuma se resolver sozinho; os avisos por fonte aparecem na própria busca.

### Busca lenta ou com aviso "X demorou demais"
A busca combinada espera no máximo 8 s e dispensa a fonte lenta (a OpenAIRE é a mais lenta). É esperado e não é erro. Se for **toda** busca, verifique a latência até as APIs a partir do servidor e se o limite do NCBI (3 req/s sem chave) está estourando; configure `NCBI_API_KEY`.

### Erros 429 ("Limite de taxa excedido")
Um IP/conta passou do limite (ver [Segurança](../arquitetura/seguranca.md#limites-de-uso-e-cotas)). Se muitos usuários legítimos recebem 429 ao mesmo tempo, o IP lido pode estar errado (todos parecem o mesmo IP do proxy): confirme `TRUSTED_PROXY_HOPS` (1 no Render, sem CDN na frente).

### Laboratório de IA indisponível ou com erro
- "Backend indisponível": `GROQ_API_KEY` ausente/inválida ou provedor fora do ar. Teste a chave no painel da Groq.
- "Cota diária de uso atingida": é a cota por identidade (renova às 00:00 UTC). Ajuste `DAILY_TOKEN_BUDGET_*` se necessário.
- Resposta truncada: o modelo estourou o teto de saída; peça menos detalhe ou outro modelo.
- Nada disso afeta busca, nota, relatórios ou alertas.

### Feed vazio ou desatualizado
1. `GET /api/feed/sources`: ver `lastOk` e `failing` por fonte.
2. Primeira vez com banco vazio: a primeira atualização leva ~1 min; a tela mostra "Buscando as primeiras novidades".
3. Sem rotina agendada, só atualiza quando alguém abre o feed (até 12 fontes por visita). Ative a rotina (ver [Rotinas agendadas](rotinas-agendadas.md)).
4. Fonte específica falhando: rodar `python scripts/verificar_feeds.py`; feeds mudam de endereço ou passam a bloquear robôs. Corrigir a URL em `feed_sources.py` ou remover a fonte.
5. Muito ruído de um jornal: ajustar os `ACADEMIC_CUES` do filtro em `feed.py`.

### Avisos do sininho não chegam
1. A conta tem **interesses** salvos? (Perfil → Interesses.) Sem interesses não há avisos de artigo novo.
2. Primeira verificação só cria a **linha de base** (não avisa o que já existia).
3. Tipos de aviso podem estar desligados (Perfil → Notificações).
4. Sem rotina agendada, a verificação só roda com o site aberto (mínimo 6 h entre verificações automáticas; "Verificar agora" aceita 15 min).
5. Verifique o retorno da rotina (`watch`, `failed`).

### Uma pessoa não consegue entrar
- Senha errada repetidas vezes → limite de tentativas (aguardar 1 min).
- Cookie bloqueado pelo navegador (cookies de terceiros não importam; é do próprio domínio).
- Conta excluída: o cookie deixa de valer em até 30 s.
- Esqueceu a senha: a própria pessoa usa **Esqueci a senha** (link por e-mail). Se o e-mail não chegar, ver "E-mails não chegam" abaixo; sem e-mail configurado, use o procedimento manual no final.

### Conciliar pagamentos Pix e ativar assinaturas
1. Entre com a sua conta de administrador (e-mail em `ADMIN_EMAILS`) e abra **Administração → Pagamentos** (ou `#/admin/pagamentos`). Sem conta de administrador, o `ADMIN_TOKEN` funciona na mesma tela.
2. Em **Pedidos pendentes**, compare cada pedido (e-mail, valor, identificador) com o extrato do banco da chave Pix. O banco costuma mostrar valor, data e nome do pagador; o identificador `BDD…` aparece só em alguns bancos.
3. Bateu: **Confirmar pagamento** (a assinatura é ativada ou prorrogada e a pessoa recebe e-mail). Não bateu e faz mais de alguns dias: **Cancelar**.
4. Pagamento recebido sem pedido: ache a conta em **Administração → Usuários** e use **Dar 30 dias de Pro** (ou peça à pessoa que crie o pedido).
5. Problemas comuns: valor diferente do pedido (não confirme; combine com a pessoa), pagamento duplicado (confirme um e devolva o outro), "Painel desativado" (falta `ADMIN_TOKEN` no servidor), 401 (token errado).
6. Emita o recibo e, quando devida, a nota fiscal (fora do sistema).

### E-mails não chegam (confirmação ou recuperação)
1. A interface diz "A recuperação de senha por e-mail não está disponível"? Faltam `SMTP_HOST` e companhia no Render (ver [Configuração](configuracao.md)).
2. Nos logs, procure "Falha ao enviar e-mail de conta": o provedor recusou (credencial, remetente não verificado, limite de envio).
3. Chegou, mas no spam: configure SPF, DKIM e DMARC do domínio do remetente.
4. Link abre "inválido ou expirou": o link de redefinição vale 1 hora e o de confirmação 48 horas, e só funcionam uma vez; peça outro.
5. `APP_BASE_URL` errada gera links para o endereço errado: confira (https, sem barra no fim).

### Suspender, reativar ou excluir uma conta
*Administração → Usuários →* clique no e-mail. **Suspender** bloqueia o acesso na hora (sem apagar nada) e **Reativar** devolve. **Excluir conta e dados** pede o e-mail de novo e é irreversível (pagamentos confirmados ficam). Administradores não podem ser suspensos nem excluídos por aqui: tire o e-mail de `ADMIN_EMAILS` antes, se for o caso.

### Pedido de exclusão ou cópia de dados
A própria pessoa faz em *Perfil → Conta e dados*. Se não conseguir entrar, siga o procedimento de [Privacidade e LGPD](../legal/privacidade-e-lgpd.md#atendimento-de-solicitações) (verificar identidade e executar manualmente).

### Dados do Brasil desatualizados
Aviso na interface após 60 dias (ANVISA e Conitec). Rodar o procedimento de [Atualização dos dados do Brasil](dados-brasil.md).

### Banco de dados
- **Conexão falhando:** o provedor pode estar em manutenção; as sessões continuam valendo (a checagem de existência falha "aberta"), mas rotas que gravam falham com 5xx.
- **Disco SQLite em produção:** nunca usar; ver [Configuração](configuracao.md).
- **PostgreSQL novo:** as tabelas se criam na subida. O caminho PostgreSQL das tabelas mais novas ainda precisa de validação em banco real (ver [Roadmap](../roadmap/roadmap.md)); se uma consulta falhar só em produção, comparar o SQL com o SQLite.

## Procedimentos manuais

### Redefinir a senha de uma conta (somente se o e-mail não estiver configurado)
1. Confirmar a identidade da pessoa por um canal acordado.
2. Gerar um novo hash com o mesmo algoritmo (PBKDF2-SHA256, 600.000 iterações, sal novo de 32 bytes) usando `account_store.py` em um console com acesso ao banco, e atualizar `password_hash`/`password_salt`.
3. Orientar a pessoa a trocar a senha ao entrar.
> Com SMTP configurado, a pessoa resolve sozinha pelo "Esqueci a senha"; este procedimento fica para exceções.

### Remover uma fonte do feed
Remover a entrada de `feed_sources.py` e fazer o deploy; os itens dela somem em até 45 dias.

### Encerrar todas as sessões
Trocar `SESSION_SECRET` e reimplantar: todos os cookies deixam de valer.

### Limpar o cache
Reiniciar o serviço (os caches estão em memória).

## Escalonamento
Registre incidentes (data, sintoma, causa, correção) em um arquivo próprio ou no sistema de chamados adotado. Falhas de segurança seguem [SECURITY.md](../../SECURITY.md).
