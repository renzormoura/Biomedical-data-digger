# Funcionalidade: Conta, sessões e dados pessoais

## Objetivo
Permitir que a pessoa use o produto sem conta (buscar, ler, navegar pelo feed) e, **com conta**, guarde artigos, acompanhe interesses, monte listas e relatórios. Também garante o controle dos dados: **baixar uma cópia** e **excluir tudo** (LGPD).

## O que a pessoa vê
- Botão "Entrar" no topo (vira o nome/e-mail da pessoa depois do login e abre o [Perfil](perfil.md)).
- Diálogo com **Entrar** e **Criar conta** (e-mail e senha).
- Em **Perfil > Conta e dados**: trocar senha, baixar uma cópia dos dados e excluir a conta.

## Regras de cadastro
- E-mail válido (normalizado em minúsculas, até 320 caracteres).
- Senha de **8 a 128 caracteres** (o teto evita abuso de custo do algoritmo de hash).
- O e-mail é confirmado por um link enviado no cadastro (ver abaixo). A conta funciona antes da confirmação.

## Como funciona
### Senhas
Guardadas como **PBKDF2-HMAC-SHA256** com **600.000 iterações** e sal aleatório de 32 bytes por conta. Nunca se guarda a senha, e o hash nunca sai da API (nem na exportação de dados).

### Sessão (`sessions.py`)
- Cookie `bdd_session` com `usuario.expiração.assinatura`. A assinatura é **HMAC-SHA256** com `SESSION_SECRET`; o cookie não carrega dado sensível além do e-mail.
- Duração de **7 dias**. Atributos: `HttpOnly`, `SameSite=Lax`, `Secure` em produção, `Path=/`.
- O servidor **não guarda estado de sessão**. Para que um cookie de conta excluída pare de valer, ele confere a existência da conta com um **cache curto de 30 s**.
- Consequência conhecida: **trocar a senha não encerra sessões de outros aparelhos** até o cookie expirar.
- Em produção, `SESSION_SECRET` com ao menos 32 caracteres é obrigatório; sem ele o serviço não sobe.

### Confirmação de e-mail e recuperação de senha
- **Confirmação:** ao se cadastrar, a pessoa recebe um link (`#/confirmar?token=…`, válido por 48 horas, uso único). Enquanto não confirma, a conta funciona normalmente; em *Perfil → Conta e dados* aparece "Não confirmado" e o botão **Reenviar** (1 por minuto). A confirmação será exigida para avisos por e-mail.
- **Recuperação:** em "Esqueci a senha" a pessoa informa o e-mail e recebe um link (`#/redefinir?token=…`, 1 hora, uso único). A tela pede a nova senha duas vezes. Abrir o link e trocar a senha também confirma o e-mail.
- **Sem vazar quem tem conta:** o pedido de redefinição responde sempre a mesma mensagem, exista ou não a conta; no máximo um e-mail por minuto por endereço.
- **Tokens:** aleatórios (32 bytes), guardados **só como hash SHA-256** (`account_tokens`), com validade, de uso único; pedir um link novo invalida o anterior. Um token de confirmação não serve para redefinir senha, e vice-versa.
- **Links seguros:** usam `APP_BASE_URL` (nunca o cabeçalho `Host`, o que impede *envenenamento de link*) e levam o token no **fragmento** da URL, que o navegador não envia ao servidor nem a terceiros; a tela tira o token da barra de endereço ao abrir.
- **Provedor de e-mail:** SMTP padrão (`SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`). Em desenvolvimento, sem SMTP, a mensagem é escrita no log do servidor; em produção, sem SMTP, a recuperação fica desligada (503) e a interface avisa. Falha do servidor de e-mail nunca derruba o cadastro.

### Proteções de entrada
- Limite de tentativas de login/cadastro por identidade (`LOGIN_ATTEMPTS_PER_MINUTE`, padrão 5). A identidade é o IP real, lido do `X-Forwarded-For` contando `TRUSTED_PROXY_HOPS` proxies confiáveis a partir do fim (entradas à esquerda são controladas pelo cliente e ignoradas).
- Troca de senha e exclusão pedem a senha atual e passam pelo mesmo limite.

### Dados pessoais
- **Baixar meus dados** (`GET /api/account/export`): arquivo `meus-dados.json` com conta (sem senha), perfil, interesses, biblioteca com etiquetas, listas, análises salvas, relatórios (com versões e histórico), avisos e preferências.
- **Excluir conta** (`DELETE /api/account`): pede a senha, **não tem volta** e apaga a conta e tudo o que ela guardou, chamando `delete_user_data` em cada armazém (biblioteca e listas, análises, relatórios, interesses e avisos, notificações e perfil). Links públicos de listas da pessoa deixam de funcionar.

Mais detalhes de privacidade em [Privacidade e LGPD](../legal/privacidade-e-lgpd.md).

## Limites
- Avisos por e-mail ainda não existem (a infraestrutura de envio está pronta; falta o recurso e o consentimento).
- Trocar a senha ou redefini-la **não encerra** as sessões já abertas em outros aparelhos (cookie sem estado, 7 dias).
- Sem autenticação de dois fatores.
- Limitadores e cotas são em memória, por instância do servidor.

## Arquivos
`account_store.py`, `account_tokens.py`, `account_routes.py`, `routes/recovery.py`, `mailer.py`, `sessions.py`, `web.py` (cookie, rotas de autenticação), `ratelimit.py`. Testes: `tests/test_account.py`, `tests/test_account_store.py`, `tests/test_recovery.py`, `tests/test_sessions.py`, `tests/test_ratelimit.py`.
