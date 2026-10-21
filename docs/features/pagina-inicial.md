# Página inicial

O início muda conforme a pessoa: **convidado** vê a vitrine do produto, **quem tem conta** vê o painel de trabalho. A escolha é feita no navegador (`renderHome` em `static/browse.js`), pela sessão: `data-user` e `data-name` no botão da conta, entregues na primeira pintura.

## Convidado: apresentar o produto e levar aos planos
Ordem das seções:
1. **Topo:** frase de valor, busca (campo, seletor de fonte) e exemplos de temas. A busca sem conta continua livre.
2. **Números:** quantas fontes de busca, quantas fontes do feed e os 8 critérios de confiabilidade.
3. **Funcionalidades** (seis cartões) e **confiança e método**, com o exemplo de nota de 0 a 100 (dados fictícios).
4. **Como funciona:** buscar, avaliar e entregar.
5. **Para quem é:** estudantes, pesquisadores e profissionais de saúde.
6. **Planos:** Gratuito, Pro ("Mais escolhido") e Max, lidos de `GET /api/billing/plans` (preço e limites reais). Os botões abrem a janela de criar conta. Se a rota falhar, a seção não aparece.
7. **Chamada final:** "Criar conta grátis", sem cartão.

## Quem tem conta: painel de trabalho
- **"Bem-vindo, Nome"** (primeiro nome) e a data de hoje; sem nome cadastrado, "Bem-vindo de volta". Logo abaixo, a busca.
- **Números da conta:** artigos salvos, listas e relatórios, cada um levando à tela correspondente. Com cobrança ativa (`BILLING_ENFORCED=1`), mostra "x de limite" e uma barra de uso, mais o cartão do plano; sem cobrança ativa os limites e o plano não aparecem, porque todas as contas têm limites do Pro.
- **Primeiros passos:** interesses, perfil de uso, primeiro artigo salvo, primeira lista e primeiro relatório. A lista some quando os cinco estão feitos.
- **Avisos** (até 4 do sininho) e **Últimos salvos** (4 da biblioteca), cada um com orientação quando está vazio.
- **Novidades para você:** até 6 cartões do feed dos interesses; se não houver, as novidades gerais.
- **Atalhos:** os do perfil de uso escolhido, ou os padrões, e o Laboratório de IA.

Os dados vêm em paralelo (`/api/account`, `/api/billing/me`, `/api/alerts`, `/api/library`, `/api/feed`); cada bloco aparece quando o seu chega e uma falha de um deles não derruba os outros.

## Nome da conta
- **Cadastro:** a janela de criar conta pede "Como podemos te chamar?". O campo aparece no primeiro clique em "Criar conta" e o segundo envia. O nome é obrigatório na interface, mas **opcional na API** (`name` em `POST /api/auth/register`), então clientes antigos continuam funcionando.
- **Edição:** Perfil → Conta e dados → Nome (`PUT /api/account/name`).
- **Regras:** 1 a 60 caracteres, espaços repetidos viram um, sem caracteres de controle. Nome inválido no cadastro recusa a criação (nenhuma conta fica pela metade).
- **Onde fica:** tabela `user_names` (`ProfileStore`). `GET /api/auth/me`, `POST /api/auth/login`, `POST /api/auth/register` e `GET /api/account` devolvem `name` (vazio se não houver). Sai junto com a conta na exclusão e entra no arquivo "Baixar meus dados".
