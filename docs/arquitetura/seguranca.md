# Segurança

Resumo dos controles existentes, o que cada um protege e o que **não** cobre. Complementa a política de divulgação em [SECURITY.md](../../SECURITY.md) e o [ADR-005](../adrs/ADR-005-seguranca-e-fidelidade.md).

## Modelo de ameaças (resumido)
| Ativo | Ameaça | Controle |
|---|---|---|
| Contas e dados pessoais | Roubo de credenciais, sessão forjada, acesso entre contas | PBKDF2 (600 mil iterações), cookie `HttpOnly` assinado, `Secure` em produção, filtro por dono em todas as consultas |
| Servidor e rede interna | SSRF por URL informada, entidades XML maliciosas | `security.safe_get`, `xmlutil` |
| Usuários | XSS, clickjacking, vazamento por referência | CSP restrita, `X-Frame-Options: DENY`, `Referrer-Policy: same-origin`, texto externo inserido como texto |
| Orçamento de IA e fontes externas | Abuso, raspagem, custo | Limitadores de taxa, cotas diárias de tokens, limites de tamanho |
| Fidelidade do conteúdo | Alucinação, prompt injection | Núcleo sem IA, verificação de números, defesa de injeção, rótulos |
| Disponibilidade | Dependência de fontes lentas | Prazos, isolamento de falhas, cache |

## Autenticação e sessão
- Senhas: PBKDF2-HMAC-SHA256, 600.000 iterações, sal de 32 bytes, 8 a 128 caracteres. O hash nunca sai da API.
- Sessão: cookie `nexus_session` = `usuário.expiração.assinatura` (HMAC-SHA256 com `SESSION_SECRET`), 7 dias, `HttpOnly`, `SameSite=Lax`, `Secure` em produção. Em produção `SESSION_SECRET` com ≥32 caracteres é obrigatório.
- Cookie de conta excluída para de valer em até 30 s (verificação de existência com cache).
- **Recuperação de senha e confirmação de e-mail:** tokens aleatórios de 32 bytes, guardados só como hash SHA-256, de uso único, com validade (1 h e 48 h) e por finalidade; resposta idêntica para contas existentes e inexistentes; no máximo um e-mail por minuto por endereço e limite por IP; links montados com `APP_BASE_URL` (nunca `Host`) e token no fragmento da URL. Senha fraca não gasta o link.
- **Limitações conhecidas:** sem 2FA; trocar ou redefinir a senha não encerra as sessões em outros aparelhos. A latência do `forgot` difere um pouco entre conta existente (envia e-mail) e inexistente (não envia): o conteúdo da resposta é idêntico, mas o tempo pode vazar a existência (risco baixo, aceito).

## Cabeçalhos e política de conteúdo
Aplicados a **todas** as respostas pelo middleware (`web.py`):
```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:;
  font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: same-origin
X-Frame-Options: DENY
Permissions-Policy: camera=(), microphone=(), geolocation=()
Strict-Transport-Security: max-age=31536000; includeSubDomains   (somente em produção)
Cache-Control: no-store (em /api/) · public, max-age=3600 (em /static/)
```
- **CSRF:** requisições `POST/PUT/PATCH/DELETE` com cabeçalho `Origin` de outro host recebem 403; o cookie é `SameSite=Lax`.
- Documentação interativa da API (`/docs`, `/redoc`, `/openapi.json`) **desativada**.

## Entrada e saída
- Todas as entradas são validadas na borda (modelos Pydantic com tamanhos máximos e `Query` com limites). Erros de domínio viram mensagens seguras; erros inesperados viram "Erro interno" e vão só para o log.
- **Markdown seguro:** `markdown_lite` escapa todo o texto antes de aplicar marcação.
- **Texto externo** (resumos, feeds, notícias) nunca vira HTML na interface; links só `http(s)`.
- **Feed:** XML sem entidades externas (`xmlutil`), limite de 3 MB por feed, trecho limitado a 300 caracteres e sem marcação.

## Proteção de rede (SSRF)
`security.safe_get` é usado onde o servidor busca URLs informadas por pessoas. A cada salto de redirecionamento aplica: apenas `http/https`, rejeição de hosts que resolvem para endereços não públicos (loopback, redes privadas, metadados de nuvem), limite de redirecionamentos e de bytes lidos (5 MB). **Limitação:** a validação de DNS e a conexão são etapas separadas, então um atacante que controle o DNS poderia tentar *DNS rebinding*; mitigar por completo exige fixar o IP na conexão.

## Limites de uso e cotas
| Controle | Padrão | Variável |
|---|---|---|
| Buscas e consultas de artigo por identidade | 30/min | `DISCOVERY_CALLS_PER_MINUTE` |
| Chamadas ao modelo de linguagem por identidade | 8/min | `RATE_LIMIT_PER_MINUTE` |
| Tentativas de login/cadastro por IP | 5/min | `LOGIN_ATTEMPTS_PER_MINUTE` |
| Leitura de listas públicas por identidade | limitador próprio | — |
| Rotina agendada | 10/min | — |
| Cota diária de tokens | 60 mil (visitante) / 200 mil (conta) | `DAILY_TOKEN_BUDGET_GUEST` / `_USER` |

A identidade é `u:<e-mail>` para quem tem conta e `ip:<ip>` para visitantes; o IP vem do `X-Forwarded-For` contando `TRUSTED_PROXY_HOPS` proxies confiáveis a partir do fim. **Os limitadores e cotas ficam em memória do processo.**

## Administração
A aba e a API de administração aceitam (a) conta cujo e-mail está em `ADMIN_EMAILS` (em produção, com e-mail confirmado) ou (b) `Bearer ADMIN_TOKEN`. A autorização é conferida **no servidor em cada requisição**; a interface só esconde o menu. Administradores não podem ser suspensos nem excluídos pela API; exclusão exige digitar o e-mail; toda escrita é registrada em log (`admin_action`). Detalhes em [Aba de Administração](../features/administracao.md). **Risco principal:** conta de administrador comprometida = acesso a dados de todos; sem 2FA ainda, use e-mails dedicados, senhas fortes e o mínimo de administradores.

## Rotas protegidas por token
- `POST /api/internal/alerts/run`: `Authorization: Bearer <ALERTS_CRON_TOKEN>` (≥24 caracteres), comparação em tempo constante; sem o token configurado, responde 404.
- `GET /api/admin/usage`: `Bearer <ADMIN_TOKEN>` (≥24 caracteres); sem o token, desativada.

## Segurança de IA
- **Prompt injection:** `injection.py` remove do texto-fonte frases em formato de ordem ao modelo e avisa a pessoa; o texto-fonte entra delimitado por marcadores. É heurística: a avaliação com modelo real mostrou que só o prompt falha em ~20% das tentativas, e a defesa em código reduz, mas não elimina, o risco.
- **Fidelidade:** `grounding.py` confere, sem outro LLM, que números da resposta existem no título/resumo; prompts exigem "somente informações explicitamente descritas no artigo"; botões de dose/conduta são bloqueados sem indícios no resumo e os geradores clínicos ficam desligados por padrão (`ENABLE_GENERATIVE_CLINICAL`).
- **Privacidade do consumo:** o registro de uso guarda só contagens, nunca conteúdo ou identificação.

## Segredos e configuração
- Segredos só em variáveis de ambiente (`GROQ_API_KEY`, `DATABASE_URL`, `SESSION_SECRET`, `ADMIN_TOKEN`, `ALERTS_CRON_TOKEN`, chaves de OpenAlex e NCBI). `.env` e `*.pem` estão no `.gitignore`. Nada de segredo é registrado em log.
- O produto **não carrega nenhum recurso de terceiros no navegador** (CSP), o que também evita rastreadores.

## Dependências
- Versões fixadas em `requirements.txt`; auditoria de dependências no CI (`pip-audit`, não bloqueante).
- CI roda lint, tipos, testes com cobertura mínima de 80% e testes de front-end em Python 3.10 e 3.11.

## Pendências de segurança conhecidas
1. Revisão de segurança externa antes do lançamento comercial.
2. 2FA e invalidação de sessões ao trocar ou redefinir a senha (a recuperação por e-mail já existe).
3. Limitadores e cotas compartilhados (Redis ou banco) antes de rodar mais de uma instância.
4. Mitigação completa de DNS rebinding.
5. Rotação documentada de segredos (hoje manual).
