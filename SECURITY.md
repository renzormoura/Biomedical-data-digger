# Política de segurança

## Reportar uma vulnerabilidade
Se você encontrou uma falha de segurança no Lastro, **não abra uma issue pública** nem divulgue detalhes. Envie um relato privado ao responsável pelo projeto (canal de contato de segurança: **[definir e-mail dedicado, por exemplo security@seu-dominio]**) com:

- descrição do problema e impacto;
- passos para reproduzir (rota, entrada, ambiente);
- se houve acesso a dados de outras pessoas;
- sua forma de contato.

## O que esperar
| Etapa | Prazo-alvo |
|---|---|
| Confirmação de recebimento | 3 dias úteis |
| Avaliação inicial e severidade | 7 dias |
| Correção ou plano de mitigação | conforme a severidade (críticas: o mais rápido possível) |

Pedimos que você aguarde a correção antes de divulgar e que use apenas contas e dados de teste. Não acesse, altere nem apague dados de terceiros e não faça testes de negação de serviço.

## Escopo
Dentro do escopo: o serviço em produção, as rotas em [docs/api/referencia.md](docs/api/referencia.md), autenticação e sessão, isolamento entre contas, tratamento de entrada, cabeçalhos de segurança, rotas protegidas por token, exposição de segredos.

Fora do escopo: falhas de provedores terceiros (Render, GitHub, Groq, fontes de artigos), engenharia social, ataques físicos e relatórios automatizados sem demonstração de impacto.

## Controles existentes
Resumo em [docs/arquitetura/seguranca.md](docs/arquitetura/seguranca.md) (senhas PBKDF2, sessão assinada e `HttpOnly`, CSP restritiva, proteção SSRF, limites de taxa e cotas, defesa contra injeção de prompt).

## Segredos
Nunca versione segredos (`.env`, chaves, tokens). Se uma credencial vazar, **revogue e troque imediatamente** (Render, GitHub Secrets, Groq, banco) e, se necessário, troque `SESSION_SECRET` para encerrar todas as sessões.
