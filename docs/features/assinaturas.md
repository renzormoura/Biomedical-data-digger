# Funcionalidade: Planos, assinatura e pagamento por Pix

## Objetivo
Cobrar pelo produto na fase inicial **sem depender de provedor de pagamento**: a pessoa escolhe um plano, paga um **Pix** e o administrador confere o extrato e **confirma**, o que ativa a assinatura. É propositalmente simples e manual, para descobrir se pagam e quanto antes de integrar um provedor com cobrança automática.

## O que a pessoa vê
- **Planos** (`#/planos`, link no rodapé e em *Perfil → Assinatura*): cartões com preço, limites e o botão **Assinar com Pix**, e a escolha do período (1, 3 ou 12 meses).
- Ao assinar, aparece o **cartão do Pix**: valor exato, código **copia e cola**, chave, recebedor e o identificador do pedido. A pessoa cola o código no app do banco e paga.
- O pedido fica **"Aguardando pagamento"** até o administrador confirmar; depois a conta passa ao plano pago e chega um e-mail ("Sua assinatura foi ativada"). Pedidos em aberto podem ser cancelados.
- **Perfil → Assinatura:** plano, validade, uso (artigos, listas, relatórios) em relação aos limites e o histórico de pedidos.

## Planos e limites
| Plano | Artigos na biblioteca | Listas | Relatórios | Preço |
|---|---:|---:|---:|---|
| Gratuito | 50 | 3 | 1 | R$ 0 |
| Pro | 500 | 50 | 30 | `PRO_PRICE_CENTS` por mês (padrão **provisório** de R$ 29,00; defina o preço real) |
| Max | 2.000 | 200 | 100 | `MAX_PRICE_CENTS` por mês (padrão **provisório** de R$ 49,90; os limites também são provisórios) |

Busca, feed, nota de confiabilidade e Panorama não têm limite em nenhum plano. Os valores de limite estão em `plans.py`.

**Os limites só valem com `BILLING_ENFORCED=1`.** Desligado (padrão), todas as contas têm os limites do Pro (os limites técnicos atuais) e a tela de planos avisa que tudo está liberado. Assim dá para publicar a tela, receber os primeiros pagamentos e só depois ligar a restrição.

Ao atingir um limite, a API responde 409 com a mensagem "O plano Gratuito permite até N artigos… Veja os planos". Salvar de novo um artigo já salvo não ocupa outro lugar. **Assinatura vencida não apaga nada:** a conta volta ao gratuito e os limites passam a valer só para novas gravações.

## Como funciona
1. **Pedido** (`POST /api/billing/requests`): cria `payment_requests` com plano, meses, valor (`preço × meses`, sem desconto por enquanto) e um **identificador** `NXS` + 10 caracteres. Pedidos idênticos pendentes são reaproveitados; no máximo 3 pendentes por conta.
2. **Pix "copia e cola"** (`pix.py`): gera o BR Code estático do Banco Central com chave, nome, cidade, **valor** e o identificador (CRC16-CCITT). Qualquer app de banco paga. É um QR estático: o banco pode ou não mostrar o identificador no extrato.
3. **Conciliação (administrador):** em `#/admin`, com o `ADMIN_TOKEN`, a lista de pedidos pendentes mostra e-mail, plano, valor e identificador. O administrador confere o extrato bancário (valor, data, nome do pagador, identificador quando houver) e clica **Confirmar pagamento**. Isso é sempre um ato humano: nada confirma sozinho.
4. **Ativação:** a confirmação marca o pedido como pago e cria ou **prorroga** a assinatura (30 dias por mês pago, somados ao vencimento atual se o plano for o mesmo), e envia o e-mail de ativação.
5. **Vencimento:** o plano em vigor é o da assinatura enquanto ela não venceu; senão, o gratuito. Não há renovação automática nem cobrança recorrente.
6. **Cortesia e ajustes:** *Dar 30 dias de Pro* e *Remover* no painel (`grant`/`revoke`), por exemplo para testadores e parceiros.

## Administração
Na aba **Administração** (`#/admin`), visível para contas em `ADMIN_EMAILS`; o `ADMIN_TOKEN` continua valendo como acesso de emergência. Ver [Aba de Administração](administracao.md) e a [Referência da API](../api/referencia.md#administração). Procedimento diário sugerido: abrir o painel, conferir os pedidos pendentes contra o extrato, confirmar os que bateram e cancelar os abandonados (mais de alguns dias).

## Dados
Tabelas `subscriptions` (conta, plano, validade) e `payment_requests` (pedidos, com valor, identificador, status e data). **Pedidos confirmados são registro de pagamento (obrigação fiscal) e permanecem mesmo se a conta for excluída**; a assinatura e os pedidos não confirmados são apagados. Ver [Modelo de dados](../arquitetura/dados.md).

## Configuração
`BILLING_ENFORCED`, `PIX_KEY`, `PIX_NAME`, `PIX_CITY`, `PRO_PRICE_CENTS`, `MAX_PRICE_CENTS` e `ADMIN_TOKEN` (ver [Configuração](../operacao/configuracao.md)). Em produção, `BILLING_ENFORCED=1` exige `PIX_KEY` e `PIX_NAME`.

## Limites e próximos passos
- **Conciliação manual:** não escala além de poucas dezenas de pagamentos por semana. O próximo passo natural é um provedor com Pix dinâmico (QR por cobrança) e *webhook* de confirmação (por exemplo Asaas, Pagar.me ou Mercado Pago): `pix.py` e a confirmação manual são substituídos, o resto (planos, assinatura, limites, painel) continua.
- **Cartão, boleto e renovação automática** não existem.
- **Nota fiscal** e recibo são manuais (emitir fora do sistema).
- Sem cupom, desconto por período, plano para equipes nem assentos.
- Sem lembrete de vencimento por e-mail.
- Antes de cobrar: CNPJ ou MEI, conta bancária para a chave Pix, Termos revisados (a seção "Planos e pagamento" é rascunho), preço definido e política de reembolso (CDC art. 49).

## Arquivos
`plans.py`, `billing.py`, `pix.py`, `routes/billing.py`, `routes/context.py` (`plan_for`, `check_limit`), `static/browse.js` (`renderPlans`, `profileSubscription`, `renderAdmin`). Testes: `tests/test_billing.py`, `tests/test_api_contract.py`.
