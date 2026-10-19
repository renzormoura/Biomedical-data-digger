# Funcionalidade: Panorama do tema

## Objetivo
Dar, em poucos segundos, um retrato do que a busca encontrou: quanta evidência forte existe, de que período, quanto é aberto e qual é o estudo de maior nota. Não gera texto e não faz nova consulta de dados além dos próprios resultados.

## O que a pessoa vê
Um painel recolhível acima dos resultados (aberto no desktop, recolhido no celular) com:
- **Três números:** porcentagem com acesso aberto, quantidade de fontes e período publicado (e, se houver, quantos artigos retratados).
- **Tipo de evidência:** uma barra única, dividida por grupo, em escala de um tom só (do mais forte ao mais fraco), com legenda e contagem. Grupos: *Preprints*, *Revisões sistemáticas e meta-análises*, *Ensaios clínicos*, *Estudos observacionais e comparativos*, *Revisões narrativas e diretrizes*, *Relatos de caso e opinião* e *Tipo de estudo não informado*.
- **Maior nota de confiabilidade na amostra:** link para o artigo com a nota, o tipo, o periódico e o ano.
- Uma nota dizendo que o retrato conta **só a amostra** (os primeiros resultados por relevância), com o tamanho da amostra e o total da busca.

O painel só aparece na primeira página de resultados e quando a amostra tem ao menos 5 artigos.

## Como funciona
1. O navegador chama `GET /api/discover/panorama` com os mesmos filtros da busca (sem página).
2. O servidor lê até 2 páginas de 20 resultados da mesma busca (aproveitando o cache) e remove repetidos por DOI/referência.
3. `search_overview.build` conta, sem IA:
   - **grupo de cada artigo** pelos tipos de estudo do registro, na prioridade *Preprint → Sistemática/meta-análise → Ensaio → Observacional → Revisão/diretriz → Opinião → Não informado*;
   - anos de publicação, acesso aberto, fontes e retratações;
   - a **maior nota** entre os artigos com resumo e não retratados, calculada pelo mesmo módulo da [nota de confiabilidade](confiabilidade.md) (empate: mais citado).
4. O painel é carregado depois da lista, de forma assíncrona: se falhar, a lista segue normal.

## Limites
- É um retrato da **amostra**, não da literatura inteira. A tela diz isso.
- Muitos registros não informam o tipo de estudo; o grupo "não informado" pode dominar (principalmente fora de Europe PMC e PubMed).
- A maior nota mede sinais do registro e do resumo, não a qualidade real do estudo.

## Arquivos
`search_overview.py`, rota em `browse_api.py`, função `panoramaView` em `static/browse.js`, estilos `.panorama` em `static/brand.css`. Testes: `tests/test_search_overview.py`.
