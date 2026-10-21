# Feature: Feed de novidades acadêmicas

## Objetivo
Uma aba **Feed** (`#/feed`) com as novidades de revistas científicas, instituições de pesquisa, preprints, divulgação científica e jornais (só o que trata de pesquisa), em todas as áreas do conhecimento, filtrada pelos interesses da pessoa. Ao clicar, a pessoa vai para a **fonte**; nada do texto da fonte é copiado além do título e de um trecho curto.

O feed é leitura (a pessoa vem ver). O sininho é aviso (o produto procura a pessoa). Os artigos novos dos interesses aparecem nos dois.

## O que a pessoa vê
- **Cartões** com tipo da fonte (Instituição, Revista, Preprint, Divulgação científica, Blog acadêmico, Jornal), nome da fonte, quando saiu, idioma (se não for português), título (link para a fonte, em nova aba), trecho de até 300 caracteres, os interesses que o item cita e "Ler em <fonte>".
- **Para você / Tudo** (só com conta e interesses): "Para você" mostra só o que cita as áreas, os subtemas ou as palavras-chave escolhidos em Perfil > Interesses; "Tudo" mostra tudo. Sem conta ou sem interesses, mostra tudo.
- **Filtros:** Tudo, Artigos ou Notícias; área do conhecimento (14); idioma (português ou inglês). Ficam na URL (`#/feed?modo=tudo&tipo=noticias&area=medicina&lang=pt`).
- **Como um item entra numa área:** pelo que o **próprio item cita** (os temas encontrados no título e no trecho) e pela **área principal da fonte** (a primeira da lista dela). As demais áreas da fonte só valem quando o item cita um tema delas, e fontes gerais (Phys.org, MIT News, Nature, PLOS ONE, Jornal da USP...) não têm área: o item só aparece num filtro se o texto citar um tema da área. Antes, uma fonte geral contava todos os seus itens em todas as suas áreas, e o filtro "Engenharias" trazia notícias de saúde. As áreas são calculadas na leitura (`item_areas`), então corrigir a lista de uma fonte vale também para o que já está guardado. Itens sem área aparecem só em "Todas as áreas" (cerca de 1 em cada 5), e com um filtro ativo a capa do cartão usa a área filtrada.
- **Limite:** a classificação é por palavras-chave (as mesmas dos interesses); um título que cite um termo ambíguo pode cair numa área errada, e um assunto sem palavra-chave conhecida não entra em nenhum filtro.
- **Artigos novos dos interesses** (os mesmos do sininho) entram em "Para você" e abrem a página do artigo aqui dentro, com a nota de confiabilidade.
- **Fontes e critérios:** painel no fim da página com as 51 fontes, o tipo de cada uma, idioma, áreas e se falharam na última busca.
- Em celular, a barra inferior é: Início, **Feed**, Busca, Biblioteca, Laboratório.

## Visual do feed
- **Sem imagens de terceiros, de propósito.** Cada cartão tem uma **capa gerada no próprio produto**: gradiente na cor da **área do conhecimento** do item (14 cores, uma por área) com o **ícone da área** em marca-d'água, o tipo da fonte na capa e um selo **"Novo"** para itens de menos de 6 horas. Não puxamos fotos das fontes: isso exigiria carregar imagens de outros sites (a CSP e a Política de Privacidade dizem que o navegador não carrega nada de terceiros) e a licença das imagens varia de fonte para fonte.
- **Grade e destaque:** o primeiro item aparece em destaque, em largura total, e os demais em grade (4 colunas no desktop largo, 1 no celular). Cada fonte tem um avatar com as iniciais, em cor própria.
- **Filtro de área em pílulas:** uma faixa rolável com todas as áreas, cada uma com cor e ícone, no lugar da lista suspensa.
- **Rolagem infinita:** ao chegar perto do fim, a próxima página carrega sozinha (o botão "Carregar mais" continua como alternativa). A rolagem automática do navegador (âncora de rolagem e restauração) foi desligada porque fazia o feed carregar tudo de uma vez.
- **Mistura de fontes:** a lista traz primeiro as **2 mais novas de cada fonte**, depois as 2 seguintes, e assim por diante (sempre por data dentro de cada rodada). Assim uma fonte que publica tudo de uma vez, ou sem data no feed, não ocupa a primeira tela inteira.
- Títulos e trechos com entidades codificadas duas vezes (`&#8220;`) passam a ser decodificados.

### Fotos de verdade: o que seria preciso
Para ter a foto de cada notícia, o caminho seguro é um **proxy de imagens** no servidor (baixa a imagem da fonte, limita tipo e tamanho, guarda em cache e serve do próprio domínio, sem expor o IP de quem lê), **só para fontes cuja licença permite** (por exemplo, as de licença aberta como Agência Brasil, PLOS e eLife). Custa banda e memória no plano gratuito e exige revisar os termos de cada fonte; fica como próximo passo opcional.

## Fontes (lista curada)
51 fontes verificadas funcionando em 2026-10-18 (`feed_sources.py`):
- **Saúde:** Fiocruz, OPAS/OMS, OMS, CDC (MMWR), BMJ, JAMA Network, PLOS Medicine, medRxiv, ScienceDaily, Medical Xpress, Agência Brasil, Folha e G1.
- **Ciência em geral:** Revista Pesquisa FAPESP, Jornal da USP, The Conversation (Brasil e global), Folha Ciência, Nature, PLOS ONE, eLife, bioRxiv.
- **Engenharia, computação e exatas:** MIT News, IEEE Spectrum, Tech Xplore, ScienceDaily (computação e matemática; matéria e energia), Phys.org, Quanta.
- **Ambiente:** ScienceDaily, Eos, Carbon Brief, Mongabay, Agência Brasil. **Mente, sociedade e educação:** ScienceDaily (duas seções), Agência Brasil Educação, G1 Educação.
- **Ciências agrárias:** ScienceDaily (agricultura e alimentos; plantas e animais), Phys.org (plantas e animais), Mongabay e Agência Brasil (meio ambiente).
- **Direito** (área "Ciências sociais e humanas"): Verfassungsblog, EJIL: Talk! e Oxford Human Rights Hub (blogs acadêmicos).
- **Economia** (mesma área): VoxEU/CEPR, NBER (working papers, sem data no feed), Ipea, Our World in Data e Agência Brasil Economia.
- **Comunicação científica e universidades:** SciELO em Perspectiva e Jornal da Unesp.

Testadas e **fora** da lista (bloqueiam leitores automáticos, mudaram de endereço ou não servem): Science, The Lancet, NEJM, NIH, Ministério da Saúde, Unicamp, Times Higher Education, Estadão, Agência FAPESP, arXiv (o feed de hoje vem vazio), Embrapa, FAO, CGIAR, Conjur, Migalhas, STF, STJ, Lawfare, Brookings, Banco Mundial, FMI, OCDE e FGV/IBRE. Também ficaram de fora, por serem notícias de instituições ou de política e não pesquisa: Agência Senado, Agência Câmara, Banco Central, Harvard Law Today e Jota.

**Lacunas:** não achamos feed utilizável de fontes brasileiras de ciências agrárias (Embrapa) nem de direito (Conjur e Migalhas bloqueiam); direito e economia em português dependem do Ipea, do SciELO, do Jornal da Unesp e da Agência Brasil.

### Tipo da fonte não é nota de confiabilidade
O tipo diz que **espécie de fonte** é. Notícias e comunicados **não passam pela nota de confiabilidade** dos artigos, e preprints não têm revisão por pares. O painel "Fontes e critérios" repete isso.

## Como funciona
1. **Leitura** (`feed.py`): RSS 2.0, Atom e RSS 1.0 (RDF), com XML sem entidades (`xmlutil`), até 3 MB por feed, só links http(s). Datas em vários formatos (inclui a variante da Folha). Do resumo da fonte guarda no máximo 300 caracteres, sem marcação. Fontes sem data no feed (NBER) usam o horário em que o item foi visto e aparecem como "data não informada".
2. **Filtro de jornais:** itens de jornal só entram se citam pesquisa ou ciência (estudo, pesquisa, cientistas, universidade, periódico, publicado, descoberta...). Receitas e conselhos de relacionamento ficam de fora. Outras fontes entram por inteiro.
3. **Classificação:** cada item recebe os temas citados no título e no resumo (a mesma lista de áreas e subtemas dos alertas, em português e inglês) e as áreas (as da fonte mais as dos temas citados).
4. **Armazenamento:** tabelas `feed_items` (45 dias) e `feed_state` (última busca, erro, ETag, Last-Modified).
5. **Atualização:** cada fonte é buscada no máximo a cada 3 horas, com requisição condicional (ETag e Last-Modified) e identificação do robô. Quem abre o feed dispara, em segundo plano, a busca de até 12 fontes vencidas; a **rota agendada** (`POST /api/internal/alerts/run`) busca todas (cerca de 40 a 60 segundos para as 51) e devolve `feed` com `due`, `refreshed`, `failed` e `items`. Uma fonte que falha não derruba as outras e o que já estava guardado fica.
6. **Leitura filtrada** (`FeedService.page`): do mais recente para o mais antigo, no máximo **12 itens por fonte** (uma fonte que publica muito não toma o feed), 20 por página.

## API
| Rota | Quem | O que faz |
|---|---|---|
| `GET /api/feed?mode=voce\|tudo&kind=todos\|artigos\|noticias&area=&lang=&page=` | público | Cartões, total, se há mais, se está personalizado, se tem interesses, data da última busca e se ainda está carregando |
| `GET /api/feed/sources` | público | Fontes, tipos, áreas, última busca bem-sucedida e falhas |

## Direitos e termos
- O feed mostra título, trecho curto e link, e leva a pessoa à fonte, que é o uso esperado de um feed público. Não copia texto completo nem imagens.
- Cada fonte tem os próprios termos de uso. **Antes de cobrar pelo produto, revisar os termos de cada fonte** (e remover quem proíbe uso comercial ou agregação). A lista foi montada só com feeds públicos, mas isso não substitui essa revisão.
- Para tirar uma fonte, basta removê-la de `feed_sources.py`; os itens dela somem em até 45 dias.

## Manutenção
- `python scripts/verificar_feeds.py` confere todas as fontes (responde, tem itens, itens com data). Rodar antes de acrescentar uma fonte e de vez em quando, pois feeds mudam de endereço ou passam a bloquear.
- Para acrescentar uma fonte: conferir o feed, escolher o tipo e as áreas (chaves de `interests.py`) e registrar em `feed_sources.py`.

## Limites
- A classificação por tema é por palavras (como os alertas): erra e deixa de fora; notícias em português citam o assunto de passagem, então "Para você" tem ruído.
- Itens sem data usam o horário da busca e aparecem como "data não informada".
- Sem busca por texto, sem salvar item e sem "marcar como lido" no feed; sem fotos das fontes (as capas são geradas, ver "Visual do feed").
- Cobertura desigual: ótima em saúde, boa em computação, engenharia, exatas e ambiente, razoável em ciências agrárias, direito e economia (quase tudo em inglês; ver "Lacunas").
- A primeira busca (banco vazio) pode levar cerca de um minuto; a tela mostra "Buscando as primeiras novidades" e tenta de novo.
- O feed não tem tradução; fontes em inglês aparecem em inglês.

## Testes
`tests/test_feed.py` (lista curada, datas, trechos, links, leitura de RSS, Atom e RDF, entidades maliciosas, busca com requisição condicional e limites, armazenamento, atualização com falhas e 304, filtro de jornais, limite por fonte, filtros e personalização, rotas e rota agendada). Nenhum teste usa a rede.
