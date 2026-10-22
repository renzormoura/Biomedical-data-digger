# Página inicial

O início muda conforme a pessoa: **convidado** vê a vitrine do produto, **quem tem conta** vê o painel de trabalho. A escolha é feita no navegador (`renderHome` em `static/browse.js`), pela sessão: `data-user` e `data-name` no botão da conta, entregues na primeira pintura.

## Convidado: a jornada (a rolagem conta o produto)
A vitrine é uma página que se conta rolando:
1. **Topo:** "Da pergunta ao relatório.", com o título entrando linha a linha, a busca de verdade (campo e seletor de fonte), exemplos de temas e o convite "Role para ver como funciona".
2. **Jornada:** uma seção alta (≈330% da tela) com um **palco fixo**. À esquerda, três passos (buscar, avaliar, entregar), de que só o atual fica aceso; à direita, um cartão que se transforma em três cenas: a **busca** (cinco fontes que surgem e três resultados com nota), a **nota** (anel que se preenche e critérios que aparecem um a um) e o **relatório** (linhas que se escrevem e os botões de exportação). Uma barra lateral mostra o progresso. Os dados do cartão são **fictícios**, como o exemplo de nota que já existia.
3. **Números** que contam de zero quando entram na tela (fontes de busca, fontes do feed, critérios), **para quem é**, **planos** (Gratuito, Pro e Max, lidos de `GET /api/billing/plans`) e a chamada final "Criar conta grátis".

No celular, só o passo atual aparece acima do cartão, a seção fica um pouco mais curta e o cartão esconde o item que não cabe; nada rola para o lado.

## Quem tem conta: painel em blocos
- **"Bem-vindo, Nome"** e a data de hoje; sem nome cadastrado, "Bem-vindo de volta". Logo abaixo, a busca.
- **Blocos** (grade de 4 colunas no computador, 2 no celular), cada um entrando com atraso e com um brilho que segue o cursor:
  - **Artigos salvos, listas e relatórios:** números que contam de zero. Com cobrança ativa (`BILLING_ENFORCED=1`), mostram "de limite" e uma barra de uso; sem cobrança, só o número.
  - **Primeiros passos:** anel de progresso (interesses, perfil de uso, primeiro artigo, primeira lista, primeiro relatório) e o próximo passo; quando os cinco acabam, o bloco vira "Tudo pronto" com um convite ao Laboratório de IA.
  - **Avisos** (até 3 do sininho; o sino balança e ganha um selo quando há não lidos) e **Últimos salvos** (3 da biblioteca, com um leque de cartões que abre ao passar o mouse).
  - **Consta no SUS?** consulta rápida de medicamento, cirurgia, exame ou técnica (ver [Disponibilidade no SUS](disponibilidade-sus.md)).
  - **Atalhos:** os do perfil de uso escolhido, o Laboratório de IA e, com cobrança ativa, o plano atual.
- **Novidades para você:** até 6 cartões do feed dos interesses (ou as gerais), abaixo dos blocos.

Os dados vêm em paralelo (`/api/account`, `/api/billing/me`, `/api/alerts`, `/api/library`, `/api/feed`); cada bloco aparece quando o seu chega e uma falha de um deles não derruba os outros.

## O mesmo estilo em todas as telas
- **Entrada animada:** cada tela do navegador de artigos entra subindo e aparecendo, com os blocos em sequência; resultados da busca, cartões do feed, números do perfil e do painel de administração, e planos entram escalonados. No Laboratório de IA, cada área entra suavemente ao ser aberta.
- **Brilho que segue o cursor** nos cartões, blocos e planos (só com mouse; no toque não existe).
- **Paleta de comandos (Ctrl/Cmd+K, ou o botão "Comandos" no topo, só o ícone em telas menores):** vai para Início, Busca, Feed, Biblioteca, Relatórios, Interesses e alertas, Perfil, Planos e Laboratório de IA, alterna o tema, e transforma qualquer texto digitado em "Buscar artigos". Setas escolhem, Enter abre, Esc fecha; funciona também no Laboratório de IA. Vem de `static/fx.js`.
- **Topo do convidado:** além da jornada, uma **rede de fontes** ao fundo (PubMed, Europe PMC, arXiv, OpenAlex e DOAJ como nós rotulados que se organizam, ligam-se ao cursor e, no celular, ao toque) e uma **faixa de fontes** passando (busca e feed). A rede só anima enquanto o topo está na tela e pausa fora dela.
- **Perfil:** mostra o nome e a inicial dele no avatar, e os números contam de zero. **Administração:** os números contam, e a visão geral passou a mostrar também o plano Max.

## Animações e acessibilidade
- Tudo é feito com classes de CSS e propriedades definidas por script (`style.setProperty`), sem estilo nem script em linha, por causa da política de segurança do site. Sem bibliotecas.
- Com **"reduzir movimento"** ligado no aparelho, as animações somem: os blocos aparecem de uma vez, os números não contam e o título não anima.
- O cartão da jornada é decorativo (`aria-hidden`); o texto dos três passos é real e fica acessível.
- A lógica que dá para testar sem navegador está em `browse-lib.js` (`journeyProgress`, `journeyScene`, `countAt`, `stepsSummary`) e em `tests/js/browse-lib.test.js`.

## Nome da conta
- **Cadastro:** a janela de criar conta pede "Como podemos te chamar?". O campo aparece no primeiro clique em "Criar conta" e o segundo envia. O nome é obrigatório na interface, mas **opcional na API** (`name` em `POST /api/auth/register`), então clientes antigos continuam funcionando.
- **Edição:** Perfil → Conta e dados → Nome (`PUT /api/account/name`).
- **Regras:** 1 a 60 caracteres, espaços repetidos viram um, sem caracteres de controle. Nome inválido no cadastro recusa a criação (nenhuma conta fica pela metade).
- **Onde fica:** tabela `user_names` (`ProfileStore`). `GET /api/auth/me`, `POST /api/auth/login`, `POST /api/auth/register` e `GET /api/account` devolvem `name` (vazio se não houver). Sai junto com a conta na exclusão e entra no arquivo "Baixar meus dados".
