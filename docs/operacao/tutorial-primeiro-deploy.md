# Tutorial: colocar o produto no ar no Render, do zero

Passo a passo para quem nunca fez. Tempo estimado: 1 a 2 horas, fora a espera de verificações de e-mail e domínio. Os nomes de botões e planos no Render e nos provedores mudam com o tempo: se algo não bater, siga a ideia do passo e consulte a documentação do provedor.

## Antes de começar (reúna isto)
| Item | Para quê |
|---|---|
| Conta no GitHub com o repositório | O Render lê o código de lá. O repositório **pode ser privado** |
| Cartão de crédito | Planos pagos do Render (serviço web e banco) |
| Um e-mail seu para ser administrador | Será o e-mail da sua conta de administrador |
| Chave Pix e o nome do recebedor | Para receber os pagamentos (pode deixar para depois) |
| Nome ou razão social e um e-mail de contato | Aparecem nos Termos de Uso e na Política de Privacidade (obrigatórios em produção) |
| Um provedor de e-mail (SMTP) | Confirmação de e-mail e recuperação de senha (veja a Parte 3) |
| Um domínio (opcional no começo) | Endereço próprio, como `app.seudominio.com.br` |

Gere dois segredos de 32 caracteres e guarde num gerenciador de senhas (um para `ALERTS_CRON_TOKEN`, outro para `ADMIN_TOKEN`):
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Parte 1: criar o serviço e o banco com o Blueprint
1. Entre em **render.com** e crie uma conta (pode entrar com o GitHub).
2. No painel, clique **New +** e depois **Blueprint**.
3. Conecte o GitHub quando pedir e **autorize o acesso ao repositório** `Biomedical-data-digger` (se for privado, marque-o na lista de repositórios permitidos).
4. Escolha o repositório e o ramo `main`. O Render lê o arquivo `render.yaml` e mostra o que vai criar: **um banco PostgreSQL** (`biomedical-data-digger-db`) e **um serviço web** (`biomedical-data-digger`).
5. Confira os **planos** que ele propõe. O arquivo pede serviço `starter` (sempre ligado) e banco `basic-256mb`. Se o nome do plano tiver mudado, escolha o equivalente pago mais barato (nunca o gratuito: o serviço dorme e o banco gratuito expira).
6. O Render pede os valores das variáveis marcadas como "preencher no painel". Pode preencher agora ou depois (Parte 2). Clique **Apply**/**Create**. O primeiro deploy vai falhar ou demorar enquanto faltar variável obrigatória: é esperado.

## Parte 2: variáveis de ambiente
No serviço web: **Environment**. Preencha (ou confira) estas variáveis. Depois de alterar, o Render reinicia o serviço.

| Variável | O que colocar | Obrigatória? |
|---|---|---|
| `LEGAL_CONTROLLER` | Seu nome ou razão social (ex.: `Empresa Exemplo Ltda.`) | **Sim**, sem ela o serviço não sobe |
| `LEGAL_CONTACT` | E-mail para solicitações de privacidade (ex.: `privacidade@seudominio.com.br`) | **Sim** |
| `LEGAL_FORUM` | Comarca (ex.: `São Paulo/SP`) | Não |
| `ADMIN_EMAILS` | O e-mail da sua conta de administrador (vários, separados por vírgula) | Recomendada |
| `ADMIN_TOKEN` | Um dos segredos gerados acima | Recomendada (acesso de emergência) |
| `ALERTS_CRON_TOKEN` | O outro segredo gerado | Recomendada (avisos e feed agendados) |
| `APP_BASE_URL` | O endereço do site com `https://` e sem barra no fim (ex.: `https://biomedical-data-digger.onrender.com`) | **Sim**, se for usar e-mail |
| `PIX_KEY` | Sua chave Pix | Para cobrar |
| `PIX_NAME` | Nome do recebedor, até 25 caracteres, sem acento | Para cobrar |
| `PIX_CITY` | Sua cidade em maiúsculas (ex.: `SAO PAULO`) | Não (padrão `BRASIL`) |
| `PRO_PRICE_CENTS` | Preço mensal do Pro em centavos (`2900` = R$ 29,00) | Defina o preço real |
| `BILLING_ENFORCED` | Deixe `0` no começo. Só mude para `1` quando quiser que os limites do plano gratuito valham | Não |
| `GROQ_API_KEY` | Chave da Groq, se quiser o Laboratório de IA | Não |

Já vêm prontas pelo Blueprint: `DATABASE_URL` (do banco criado), `SESSION_SECRET` (gerado), `APP_ENV=production`, `PYTHON_VERSION`.

## Parte 3: e-mail (confirmação e recuperação de senha)
O produto envia e-mail por **SMTP padrão**, então serve qualquer provedor (Resend, Brevo, Amazon SES, Mailgun, Postmark, Google Workspace...). Escolha um e siga o roteiro dele.

1. Crie conta no provedor e **verifique o seu domínio** (ou, para testar, o seu e-mail remetente).
2. No painel DNS do seu domínio, adicione os registros que o provedor mostrar: **SPF**, **DKIM** e, de preferência, **DMARC**. Sem isso, os e-mails caem no spam.
3. Crie as credenciais SMTP no provedor. Você vai precisar de: servidor (host), porta (normalmente 587), usuário e senha.
4. No Render, preencha:
   - `SMTP_HOST` = servidor do provedor
   - `SMTP_PORT` = `587` (ou o que o provedor indicar)
   - `SMTP_USER` e `SMTP_PASSWORD` = as credenciais
   - `SMTP_FROM` = o remetente verificado (ex.: `no-reply@seudominio.com.br`)
   - `SMTP_SECURITY` = `starttls` (padrão); use `ssl` se o provedor mandar usar a porta 465
5. Salve. Quando o serviço reiniciar, crie uma conta de teste e veja se chega o e-mail de confirmação.

> Sem `SMTP_HOST`, em produção, a recuperação de senha fica desligada e a tela avisa. Você ainda consegue administrar com o `ADMIN_TOKEN`.

## Parte 4: conferir que o banco está pronto
O serviço cria as tabelas sozinho na subida. Se quiser conferir pelo seu computador (opcional):
1. No Render, abra o banco e copie a **External Database URL** (use só para isso e não a compartilhe).
2. No seu computador, na pasta do projeto:
   ```bash
   DATABASE_URL="postgresql://..." python scripts/verificar_banco.py
   ```
   No Windows PowerShell: `$env:DATABASE_URL="postgresql://..."; python scripts/verificar_banco.py`.
3. A saída deve terminar com **"Banco pronto."**
4. Em *Backups* do banco no Render, confirme que o backup automático está ativo no seu plano.

## Parte 5: primeiro acesso e a conta de administrador
1. Abra o endereço do serviço (algo como `https://biomedical-data-digger.onrender.com`). A primeira abertura pode demorar um pouco. Teste `/healthz`: deve mostrar `{"status":"ok"}`.
2. Clique em **Entrar → Criar conta** usando **exatamente** o e-mail que você pôs em `ADMIN_EMAILS`. Marque o aceite dos Termos.
3. Abra o e-mail de confirmação e clique no link. Em produção a aba de administração **só aparece para administradores com e-mail confirmado**.
4. Entre de novo (ou recarregue). O menu passa a mostrar **Administração**. Se não aparecer, veja a lista de problemas abaixo.

## Parte 6: avisos e feed agendados (GitHub Actions)
Para o sininho e o feed se atualizarem mesmo sem ninguém no site:
1. No GitHub, no repositório: **Settings → Secrets and variables → Actions → New repository secret**.
2. Crie `APP_URL` (o endereço do site, com `https://` e sem barra no fim) e `ALERTS_CRON_TOKEN` (o **mesmo** valor que está no Render).
3. Em **Actions → Alertas agendados → Run workflow**, rode uma vez à mão e confira que terminou com sucesso.

## Parte 7: domínio próprio (opcional)
1. No serviço web, **Settings → Custom Domains → Add**, digite o domínio (ex.: `app.seudominio.com.br`).
2. Crie no DNS do domínio o registro que o Render mostrar (normalmente um `CNAME`). Espere a verificação e o certificado HTTPS ficarem prontos.
3. Atualize `APP_BASE_URL` e o segredo `APP_URL` do GitHub para o novo endereço.

## Parte 8: receber pagamentos por Pix
1. Confirme que `PIX_KEY`, `PIX_NAME` e `PRO_PRICE_CENTS` estão corretos.
2. Em **Planos**, crie um pedido de teste de uma conta sua e pague o valor (ou apenas confira que o código "copia e cola" abre certo no app do banco, sem pagar).
3. Em **Administração → Pagamentos**, o pedido aparece como pendente. Confira o extrato do banco e clique **Confirmar pagamento**: a assinatura é ativada e a pessoa recebe e-mail.
4. Quando estiver tudo certo e você quiser que os limites do plano gratuito passem a valer, mude `BILLING_ENFORCED` para `1`.

## Lista de conferência antes de divulgar
- [ ] `/healthz` responde `ok`
- [ ] Cadastro, login, busca e página de um artigo funcionam
- [ ] E-mail de confirmação chega (fora do spam) e o "Esqueci a senha" funciona
- [ ] Você vê a aba **Administração** com a sua conta
- [ ] Termos e Política abrem e mostram o seu nome e contato (sem "[a definir]")
- [ ] Os textos legais foram revisados por um advogado
- [ ] Backup do banco ativo e restauração testada
- [ ] Repositório do GitHub privado
- [ ] Segredos guardados num gerenciador de senhas (nunca no código nem em conversas)

## Problemas comuns
| Sintoma | Causa provável e solução |
|---|---|
| Deploy falha com "Defina LEGAL_CONTROLLER e LEGAL_CONTACT" | Faltam essas variáveis. Preencha e reinicie |
| Falha dizendo `APP_BASE_URL … obrigatória` | Com `SMTP_HOST` definido, `APP_BASE_URL` precisa começar com `https://` |
| Falha dizendo `SESSION_SECRET` | Era para ser gerada pelo Blueprint; se criou o serviço à mão, defina uma com 32+ caracteres |
| Falha ao conectar no banco | Banco e serviço precisam estar na **mesma região**; use a URL interna do banco |
| A aba Administração não aparece | O e-mail da conta não é igual ao de `ADMIN_EMAILS`, ou o e-mail ainda não foi confirmado. Use o `ADMIN_TOKEN` em `#/admin` para entrar e marcar o e-mail como confirmado em **Usuários** |
| E-mails não chegam | Confira `SMTP_*`, o remetente verificado e os registros SPF/DKIM; veja os logs do serviço por "Falha ao enviar e-mail" |
| A primeira visita demora | Plano gratuito dormindo; no plano `starter` isso não ocorre |
| Painel diz "desativado" | Faltam `ADMIN_EMAILS` e `ADMIN_TOKEN` |

Mais detalhes: [Implantação](implantacao.md), [Configuração](configuracao.md), [Rotinas agendadas](rotinas-agendadas.md) e [Runbook](runbook.md).
