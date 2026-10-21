# Configuração

Toda a configuração vem de **variáveis de ambiente**, lidas e validadas em um só lugar (`config.py`). Valores inválidos impedem a subida com mensagem clara (por exemplo, "RATE_LIMIT_PER_MINUTE deve ser um inteiro"). Em desenvolvimento, as variáveis podem ficar em `nexus-science/.env` (ignorado pelo Git).

## Variáveis

### Obrigatórias em produção
| Variável | Descrição |
|---|---|
| `APP_ENV` | `production` liga cookie `Secure`, HSTS e as exigências abaixo. Padrão: `development` |
| `SESSION_SECRET` | Segredo de assinatura das sessões, **mínimo 32 caracteres**. No Render é gerado automaticamente (`generateValue`). Trocá-lo **encerra todas as sessões** |
| `DATABASE_URL` | URL do PostgreSQL. Em produção, sem ela o serviço **não inicia** |

### Para a aba de Administração
| Variável | Descrição |
|---|---|
| `ADMIN_EMAILS` | E-mails (separados por vírgula) das contas que veem a aba **Administração**. Em produção, a conta também precisa ter o e-mail confirmado. Sem ela e sem `ADMIN_TOKEN`, o painel fica desativado |

### Para planos e pagamento (Pix)
| Variável | Descrição |
|---|---|
| `BILLING_ENFORCED` | `1` faz valerem os limites do plano gratuito. Desligado (padrão), todas as contas têm os limites do Pro. Em produção, ligado exige `PIX_KEY` e `PIX_NAME` |
| `PIX_KEY` | Chave Pix que recebe os pagamentos (e-mail, CPF/CNPJ, telefone ou chave aleatória) |
| `PIX_NAME` | Nome do recebedor mostrado no Pix (ASCII, até 25 caracteres) |
| `PIX_CITY` | Cidade do recebedor (padrão `BRASIL`, até 15 caracteres) |
| `PRO_PRICE_CENTS` | Preço do Pro por mês em centavos (padrão 2900, **provisório**) |

O painel de administração e a conciliação usam `ADMIN_TOKEN` (já listado abaixo).

### Para os textos legais (obrigatórias em produção)
| Variável | Descrição |
|---|---|
| `LEGAL_CONTROLLER` | Nome ou razão social do controlador dos dados, exibido nos Termos e na Política. Sem ela (e `LEGAL_CONTACT`), o serviço **não sobe** em produção |
| `LEGAL_CONTACT` | E-mail do encarregado / para solicitações de titulares |
| `LEGAL_FORUM` | Comarca do foro (opcional) |
| `REQUIRE_TERMS` | `1` (padrão em produção) exige aceitar os Termos ao criar a conta; `0` desliga (não recomendado em produção) |

### Para e-mail (confirmação de endereço e recuperação de senha)
| Variável | Descrição |
|---|---|
| `APP_BASE_URL` | URL pública do site, `https://…` sem barra no fim. Base dos links dos e-mails. **Obrigatória em produção se `SMTP_HOST` estiver definido** (o serviço não sobe sem ela) |
| `SMTP_HOST` | Servidor SMTP do provedor de e-mail. Sem ele, em produção, a recuperação de senha fica desligada |
| `SMTP_PORT` | Padrão 587 |
| `SMTP_USER`, `SMTP_PASSWORD` | Credenciais do provedor |
| `SMTP_FROM` | Remetente (ex.: `no-reply@seudominio.com`); obrigatório com `SMTP_HOST` |
| `SMTP_SECURITY` | `starttls` (padrão), `ssl` ou `none` |

Configure SPF, DKIM e DMARC no domínio do remetente (o provedor orienta), senão as mensagens caem no spam.

### Recomendadas
| Variável | Descrição |
|---|---|
| `GROQ_API_KEY` | Chave da Groq para o Laboratório de IA. Sem ela e sem Ollama, o Laboratório responde que está indisponível; o restante funciona |
| `ALERTS_CRON_TOKEN` | Token (≥24 caracteres) que autoriza `POST /api/internal/alerts/run`. Sem ele a rota responde 404 e os avisos só rodam com o site aberto |
| `ADMIN_TOKEN` | Token (≥24 caracteres) para `GET /api/admin/usage`. Sem ele a rota fica desativada |

### Opcionais
| Variável | Padrão | Descrição |
|---|---|---|
| `PORT` | 7860 | Porta do servidor (o Render a define) |
| `DATABASE_PATH` | `accounts.sqlite3` | Arquivo SQLite usado **somente sem** `DATABASE_URL` (desenvolvimento) |
| `OPENALEX_API_KEY` | vazio | Liga a fonte OpenAlex na busca |
| `OPENALEX_MAILTO` | vazio | E-mail de contato enviado ao OpenAlex |
| `NCBI_API_KEY` | vazio | Eleva o limite do PubMed |
| `DISCOVERY_CALLS_PER_MINUTE` | 30 | Buscas/consultas de artigo por identidade |
| `RATE_LIMIT_PER_MINUTE` | 8 | Chamadas ao modelo de linguagem por identidade |
| `LOGIN_ATTEMPTS_PER_MINUTE` | 5 | Tentativas de login, cadastro, troca de senha e exclusão |
| `TRUSTED_PROXY_HOPS` | 1 | Quantos proxies confiáveis estão à frente (para ler o IP real). Com `0`, usa só o IP da conexão |
| `DAILY_TOKEN_BUDGET_GUEST` | 60000 | Cota diária de tokens por visitante (0 = sem limite) |
| `DAILY_TOKEN_BUDGET_USER` | 200000 | Cota diária de tokens por conta (0 = sem limite) |
| `LLM_TEMPERATURE` | 0.2 | Temperatura do modelo (0 a 2) |
| `ENABLE_GENERATIVE_CLINICAL` | desligado | `1/true/yes/on` liga os botões que **geram** dose e conduta por IA. Desligado por padrão por segurança |

## Valores fixos no código (não configuráveis por ambiente)
| Item | Valor | Onde |
|---|---|---|
| Duração da sessão | 7 dias | `sessions.py` |
| Cache de busca / obra | 10 min / 1 h | `discovery.py` |
| Prazo da busca em todas as fontes | 8 s (+1,5 s após 3 respostas) | `discovery.py` |
| Intervalo mínimo por fonte do feed | 3 h | `feed.py` |
| Retenção do feed | 45 dias | `feed.py` |
| Intervalos de alerta | 6 h (automático), 15 min (manual) | `alerts.py` |
| Reconferência de retratação | semanal | `notifications.py` |
| Limites por conta (biblioteca, listas, relatórios…) | ver [Biblioteca](../features/biblioteca-e-listas.md) e [Relatório](../features/relatorio-de-tema.md) | `library_store.py`, `reports.py` |

## Modelos de linguagem
Os modelos disponíveis estão em `pages.MODEL_CHOICES` (GPT-OSS 20B — padrão — e 120B, Qwen 3.6 e 3.8 27B pela Groq, e Llama local pelo Ollama). O Ollama é usado quando o modelo escolhido é o local; o servidor Ollama precisa estar em execução na máquina.

## Exemplo de `.env` para desenvolvimento
```
DATABASE_PATH=accounts.sqlite3
GROQ_API_KEY=<sua chave, opcional>
```
Nunca registre segredos no repositório. Valores de produção ficam apenas no painel do provedor.
