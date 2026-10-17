# Plano de redesign visual: do "divertido" ao institucional

Status: proposta para aprovação. Nada deste plano foi implementado.

## 1. Diagnóstico

Referência observada: openalex.org. O que passa a impressão de empresa grande ali:

- **Contenção.** Uma cor de ação (botão preto), todo o resto em tons de cinza. Quase nada compete por atenção.
- **Tipografia como protagonista.** Título enorme, em peso forte, com espaçamento entre letras levemente negativo; texto de apoio em cinza médio, largura de linha curta.
- **Ar.** Muito espaço em branco, poucas caixas, bordas finas em vez de fundos coloridos.
- **Sem decoração.** Nenhum emoji, nenhum ícone colorido, nenhuma pílula chamativa. Números reais (517 milhões de registros) no lugar de adjetivos.
- **Estrutura previsível.** Barra superior fina, menu simples, um botão primário, rodapé completo.

O que no nosso visual lê como "infantil" (auditoria do código):

| Problema | Onde | Quantidade |
|---|---|---|
| Emoji como ícone e rótulo | `browse.js` 14, `browse.html` 3, `ia.html` 4, `pages.py` 21 (nomes das abas), `app.js` 5 | 47 |
| Laranja em excesso (fundos cheios, pílulas, selos, rótulo em caixa alta com borda) | Página inicial, abas, chips, etiqueta "Navegador de artigos científicos" | vários |
| Muitas formas arredondadas e "cartões" de mesmo peso | `border-radius` 12 px e 999 px por toda parte; 24 usos em `browse.css` | todo o app |
| 17 abas em linhas quebradas, todas com o mesmo peso | `/ia` | 17 |
| Hierarquia fraca: tudo é cartão, nada é título | Página inicial e artigo | — |
| Cabeçalho e rodapé sem identidade institucional | Sem rodapé; marca é um "M" em quadrado laranja | — |

## 2. Direção

**"Instrumento científico, não aplicativo de consumo."** Preto e laranja continuam sendo a identidade, mas o laranja passa a ser um **sinal** (ação, foco, estado ativo), não um preenchimento. Isso é o que faz o preto-e-laranja parecer premium em vez de esportivo.

Princípios:

1. **Uma cor de destaque, usada com parcimônia.** Laranja só em: botão primário, link, foco, item ativo, uma linha fina de marca. Nunca em fundos grandes nem em pílulas decorativas.
2. **Tipografia antes de caixas.** Hierarquia por tamanho, peso e espaço; cartões só onde agrupam de fato (resultado de busca, painel).
3. **Zero emoji.** Ícones de traço fino em SVG embutido (mesma espessura e cantos), apenas onde ajudam a achar algo.
4. **Densidade de ferramenta.** Linhas e divisórias de 1 px no lugar de fundos; raios de 6 px (2 px em controles pequenos), nunca pílulas, exceto em contadores.
5. **Provas, não adjetivos.** Números verdadeiros e verificáveis, nomes de fontes, critérios abertos.
6. **Acessibilidade como padrão.** Contraste AA, foco visível, teclado, movimento reduzido, impressão.

## 3. Sistema de design (tokens)

Tudo em variáveis CSS em `static/browse.css` (e reaproveitado por `app.css`). Valores iniciais, a ajustar com protótipo:

**Cor, tema escuro (padrão da marca)**

| Token | Valor | Uso |
|---|---|---|
| `--bg` | `#0a0a0b` | fundo da página |
| `--surface` | `#111113` | painéis, resultados |
| `--surface-2` | `#18181b` | hover, campos |
| `--line` | `#26262b` | bordas e divisórias (1 px) |
| `--text` | `#ededee` | texto principal |
| `--muted` | `#9b9ba3` | texto de apoio (contraste ≥ 4,5:1 sobre `--bg`) |
| `--accent` | `#ff6a00` | ação, foco, link |
| `--accent-strong` | `#ff8533` | hover |
| `--on-accent` | `#0a0a0b` | texto sobre laranja |

**Cor, tema claro (par de igual qualidade)**: fundo `#ffffff`, superfície `#fafaf9`, linha `#e4e4e0`, texto `#0f0f10`, apoio `#5a5a62`, destaque `#c2410c` (texto) e `#ea580c` (preenchimento), botão primário com texto branco.

**Decisão a tomar:** seguir a preferência do sistema (recomendado) ou manter escuro como padrão. Hoje o tema claro existe, mas é secundário.

**Tipografia**
- Pilha de sistema (`system-ui`, `-apple-system`, `Segoe UI`, `Roboto`), **sem baixar nada**, mantendo a CSP `default-src 'self'`.
- Opcional, com sua aprovação: hospedar a fonte Inter (licença OFL) em `static/fonts/` para ficar idêntico em todos os aparelhos. Exige baixar o arquivo oficial; só faço depois do seu "sim".
- Escala: 14 / 16 / 18 / 22 / 32 / 48 px; títulos com peso 700 e espaçamento −0,02 em; texto corrido a 16 px, entrelinha 1,6, largura máxima de 68 caracteres.

**Forma e espaço**
- Escala de espaço de 4 px (4, 8, 12, 16, 24, 32, 48, 72).
- Raios: 6 px (padrão), 4 px (campos pequenos). Sombras praticamente ausentes; separação por linha.
- Container 1200 px, grade de 12 colunas, margens laterais de 24 px (16 px no celular).

**Ícones**
- Conjunto próprio de 12 a 16 ícones de traço de 1,5 px (busca, filtro, salvar, lista, exportar, link externo, usuário, tema, alerta, verificado, documento, seta), em `static/icons.svg` como `<symbol>`, usados com `<use>`. Sem biblioteca externa.
- Marca: trocar o "M" em quadrado laranja por um logotipo simples em traço (monograma ou lupa sobre linha), com versão para fundo claro.

## 4. Componentes (o que muda)

| Componente | Hoje | Depois |
|---|---|---|
| Botão primário | laranja cheio, canto 10 px | laranja cheio, canto 6 px, peso 600, sem sombra |
| Botão secundário | fundo cinza com borda | só borda de 1 px, texto `--text` |
| Chip / filtro ativo | pílula laranja | pílula removida; texto com sublinhado laranja de 2 px |
| Cartão de resultado | caixa com borda grossa | linha divisória entre resultados, título como link, metadados em cinza |
| Selo de tipo de estudo | pílula laranja | texto pequeno em caixa alta, cinza, com ponto laranja só nos tipos de maior evidência |
| Nota de confiabilidade | faixa com número grande | medidor discreto (barra fina + número), explicação em painel, ícones de estado em SVG (sem ✓ ◐ ✗ textuais) |
| Campos | fundo preto, borda cinza | altura 40 px, foco com anel laranja de 2 px |
| Abas do `/ia` | 17 botões em linhas | menu lateral agrupado (ver 5.5) |
| Cabeçalho | marca + abas em pílula | barra fina de 56 px, links em texto, item ativo com linha laranja inferior |
| Rodapé (novo) | não há | colunas: produto, fontes, legal; aviso de que não é orientação médica |

## 5. Telas

### 5.1 Início
- **Hero tipográfico:** título grande (48 px) à esquerda, parágrafo de 2 linhas, caixa de busca larga com seletor de fonte embutido (como no OpenAlex), botão "Buscar". Sem etiqueta em caixa, sem sugestões em pílula (viram uma linha de links discretos "Exemplos:").
- **Faixa de números verdadeiros:** só o que podemos garantir, por exemplo "2 fontes integradas", "8 critérios abertos de confiabilidade", "5 formatos de citação", "17 áreas de análise". Nada inventado.
- **Como funciona** em 3 colunas numeradas (01, 02, 03), sem cartão colorido.
- **Para quem**: quatro linhas de texto com link, em vez de quatro cartões.
- **Confiança e método**: bloco explicando a nota e o "sem IA primeiro", com link para a página de metodologia.
- **Rodapé** completo.

### 5.2 Busca
- Barra de busca fixa no topo da página; filtros em coluna lateral com títulos em caixa alta pequena; resultados como lista com divisórias; contagem e ordenação alinhadas à direita; paginação numérica simples.

### 5.3 Artigo
- Cabeçalho editorial: título (32 px), autores, periódico e ano em uma linha; ações em barra (salvar, citar, versão aberta, analisar com IA).
- Coluna principal com resumo e números; coluna lateral fixa com nota de confiabilidade, tipo de estudo, fonte e metadados. Nota explicada em painel recolhível.

### 5.4 Biblioteca e listas
- Tabela densa e ordenável (título, ano, etiquetas, data); ações em menu; listas como seções com contagem.

### 5.5 Laboratório de IA (`/ia`)
- **Menu lateral agrupado**, em vez de 17 abas: **Geral** (Geral, Acadêmico), **Saúde** (Medicina, Enfermagem, Farmácia, Nutrição, Psicologia, Saúde Pública, Para o Paciente), **Exatas e Tecnologia** (Tecnologia e IA, Engenharias, Biotecnologia), **Sociedade e Ambiente** (Ambiental, Direito e Políticas, Educação, Agro e Veterinária), **Busca** (Pesquisa).
- Nomes de aba sem emoji (`pages.py`: `tab_name` passa a texto puro; o teste que garante nomes únicos continua valendo).
- Botões de análise em lista vertical agrupada por seção, com rótulo claro; resultado em painel de leitura com tipografia de documento.

## 6. Fases e entregas

| Fase | Entrega | Verificação |
|---|---|---|
| 1. Fundação | Tokens, tipografia, `icons.svg`, novo logotipo, cabeçalho e rodapé; remover todos os emojis | Nenhum emoji no HTML renderizado; contraste AA |
| 2. Início | Hero, faixa de números, como funciona, para quem, método | Captura de tela comparativa antes e depois, desktop e celular |
| 3. Busca e artigo | Lista com divisórias, filtros laterais, cabeçalho editorial, painel de nota | Fluxo real com Europa PMC e OpenAlex, sem erros no console |
| 4. Biblioteca e listas | Tabela densa, menus | Teste de ponta a ponta com conta de teste local |
| 5. Laboratório de IA | Menu lateral agrupado, painel de leitura | Navegação por teclado entre grupos e abas |
| 6. Acabamento | Tema claro e escuro, impressão, movimento reduzido, 3 larguras (360, 768, 1280) | Checklist de acessibilidade e capturas finais |

Cada fase vira um commit atômico; nenhuma muda comportamento, API nem banco. Testes existentes continuam como estão, mais testes de asserção para "sem emoji" e "rótulos de aba sem símbolo".

## 7. Critérios de aceite

- Zero emoji em qualquer tela e em `tab_name`.
- Laranja ocupa menos de 5% da área visível em qualquer tela (medido por amostragem de pixels na captura).
- Contraste de texto ≥ 4,5:1 e de controles ≥ 3:1 nos dois temas.
- Sem recurso externo (CSP `default-src 'self'` mantida); fonte própria só com aprovação.
- 100% navegável por teclado; foco visível sempre.
- Ruff, mypy, pytest e testes de Node passando.

## 8. Riscos

- **Preto e laranja em excesso de contraste** cansam a leitura longa. Mitigação: texto corrido em cinza claro, não branco puro; resumo e artigo em largura de leitura.
- **Mudar tudo de uma vez** dificulta revisão. Mitigação: fases pequenas, cada uma publicável.
- **Gosto é subjetivo.** Mitigação: antes de codar, uma maquete estática da página inicial e do artigo para aprovação.

## 9. Decisões que preciso de você

1. Tema padrão: seguir o sistema (recomendado) ou escuro sempre?
2. Fonte: pilha do sistema (sem baixar nada) ou hospedar Inter?
3. Nome e logotipo: manter "Biomedical Data Digger" com novo monograma, ou aproveitar para renomear?
4. Faixa de números: vale aparecer só com dados que podemos garantir (itens acima)?
5. Começo pela maquete estática (recomendado) ou direto para a fase 1?
