# Front-end

## Visão geral
- **Sem framework, sem build, sem CDN, sem fontes externas.** HTML + CSS + JavaScript puro, servidos pelo próprio servidor em `/static`.
- **SPA com roteamento por hash** (`#/rota`) para o navegador de artigos; o Laboratório de IA (`/ia`) é uma página separada.
- Tema escuro e claro (alternância guardada no navegador), identidade preto e laranja, layout responsivo (desktop, tablet e celular) com barra inferior no celular.
- **Política de segurança de conteúdo estrita:** `default-src 'self'` e `style-src 'self'`. Consequência prática: **nada de `style` inline nem `<script>` inline**. Larguras e alturas dinâmicas (barras do panorama) são aplicadas por JavaScript via CSSOM (`elemento.style.width = …`), que a política permite.

## Arquivos
| Arquivo | Papel |
|---|---|
| `templates/browse.html` | Casca da SPA: topo, menu, sininho, diálogo de entrada, `#app`, barra inferior, rodapé |
| `templates/ia.html` | Laboratório de IA (formulário, abas por área, resultado) |
| `templates/_icons.html` | Sprite SVG (ícones referenciados por `<use href="#i-…">`) |
| `templates/_footer.html` | Rodapé: produto, fontes de busca, registros abertos |
| `static/browse.js` | Aplicação: telas, chamadas à API, estado de sessão |
| `static/browse-lib.js` | Funções puras (rotas, parâmetros de busca, paginação) com testes em `tests/js/` |
| `static/brand.css` | Variáveis de tema, componentes e telas do produto |
| `static/browse.css` | Estilos auxiliares do navegador |
| `static/app.js`, `static/app.css` | Laboratório de IA |

Os assets recebem `?v=<hash>` calculado no início do servidor (data de modificação), permitindo cache longo sem servir arquivos velhos. **Depois de alterar JS/CSS em desenvolvimento, reinicie o servidor** para atualizar o hash.

## Rotas da SPA
| Hash | Tela | Observações |
|---|---|---|
| `#/` | Início | Busca, números do produto, recursos, método e atalhos do perfil |
| `#/busca?q=…` | Busca | Filtros e ordenação na URL; panorama do tema |
| `#/artigo?ref=…` | Artigo | Resumo, números, nota, registros abertos, Brasil, semelhantes, downloads |
| `#/feed?…` | Feed | `modo`, `tipo`, `area`, `lang` na URL |
| `#/biblioteca` | Biblioteca e listas | Exige conta |
| `#/lista/<id ou token>` | Lista de leitura (própria) ou lista pública | Token público não exige conta |
| `#/relatorio/<id>` | Relatório de tema | Exige conta |
| `#/perfil/<seção>` | Perfil: visão geral, uso, interesses, notificações, conta | Exige conta (sem conta, mostra convite) |
| `#/interesses` | Redireciona para `#/perfil/interesses` | Compatibilidade |

Hash desconhecido volta ao início. Parâmetros de URL são tratados como **entrada não confiável**: valores inválidos viram o padrão.

## Navegação
- Desktop: Início, Feed, Busca, Biblioteca, Laboratório de IA; à direita, tema, sininho (com conta) e o botão da conta (abre o Perfil).
- Celular: barra inferior com Início, Feed, Busca, Biblioteca e Laboratório (a mesma nas duas páginas).

## Comunicação com a API
- `fetch` com cookies de sessão (mesma origem). Respostas de erro vêm como `{"error": "mensagem"}`; a interface mostra a mensagem.
- Buscas usam `AbortController` para cancelar a anterior. Panorama, semelhantes, registros abertos e situação no Brasil carregam **depois** do conteúdo principal.
- O sininho consulta `GET /api/alerts` ao entrar e a cada 15 minutos com a aba visível; "Verificar agora" chama `POST /api/alerts/check`.

## Acessibilidade e conteúdo
- Elementos semânticos, `aria-label` em controles sem texto, foco visível, navegação por teclado, `aria-live` na lista de resultados.
- **Sem emojis na interface** (regra testada em `tests/test_no_emoji_ui.py`).
- Texto de fontes externas é inserido como texto (nunca como HTML); links externos só `http(s)` (`safeHttpUrl`).

## Testes
- `tests/js/browse-lib.test.js` (`node --test`): rotas, estado de busca, parâmetros, paginação.
- Testes de integração em `tests/test_browse_api.py` verificam a página servida e os cabeçalhos.
- A verificação visual é manual (desktop e celular); não há teste visual automatizado.
