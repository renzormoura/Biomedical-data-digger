# Funcionalidade: Aba de Administração

## Objetivo
Dar a quem administra o produto, **dentro da própria conta**, uma aba para ver todos os usuários e os planos, conferir pagamentos e agir sobre as contas, sem mexer em banco de dados nem em scripts.

## Quem é administrador
- **Pela conta (uso normal):** o e-mail da conta está em `ADMIN_EMAILS` (lista separada por vírgulas, sem diferenciar maiúsculas). Em **produção**, a conta também precisa ter o **e-mail confirmado**; sem isso a aba não aparece e a API recusa. Para criar o primeiro administrador: criar a conta normalmente, confirmar o e-mail e pôr o endereço em `ADMIN_EMAILS` no Render.
- **Por token (emergência e scripts):** `Authorization: Bearer ADMIN_TOKEN`. Serve para chamar a API de fora e para entrar no painel se o e-mail ainda não estiver configurado.
- Sem `ADMIN_EMAILS` e sem `ADMIN_TOKEN`, o painel fica **desativado** (a API responde 404 e a aba não existe).
- Pessoas comuns nunca veem a aba; a rota `GET /api/admin/session` diz à interface se mostra o menu.

## O que há na aba (`#/admin`)
| Aba | Conteúdo |
|---|---|
| **Visão geral** | Contas, com e-mail confirmado, novas em 7 dias, no plano Pro e no gratuito, assinaturas vencendo em 7 dias, suspensas, pagamentos a conferir, receita em 30 dias e total |
| **Usuários** | Tabela com e-mail, plano e validade, e-mail confirmado, uso (biblioteca / listas / relatórios), data de criação e situação; busca por e-mail e paginação (25 por página). Clicar no e-mail abre o detalhe |
| **Pagamentos** | Pedidos Pix pendentes (confirmar com anotação, ou cancelar) e o histórico de pagamentos confirmados |
| **Sistema** | Banco em uso, produção, cobrança ligada, chave Pix, e-mail, aceite de termos, dados legais, administradores configurados e o consumo do Laboratório de IA |

### Ações sobre uma conta (detalhe do usuário)
- **Plano:** dar 30, 90 ou 365 dias de Pro (soma ao vencimento atual) ou remover a assinatura.
- **Enviar link de redefinição de senha** ao e-mail da conta (o administrador nunca vê nem define a senha).
- **Marcar e-mail como confirmado.**
- **Suspender** (com motivo) e **reativar:** a conta suspensa não entra e a sessão aberta deixa de valer na hora; nada é apagado. Quem tenta entrar vê "conta suspensa" (só depois de acertar a senha, para não revelar o estado a quem não é o dono).
- **Excluir conta e dados:** exige digitar o e-mail da conta de novo; apaga tudo (biblioteca, listas, relatórios, interesses, avisos, perfil, tokens, aceite, assinatura e pedidos não confirmados). **Pagamentos confirmados permanecem** (obrigação fiscal). Serve para atender pedido de exclusão feito por e-mail (LGPD) quando a pessoa não consegue entrar.
- Ver o aceite dos termos (versão e data), o motivo da suspensão e o histórico de pagamentos.

## Proteções
- **Administradores não podem ser suspensos nem excluídos por aqui**, nem a própria conta de quem está agindo.
- Toda escrita vai para o log: `admin_action actor=<quem> action=<o quê> target=<conta>` (sem conteúdo de dados).
- Limite de 60 chamadas por minuto por identidade nas rotas de administração; comparação do token em tempo constante.
- A autorização é verificada **em cada requisição** no servidor (e-mail em `ADMIN_EMAILS`); esconder a aba é só conforto. Cookie `HttpOnly`, `SameSite=Lax` e a checagem de origem em escritas protegem de CSRF.
- Não há 2FA ainda: **proteja o e-mail e a senha das contas de administrador** e use poucas.

## Como funciona
`routes/admin.py` (rotas e autorização), `admin_service.py` (consultas de visão geral, lista e detalhe, com contagens em SQL), `account_flags.py` (suspensão), `billing.py` (planos e pagamentos) e `account_routes.make_account_purger` (exclusão compartilhada com o "Excluir minha conta"). Ver [Referência da API](../api/referencia.md#administração).

## Limites
- Sem trilha de auditoria em banco (só log do servidor).
- Sem exportar a lista de usuários, sem filtro por plano ou por situação, sem ações em lote.
- Sem enviar e-mail avulso a usuários e sem personificar a conta de alguém (de propósito).
- Conciliação de pagamentos continua manual (ver [Planos e Pix](assinaturas.md)).

## Testes
`tests/test_admin.py` (administrador por conta e por token, produção exigindo e-mail confirmado, lista, busca, detalhe, suspensão, exclusão, proteção de administradores, link de redefinição), `tests/test_billing.py` e `tests/test_api_contract.py`.
