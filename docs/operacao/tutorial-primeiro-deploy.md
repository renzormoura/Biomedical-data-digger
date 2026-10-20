# Tutorial: colocar o produto no ar, de graça, no Render

Montagem **sem custo nenhum**, o mais parecida possível com a versão paga. Tempo estimado: 1 a 2 horas, fora a espera de verificações de e-mail. Os nomes de botões e limites dos provedores mudam com o tempo: se algo não bater, siga a ideia do passo e consulte a documentação do provedor.

## O desenho gratuito (e o que muda em relação ao pago)
| Peça | Gratuito | Pago (para depois) | Diferença |
|---|---|---|---|
| Serviço web | **Render, plano free** | Render `starter` | O free **dorme** após ~15 min sem acesso; um monitor gratuito acessando o site a cada 5 min o mantém acordado (Parte 6). Memória e CPU menores |
| Banco de dados | **Neon, plano free** (PostgreSQL permanente) | PostgreSQL do Render com backup | O banco gratuito **do Render** expira em 30 dias, por isso usamos o Neon. Limite de 0,5 GB e suspende quando ocioso (a primeira consulta leva 1 a 2 s). Histórico de recuperação curto |
| E-mail | **Brevo** (ou Gmail), plano free | Qualquer provedor SMTP | Limite diário de envios (centenas) |
| Domínio | `*.onrender.com` | Domínio próprio | Nenhuma |
| Rotina de avisos e feed | **GitHub Actions** | Igual | Nenhuma |
| Código | GitHub **privado** (grátis) | Igual | Nenhuma |
| Pix, Termos, painel de administração | Igual | Igual | Nenhuma |

Tudo é o mesmo código: para ir ao pago basta trocar o plano e a `DATABASE_URL` (Parte 9).

## Antes de começar
Reúna: o repositório no GitHub (pode ser privado), o e-mail que será o administrador, a chave Pix e o nome do recebedor (pode ficar para depois), seu nome ou razão social e um e-mail de contato (obrigatórios nos Termos). Gere dois segredos de 32 caracteres e guarde num gerenciador de senhas (um para `ALERTS_CRON_TOKEN`, outro para `ADMIN_TOKEN`):
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Parte 1: banco de dados gratuito (Neon)
1. Crie conta em **neon.tech** (pode entrar com o GitHub).
2. **Create project**: nome `biomedical-data-digger`, região **AWS US East (N. Virginia)** (a mesma região do serviço no Render, para ficar rápido).
3. Na tela do projeto, abra **Connect** (ou *Connection Details*) e copie a **connection string**. Dois cuidados:
   - Use a conexão **direta**, **sem** `-pooler` no endereço (o `pooler` pode atrapalhar o driver).
   - Ela deve terminar com `?sslmode=require`. Algo como `postgresql://usuario:senha@ep-xxxx.us-east-1.aws.neon.tech/neondb?sslmode=require`.
4. Guarde essa URL (é a sua `DATABASE_URL`; é uma senha, não a compartilhe).
5. (Opcional) Confirme que o banco está pronto, no seu computador, na pasta do projeto:
   ```bash
   DATABASE_URL="postgresql://..." python scripts/verificar_banco.py
   ```
   No Windows PowerShell: `$env:DATABASE_URL="postgresql://..."; python scripts/verificar_banco.py`. Deve terminar com **"Banco pronto."**

## Parte 2: criar o serviço no Render (gratuito)
1. Em **render.com**, crie a conta (pode entrar com o GitHub) e clique em **New + → Blueprint**.
2. Conecte o GitHub e **autorize o repositório** (se for privado, marque-o na lista).
3. Escolha o ramo `main`. O Render lê o `render.yaml`, que já está no plano **free** e cria só o serviço web.
4. O Render pede as variáveis marcadas "preencher no painel". Você pode preencher agora (Parte 3) ou depois. Clique **Apply**. O primeiro deploy falha enquanto faltarem as variáveis obrigatórias: é esperado.

## Parte 3: variáveis de ambiente
No serviço web: **Environment**. Preencha estas:

| Variável | O que colocar | Obrigatória? |
|---|---|---|
| `DATABASE_URL` | A URL do Neon (Parte 1) | **Sim** |
| `LEGAL_CONTROLLER` | Seu nome ou razão social | **Sim** (sem ela o serviço não sobe) |
| `LEGAL_CONTACT` | E-mail para pedidos de privacidade | **Sim** |
| `APP_BASE_URL` | `https://` + o endereço do serviço (aparece no topo da página do serviço, algo como `https://biomedical-data-digger.onrender.com`), sem barra no fim | **Sim**, se usar e-mail |
| `ADMIN_EMAILS` | O e-mail da sua conta de administrador | Recomendada |
| `ADMIN_TOKEN`, `ALERTS_CRON_TOKEN` | Os dois segredos gerados | Recomendadas |
| `PIX_KEY`, `PIX_NAME`, `PRO_PRICE_CENTS` | Chave Pix, nome do recebedor (até 25 caracteres, sem acento) e preço em centavos (`2900` = R$ 29,00) | Para cobrar |
| `BILLING_ENFORCED` | Deixe `0` | Não |
| `GROQ_API_KEY` | Chave da Groq (tem plano gratuito), se quiser o Laboratório de IA | Não |

`SESSION_SECRET` é gerada sozinha. Depois de salvar, o Render reinicia o serviço.

## Parte 4: e-mail grátis (confirmação e recuperação de senha)
**Opção A: Brevo (recomendada para começar).**
1. Crie conta em **brevo.com** (plano gratuito).
2. Em *SMTP & API → SMTP*, copie o servidor (`smtp-relay.brevo.com`), a porta (587), o **login** e gere uma **chave SMTP**.
3. Em *Senders*, cadastre e **verifique** o e-mail remetente (chega um link na caixa dele). Quando tiver domínio próprio, autentique o domínio (SPF/DKIM) para os e-mails não caírem no spam.
4. No Render: `SMTP_HOST=smtp-relay.brevo.com`, `SMTP_PORT=587`, `SMTP_USER` = login do Brevo, `SMTP_PASSWORD` = chave SMTP, `SMTP_FROM` = o remetente verificado.

**Opção B: Gmail (para testar).** Ative a verificação em duas etapas na conta Google, crie uma **senha de app** e use `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER` = seu Gmail, `SMTP_PASSWORD` = a senha de app, `SMTP_FROM` = seu Gmail. Serve para poucas pessoas; para público, prefira o Brevo com domínio.

> Sem `SMTP_HOST`, em produção, a recuperação de senha fica desligada. Você ainda administra com o `ADMIN_TOKEN`.

## Parte 5: primeiro acesso e conta de administrador
1. Abra o endereço do serviço (a primeira abertura leva até um minuto). Teste `/healthz`: deve mostrar `{"status":"ok"}`.
2. **Entrar → Criar conta** com **exatamente** o e-mail de `ADMIN_EMAILS` e marque o aceite dos Termos.
3. Clique no link do e-mail de confirmação. Em produção, a aba **Administração** só aparece para administradores com e-mail confirmado.
4. Recarregue. Se a aba não aparecer, abra `#/admin` e entre com o `ADMIN_TOKEN`; em **Usuários** marque o seu e-mail como confirmado.

## Parte 6: manter o serviço acordado (grátis)
O plano free do Render dorme sem visitas. Para evitar a lentidão da primeira visita:
1. Crie conta em **uptimerobot.com** (plano gratuito).
2. **Add New Monitor**: tipo *HTTP(s)*, URL `https://SEU-SERVICO.onrender.com/healthz`, intervalo de **5 minutos**.
3. Com isso o serviço fica sempre acordado (os 750 horas gratuitas por mês do Render cobrem um serviço ligado o mês todo).

Sem o monitor, tudo funciona, só que a primeira visita depois de um tempo parado demora cerca de um minuto e a memória do servidor (caches e limites de uso) zera a cada despertar.

## Parte 7: avisos e feed agendados (GitHub Actions, grátis)
1. No GitHub: **Settings → Secrets and variables → Actions → New repository secret**.
2. Crie `APP_URL` (o endereço do site, com `https://` e sem barra no fim) e `ALERTS_CRON_TOKEN` (o **mesmo** valor do Render).
3. Em **Actions → Alertas agendados → Run workflow**, rode uma vez para conferir. Depois roda sozinho a cada 6 horas (poucas execuções por mês, dentro do limite gratuito do GitHub).

## Parte 8: receber por Pix
1. Confira `PIX_KEY`, `PIX_NAME` e `PRO_PRICE_CENTS`.
2. Em **Planos**, crie um pedido de teste e veja o código "copia e cola" (abra no app do banco sem pagar, só para conferir).
3. Em **Administração → Pagamentos**, o pedido aparece pendente. Quando um pagamento de verdade cair, confira o extrato e clique **Confirmar pagamento**.
4. Só mude `BILLING_ENFORCED` para `1` quando quiser que os limites do plano gratuito valham.

## Parte 9: quando houver receita (subir para o pago)
1. **Banco:** crie o PostgreSQL pago (no Render ou outro), troque a `DATABASE_URL` e rode `scripts/verificar_banco.py`. Para levar os dados do Neon, faça `pg_dump` do Neon e restaure no novo banco (o Neon também oferece exportação).
2. **Serviço:** em *Settings → Instance Type*, escolha um plano pago (sempre ligado, mais memória) e desligue o monitor do UptimeRobot.
3. **Domínio próprio:** *Custom Domains* no serviço, crie o `CNAME` no DNS, depois atualize `APP_BASE_URL` e o segredo `APP_URL` do GitHub e autentique o domínio no provedor de e-mail.
4. Se preferir tudo no Render, aplique o `render.pago.yaml` (serviço + banco com backup) em vez do `render.yaml`.

## Lista de conferência antes de divulgar
- [ ] `/healthz` responde `ok` e o monitor está ativo
- [ ] Cadastro, login, busca e página de um artigo funcionam
- [ ] E-mail de confirmação chega (fora do spam) e "Esqueci a senha" funciona
- [ ] Você vê a aba **Administração**
- [ ] Termos e Política mostram o seu nome e contato (sem "[a definir]")
- [ ] Os textos legais foram revisados por um advogado
- [ ] Você sabe restaurar/exportar o banco (no plano gratuito, **faça cópias do banco com frequência**: exportação do Neon ou `pg_dump`)
- [ ] Repositório do GitHub privado
- [ ] Segredos só no gerenciador de senhas e nos painéis (nunca no código nem em conversas)

## Limites do modelo gratuito (seja honesto com você mesmo)
- **Sem backup robusto:** o Neon gratuito guarda só um histórico curto. Exporte o banco regularmente enquanto houver usuários reais.
- **Desempenho modesto:** CPU e memória pequenas; ótimo para começar e para dezenas de usuários, não para picos.
- **Reinícios:** o Render pode reiniciar o serviço; sessões continuam válidas (o cookie é assinado), mas caches e limites de uso zeram.
- **Limites de uso dos provedores** (envios de e-mail por dia, tamanho do banco) podem mudar: confira nas páginas deles.

## Problemas comuns
| Sintoma | Causa provável e solução |
|---|---|
| "Defina LEGAL_CONTROLLER e LEGAL_CONTACT" | Faltam essas variáveis |
| Falha citando `APP_BASE_URL` | Com `SMTP_HOST` definido, ela precisa começar com `https://` |
| Falha ao conectar no banco | Confira a `DATABASE_URL` (conexão direta, `?sslmode=require`); no Neon, o banco acorda em 1 a 2 segundos na primeira consulta |
| E-mails não chegam | Confira `SMTP_*`, o remetente verificado no Brevo e os logs ("Falha ao enviar e-mail") |
| A aba Administração não aparece | E-mail diferente do de `ADMIN_EMAILS` ou ainda não confirmado: use o `ADMIN_TOKEN` em `#/admin` |
| Primeira visita lenta | O serviço dormiu: configure o monitor (Parte 6) |

Mais detalhes: [Implantação](implantacao.md), [Configuração](configuracao.md), [Rotinas agendadas](rotinas-agendadas.md) e [Runbook](runbook.md).
