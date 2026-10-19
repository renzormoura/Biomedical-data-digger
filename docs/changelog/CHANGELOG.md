# CHANGELOG

## 2026-10 — Notificações: retratação, mudança regulatória e relatórios

### Adicionado
- O sininho agora avisa de tudo o que é de prioridade alta ou média: **artigo retratado** na sua biblioteca, listas ou relatórios (alta), **mudança regulatória** de substância confirmada em relatório (alta), **novidades dos relatórios** com artigos novos na lista de origem (média) e os artigos novos dos interesses (média). Cada aviso traz selo do tipo e link direto; os importantes não lidos ficam no topo.
- **Retratação:** cada artigo guardado é reconferido na fonte uma vez por semana (resultado compartilhado entre contas); detecta onde a fonte informa (Europe PMC, PubMed e OpenAlex). Correções (errata) não são detectadas.
- **Regulatório:** compara o estado da substância (Conitec, Rename, ANVISA) com a verificação anterior; a primeira só memoriza.
- Seção **Perfil > Notificações**, para ligar e desligar cada tipo (tudo ligado por padrão). Por enquanto só o sininho; e-mail e outros canais ficam para depois.
- Módulo `notifications.py`; rota `GET/PUT /api/notifications/prefs`; `GET /api/alerts` passou a devolver a caixa unificada (`kind`, `priority`, `title`, `body`, `href`); a rota agendada também roda o vigia. Exportação de dados e exclusão de conta incluem os avisos.

### Alterado
- A verificação do sininho agora roda para todas as contas logadas, não só para quem tem interesses. O painel fecha ao trocar de tela.

### Limites
- Retratação só nas fontes que informam; uma biblioteca grande leva alguns dias para ser conferida inteira. Dados regulatórios mudam só quando um instantâneo novo é publicado e seguem sem revisão de especialista.
## 2026-10 — Aba Perfil

### Adicionado
- Aba **Perfil** (`#/perfil`) no menu e na barra inferior, com quatro seções: **Visão geral** (e-mail, "membro desde", contadores e resumos), **Perfil de uso**, **Interesses e alertas** (a antiga página "Meus interesses" agora vive aqui; `#/interesses` redireciona) e **Conta e dados**.
- **Conta e dados:** trocar senha (pede a atual), **baixar uma cópia dos dados** em JSON (sem a senha) e **excluir a conta** com todos os dados, confirmando a senha. Rotas `GET /api/account`, `POST /api/account/password`, `GET /api/account/export` e `DELETE /api/account`; módulo `account_routes.py`.
- O servidor passa a conferir, com cache de 30 segundos, se a conta da sessão ainda existe: uma conta excluída deixa de valer em outros aparelhos.

### Alterado
- O item "Interesses" saiu do menu (virou parte do Perfil), e a barra inferior do celular passou a ter 5 itens.

### Limites
- Sem troca de e-mail, recuperação de senha, confirmação de e-mail, verificação em duas etapas nem encerramento remoto de outras sessões (trocar a senha não derruba os outros aparelhos; a sessão expira em 7 dias).
## 2026-10 — Roteiro de validação com usuários (fase 5, preparação)

### Adicionado
- `docs/roadmap/roteiro-validacao-usuarios.md`: 7 hipóteses com critério de confirmação, perfis e triagem de 6 participantes, checklist da equipe, sessão de 45 minutos com fala de abertura, 5 tarefas com critério de sucesso, ficha de observação, perguntas sobre valor, confiança e preço, questionário curto, consentimento (LGPD), forma de análise e a tabela "se isto, então aquilo" para as decisões (CMED, preço, e-mail, revisão por especialista). Nenhuma sessão foi feita.
## 2026-10 — Perfil de uso (fase 4 do relatório de tema)

### Adicionado
- **Perfil de uso** por conta (estudante, pesquisador, profissional de saúde ou farmácia, consultoria, outro), com pergunta na primeira entrada ("Agora não" disponível) e tela **Perfil e preferências** (`#/perfil`), acessível pelo diálogo da conta.
- O perfil liga ou desliga o **pacote Saúde no Brasil** (cartão no artigo e seção no relatório) e mostra três atalhos "Para você" na página inicial. Só o perfil de saúde liga o pacote por padrão; a caixa permite mudar à parte. Sem conta ou sem perfil, o pacote fica visível. Nada do núcleo é bloqueado.
- Rotas `GET /api/profile/options`, `GET/PUT /api/profile`; módulo `profiles.py`; a página inicial recebe o perfil do servidor para não piscar.

### Limites
- A recusa da pergunta fica no navegador. Se o pacote estiver desligado, o relatório que já tem substâncias confirmadas continua mostrando a seção e as incluindo no documento.
## 2026-10 — Relatório de tema (fase 3): versões e atualização

### Adicionado
- **Versões do relatório** com resumo do que mudou e **restauração** de uma versão anterior (como nova versão). Salvar sem mudanças não cria versão. Ficam as últimas 50.
- **Atualizar o relatório:** "Novos na lista de origem" (com adicionar), **busca de artigos novos sobre o tema** (todas as fontes, só o que ainda não está no relatório) e **"Acompanhar nos meus alertas"**, que leva a busca para as palavras-chave do sininho.
- **Histórico de buscas e adições**, que entra no apêndice de método do documento. O método passa a dizer que as buscas feitas a partir do relatório estão registradas.
- Rotas `GET /api/reports/{id}/history`, `POST /api/reports/{id}/search`, `POST /api/reports/{id}/add` e `POST /api/reports/{id}/restore`.

### Limites
- Relatórios criados antes desta fase não têm lista de origem registrada (o painel "Novos na lista" avisa). A busca que levou aos estudos da lista de origem continua sem registro.
## 2026-10 — Biblioteca: botão Exportar

### Alterado
- Na biblioteca e em cada lista, os 13 botões de exportação viraram **um botão "Exportar"** com um menu agrupado: gerenciadores de referências (RIS, EndNote, CSL JSON, BibTeX), citações prontas (ABNT, APA, Vancouver, IEEE, Harvard, MLA) e planilha e dados (CSV, JSON, resumos). No celular o menu abre como painel acima da barra inferior. Esc fecha o menu.

### Corrigido
- Entre 561 e 900 px de largura, o painel de download do artigo ficava esmagado (20 px de altura) porque recebia `top` e `bottom` ao mesmo tempo; o `bottom` agora vale só no celular, onde o painel é fixo.

## 2026-10 — Relatório de tema (fase 2): Situação no Brasil

### Adicionado
- Seção **Situação no Brasil** no relatório, para temas de medicamento: o sistema sugere substâncias a partir dos resumos (com quantos estudos citam cada uma), o autor **confirma** as que valem, e o documento traz Rename 2024, registro na ANVISA e decisões da Conitec, com a data de cada base, os avisos de que constar não é estar disponível e de que os dados ainda não foram revisados por especialista. O apêndice de método registra a confirmação e as datas.
- Rota `GET /api/reports/{id}/brasil` e módulo `report_brasil.py`. O `PUT` do relatório aceita `substances`.

### Alterado
- A busca de nomes em português ficou ~4 vezes mais rápida (formas inglesas dos nomes em cache): de ~78 ms para ~21 ms por resumo.
- Os cartões da situação no Brasil foram movidos para o escopo do módulo para serem usados no artigo e no relatório.
- No relatório, a barra de ações deixou de ser fixa no rodapé (cobria o conteúdo no celular).

### Corrigido
- A lista de relatórios na biblioteca chamava uma função de data que só existia dentro da página do artigo; teria falhado assim que houvesse um relatório.
## 2026-10 — Relatório de tema (fase 1)

### Adicionado
- **Relatório de tema** a partir de uma lista de leitura: botão "Criar relatório" nas listas, seção "Relatórios de tema" na biblioteca e a tela `#/relatorio/<id>`. O autor escreve título e pergunta, escolhe quais estudos entram, escreve uma nota por estudo e uma nota livre sobre o método; cada salvamento gera uma nova versão.
- O documento traz panorama (tipo de estudo, ano, idioma, fonte, acesso aberto), estudos com nota de confiabilidade e frases estatísticas copiadas do resumo, referências (ABNT, APA, Vancouver) e um **apêndice de método automático** (origem, contagens de reunidos, incluídos e excluídos, critérios e pesos da nota, limites, versão e data). Download em **HTML, Word (.docx) e Markdown**; PDF pela impressão do HTML.
- Rotas `POST/GET /api/reports`, `GET/PUT/DELETE /api/reports/{id}` e `GET /api/reports/{id}/download`. Módulo `reports.py`.

### Limites
- As buscas usadas para achar os estudos não são registradas (a origem é uma lista montada à mão), e o método diz isso. Os estudos são um retrato do momento da criação e não se atualizam sozinhos.
- Sem seção "Situação no Brasil", versões comparáveis, perfil de usuário nem link público ainda (fases seguintes do plano).
## 2026-10 — Citações e exportação para Zotero, Mendeley e EndNote

### Adicionado
- Formatos **EndNote (.enw)** e **CSL JSON**, e novos estilos de citação **IEEE, Harvard e MLA** (junto de ABNT, APA e Vancouver). Valem na página do artigo, na biblioteca e nas listas.
- Na página do artigo, o bloco **Levar para o gerenciador de referências**: baixa a referência daquele artigo em RIS, EndNote, CSL JSON ou BibTeX, e copia o BibTeX. Rota pública `GET /api/discover/cite`.
- **Metadados `citation_*`** no `<head>` da página do artigo, para o conector do Zotero e do Mendeley capturarem o artigo pelo botão da extensão.

### Alterado
- RIS, BibTeX e os novos formatos agora levam URL (DOI ou PubMed), PMID, idioma e palavras-chave; no RIS a revista vai em `JF` e o resumo em uma linha só, para não quebrar a importação.
## 2026-10 — Alertas: datas, filtro de relevância e verificação agendada

### Medido com busca real
- Em 8 buscas reais (PubMed, Europe PMC, arXiv, DOAJ, OpenAIRE), a primeira versão trazia muito ruído: "direito" casou com "ventrículo direito" (o PubMed traduz a palavra), "large language models" trouxe um artigo de enterovírus, e as fontes devolvem datas futuras (fascículos programados, até 2099 no OpenAIRE).

### Alterado
- Cada artigo guarda a **data exata de publicação** quando a fonte informa (`Work.published`): Europe PMC, OpenAlex, arXiv, OpenAIRE e, no PubMed, a data em que o registro chegou. Só o ano continua valendo para DOAJ.
- Um artigo só vira aviso se tiver até 60 dias, quando a data é conhecida; datas futuras contam como "sem data" e anos absurdos são descartados.
- **Filtro de relevância:** o resultado só conta se o título, as palavras-chave ou a revista tratam do tema, ou se o resumo cita ao menos dois termos diferentes. Cada tema agora tem uma lista de termos em inglês e em português (80 temas revisados), e a primeira é a que vai para a busca.
- No máximo 5 avisos por tema em cada verificação, e os excedentes são descartados, sem formar fila. Cada busca traz até 20 resultados.

### Adicionado
- **Verificação agendada** (`POST /api/internal/alerts/run`, protegida por `ALERTS_CRON_TOKEN`; sem a variável a rota responde 404) e o fluxo `.github/workflows/alertas.yml`, que a chama a cada 6 horas. Para ativar: definir `ALERTS_CRON_TOKEN` no Render (24+ caracteres) e os segredos `APP_URL` e `ALERTS_CRON_TOKEN` no repositório do GitHub. Cada execução atende até 40 contas.

### Limites que continuam
- Precisão boa, mas não perfeita: a checagem é por palavras, não por frase, e para português o resultado é bem menor que para inglês.
- Sem e-mail ainda (o aviso aparece no sininho, ao abrir o site). E-mail exige escolher um provedor.
- Os termos de cada tema precisam de revisão por especialistas da área.

## 2026-10 — Alertas de artigos novos

### Adicionado
- **Sininho** no canto superior direito (para quem está logado), com contador de não lidos, lista dos artigos novos, "Marcar como lidas", dispensar aviso e "Verificar agora". No celular o painel desce da barra, em largura total.
- Tela **Meus interesses** (`#/interesses`): 14 áreas do conhecimento com subtemas (por exemplo, Medicina com Pediatria, Oncologia, Cardiologia...), até 4 idiomas, até 5 palavras-chave livres e limite de 15 temas. Para artigos em português a busca usa também os termos em português.
- Rotas `GET/PUT /api/interests`, `GET /api/interests/options`, `GET /api/alerts`, `POST /api/alerts/check`, `POST /api/alerts/read`, `DELETE /api/alerts`. Módulos `interests.py` (catálogo e validação) e `alerts.py` (preferências, verificação e caixa de avisos).

### Como funciona (e o que ainda não faz)
- Ao salvar, a primeira verificação só **memoriza** os artigos recentes que já existem; só o que surgir depois vira aviso, para não tratar artigo antigo como novo.
- A verificação roda quando o usuário está com o site aberto (ao entrar e a cada 15 minutos), no máximo a cada 6 horas (15 minutos no "Verificar agora"). Usa "Todas as fontes", ordenadas por mais recentes, do ano atual e do anterior.
- **Ainda não** há e-mail nem aviso com o site fechado: isso exige uma tarefa agendada no servidor, prevista como próximo passo.

## 2026-10 — Dados reais do Brasil, fase 3: Rename

### Adicionado
- O cartão **Situação no Brasil** agora mostra se a substância **consta na Rename 2024** (componente básico, estratégico ou especializado; apresentações com a página do PDF), junto do registro na ANVISA e das decisões da Conitec. Rota nova de dados em `GET /api/brasil/medicamento` e `GET /api/discover/brasil` (campo `rename`).
- Instantâneo `dados_brasil/rename.json` (968 apresentações, 514 substâncias, 267 páginas) gerado por `scripts/atualizar_rename.py` a partir do PDF oficial da 2ª edição (BVS/Ministério da Saúde). A leitura do PDF usa `pypdf` (só desenvolvimento) e guarda a página de origem de cada item.
- Conferência: todos os itens foram localizados, por texto e código ATC, na página citada do PDF (2 divergências eram só hifenização/nome corrigido), e uma amostra de 50 itens foi lida contra o PDF.

### Observações
- Licença do PDF: CC BY-NC-SA 4.0 (uso não comercial, com atribuição e mesma licença). Se o projeto for monetizado, rever.
- Insumos (Anexo IV) e as listas de inclusões, exclusões e ampliações não entram nesta fase. "Constar na Rename" não é "disponível na sua unidade", e a tela diz isso. O rótulo "pendente de revisão por especialista" continua até um farmacêutico ou médico revisar os dados.

## 2026-10 — Dados reais do Brasil, fase 2: ANVISA

### Adicionado
- O cartão **Situação no Brasil** agora mostra, por medicamento, o **registro na ANVISA** (registros ativos e inativos, genéricos, similares e novos, empresas, classe terapêutica e validade mais distante) ao lado das decisões da Conitec. A busca manual consulta as duas bases (`GET /api/brasil/medicamento`).
- Instantâneo `dados_brasil/anvisa.json` (3.857 substâncias, 72.824 registros ativos, 750 KB) gerado por `scripts/atualizar_anvisa.py` a partir do CSV aberto de 46 MB (dados.anvisa.gov.br, atualização diária na origem); sal e forma farmacêutica são removidos, e `cloreto de sódio` não vira `sódio`.
- Ligação inglês-português mais completa: dobra de grafia (ph/f, th/t, ll/l, y/i), que liga ampicillin, morphine, buprenorphine e ketamine sem tabela de sinônimos. Em 207 resumos reais, 121 tiveram candidatos e todas as correspondências revisadas estavam corretas.

### Removido
- A correspondência por grafia aproximada: ela ligava valganciclovir a valaciclovir, medicamentos diferentes. Preferimos perder recall a errar a substância.
- Exames, elementos e palavras comuns da química (glicose, sódio, fósforo, enxofre, sulfato...) nunca viram candidatos.

### Limitações
- Registro ativo permite comercializar; não indica fornecimento pelo SUS nem estoque local. A Rename (fase 3) ainda não está integrada, e a tela diz isso.

## 2026-10 — Dados reais do Brasil, fase 1: CONITEC

### Adicionado
- Cartão **Situação no Brasil** na página do artigo: decisões da Conitec (incorporar, não incorporar, ampliar, excluir...) para os medicamentos que o resumo parece citar, com portaria, data e número do relatório, e uma busca manual por nome em português. Sem IA e sem rede em tempo de execução.
- Instantâneo versionado `dados_brasil/conitec.json` (782 decisões sobre medicamentos, planilha oficial da Conitec) com origem e data da extração; `scripts/atualizar_conitec.py` o regenera (descobre o link atual na página, baixa com tentativas, lê o XLSX só com a biblioteca padrão e recusa leituras suspeitas).
- Ligação entre o nome em inglês e a DCB em português por sinônimos curados, cognatos de sufixo (-ine/-ina, -mab/-mabe...) e grafia aproximada; todo resultado vem marcado como correspondência a confirmar, com o método usado. Em 108 resumos reais testados, todas as correspondências eram corretas e os textos sem medicamento não geraram nenhuma.
- `GET /api/brasil/conitec?q=` e `GET /api/discover/brasil?ref=`.

### Limitações
- Só medicamentos e só Conitec: ainda não inclui ANVISA nem Rename (fases 2 e 3 do plano). Estar na Conitec não é o mesmo que estar disponível na sua unidade de saúde, e a tela diz isso.
- O portal gov.br responde 404 de forma intermitente; a atualização tenta até 6 vezes.
- A tabela de sinônimos precisa de revisão por farmacêutico.

## 2026-10 — Contexto do Brasil: correções de honestidade

### Corrigido
- O contexto do SUS não é mais injetado em artigos sem relação com o Brasil: o casamento passou a ser por palavra inteira e sem acento ("versus" e "susceptible" continham "sus"; "adrenal" continha "renal"), com sinônimos em inglês para vigilância, genéricos e populações especiais.
- CONASS descrito corretamente (Conselho Nacional de **Secretários** de Saúde) e erro de grafia ("radiao") corrigido.
- O anexo de verificação agora diz apenas que o site oficial respondeu e que isso **não confirma** o conteúdo da análise; deixou de exibir "revisão 2026-09" e "acessível", que sugeriam checagem.
- Os textos do contexto curado e do catálogo carregam "pendente de revisão por especialista", e o módulo deixou de afirmar que são mantidos por especialistas.

### Limitação conhecida
- O contexto curado traz orientações gerais, sem dados específicos (RENAME, CONITEC, registros da ANVISA). Disponibilidade, registro e regulação continuam "não verificáveis" até integrarmos essas bases por consulta direta, sem IA.

## 2026-10 — Listas recolhíveis na biblioteca

- Em "Listas de leitura" aparecem só os nomes (com a contagem de artigos); ao tocar no nome, a lista abre com os artigos, o link de compartilhamento e as exportações. A lista aberta continua aberta depois de tirar um artigo ou compartilhar.

## 2026-10 — Salvar em lista, sem rodeios

- O botão **Salvar** é um só: salva na biblioteca e abre o menu para marcar listas, **criar uma lista nova na hora** (mesmo sem nenhuma lista ainda) e remover da biblioteca. Com o artigo já salvo, o clique abre o mesmo menu em vez de remover. Vale na busca, no artigo e nos semelhantes; no celular o menu sobe como painel na base da tela.

## 2026-10 — Celular mais confortável

- Busca: barra de busca sempre visível e fixa, botão **Filtros** com contador que abre uma folha inferior (com "Limpar tudo" e "Ver resultados"), filtros ativos como chips removíveis, **Ordenar** ao lado da contagem e resultados logo abaixo; avisos da busca recolhidos em um só bloco. No desktop os filtros seguem na coluna lateral, agora com os mesmos chips e a barra de busca no topo.
- Navegação inferior (Início, Busca, Biblioteca, Laboratório) no lugar do menu em linha, e cabeçalho de uma linha.
- Alvos de toque de 44 px, campos de 16 px (sem zoom automático no iOS) e rótulos mais curtos.
- Artigo: a nota de confiabilidade aparece logo após as ações; ações em grade de duas colunas.
- Laboratório: seletor "Área de análise" agrupado no lugar da faixa de 17 abas.

## 2026-10 — Laboratório ligado ao navegador

### Adicionado
- Cartão do artigo carregado no topo de cada aba do Laboratório (título, autores, tipo de estudo, fonte e nota de confiabilidade, com link para a página do artigo); `GET /api/discover/brief`.
- **Salvar no artigo**: a análise fica guardada na conta (até 200, 60 mil caracteres cada), aparece no cartão "Análises do Laboratório" da página do artigo e na seção "Análises salvas" da biblioteca, onde dá para ver, baixar e excluir. `POST/GET/DELETE /api/analyses`.
- **Baixar a análise** em Word, Markdown, página web ou texto, com o artigo e o aviso de que análises com IA podem errar; `POST /api/export/analysis` (sem conta, sem guardar nada).

### Corrigido
- Na primeira análise de uma aba, os botões Copiar e Imprimir ficavam desabilitados porque o fim do carregamento restaurava o estado anterior.

## 2026-10 — Artigos semelhantes no fim do artigo

- Seção "Artigos semelhantes" no fim da página do artigo, com até 6 cartões (salvar e abrir) e a lista dos termos usados na busca; carrega depois da página, por `GET /api/discover/similar`.
- Semelhança por palavras-chave úteis (sem termos genéricos como Humans) somadas às palavras mais específicas do título, por relevância e na mesma fonte; artigos sem palavra-chave (como os do arXiv) passam a ter semelhantes pelo título.
- O detalhe do artigo não faz mais a busca de semelhantes, o que acelera a abertura da página.

## 2026-10 — Busca em todas as fontes por padrão

- A busca abre em "Todas as fontes" (também na página inicial); a fonte única continua a um clique. Com uma só fonte configurada, o padrão é ela.

## 2026-10 — Download de artigos

### Adicionado
- Menu **Baixar** no artigo: resumo, ficha de leitura, referência e texto completo aberto, em TXT, Markdown, HTML, DOCX e JSON (texto completo também em XML JATS). `GET /api/discover/downloads` e `GET /api/discover/download`.
- Texto completo vem da Europe PMC apenas para artigos de acesso aberto (PMC), com a licença no cabeçalho; sem acesso aberto, o menu explica e oferece os links abertos de PDF informados pela fonte.
- Exportação em lote da biblioteca e das listas: planilha CSV (protegida contra fórmulas), JSON e todos os resumos em Markdown.
- Documentos com cabeçalhos `attachment` e `nosniff`; HTML gerado com todo o texto escapado; DOCX gerado sem dependências externas.

### Limitações conhecidas
- PDFs de editoras não são baixados pelo servidor: a interface só leva ao link aberto da fonte.
- Texto completo depende de a Europe PMC ter o artigo no subconjunto aberto; artigos do arXiv têm o PDF como link, sem conversão.

## 2026-10 — Mais fontes e registros abertos

### Adicionado
- Fontes de busca: PubMed (E-utilities), arXiv, DOAJ e OpenAIRE, sem chave. O PubMed aceita `NCBI_API_KEY` opcional.
- Cartão "Registro e dados" no artigo: ClinicalTrials.gov, OpenCitations e DataCite (inclui Zenodo), carregado em segundo plano (`GET /api/discover/enrichment`).
- Leitura de XML da rede com recusa de declarações de entidade (`xmlutil.py`).

### Alterado
- "Todas as fontes" passa a consultar as seis fontes em paralelo: cada uma entrega uma fatia da página (a página combinada mantém o tamanho pedido), fonte que passa de 14 s fica de fora com aviso e deixa o resultado no cache.
- A etiqueta de citações some quando a fonte não informa o número.

### Limitações conhecidas
- medRxiv e bioRxiv não têm busca por palavra-chave na API; seus preprints já aparecem pela Europe PMC.
- arXiv, DOAJ e OpenAIRE não oferecem alguns filtros (tipo de estudo, idioma, acesso aberto, ordenação); a tela avisa quando um filtro não foi aplicado.

## 2026-10 — Nove novas abas no Laboratório de IA

### Adicionado
- Enfermagem, Farmácia, Nutrição, Psicologia, Direito e Políticas, Educação, Agro e Veterinária, Biotecnologia e Para o Paciente, com 23 prompts novos (mesma fábrica, restrição "somente a fonte" e testes de contrato).
- Abas de saúde (Enfermagem, Farmácia, Nutrição, Psicologia, Para o Paciente) são clínicas: sem redução de raciocínio e com avisos de que não substituem orientação profissional. Doses, interações e reações na Farmácia seguem extrativas, sem IA.
- Públicos e focos novos nos filtros; no desktop as abas quebram em linhas.

## 2026-10 — Navegador de artigos (pivô do produto)

### Adicionado
- `/` passa a ser um navegador de artigos: busca com filtros (ano, tipo de estudo oficial, acesso aberto, idioma, ordenação, fonte) e paginação, página do artigo, artigos semelhantes, citações ABNT/APA/Vancouver.
- Biblioteca por conta com etiquetas, listas de leitura, link público revogável (sem expor o e-mail do dono) e exportação BibTeX/RIS/ABNT/APA/Vancouver.
- Fontes: Europe PMC (padrão) e OpenAlex (opcional, com `OPENALEX_API_KEY`). Variável `DISCOVERY_CALLS_PER_MINUTE`.
- Testes de lógica do frontend em Node (`tests/js`) e etapa no CI.

### Alterado
- A interface de IA anterior foi para `/ia`; "Analisar com IA" no artigo abre `/ia?artigo=...` preenchido.

### Corrigido
- `markdown_lite`: byte NUL no texto forjava marcador interno e causava `IndexError`.

### Limitações conhecidas
- Caminho PostgreSQL da biblioteca testado apenas com SQLite; OpenAlex testado só com respostas simuladas e verificação sem chave.

## 2026-10 — Fase 3: camada sem IA e botões clínicos extrativos

### Adicionado
- **"Extrair do artigo (sem IA)"** em todas as abas: resumo organizado em seções com o texto original, números com a frase de origem, tipo de estudo do registro oficial (Europe PMC) e metadados. Zero token, nada gerado.
- **Botões de dose, conduta, interações e reações adversas passam a ser extrativos** (trechos copiados do resumo ou "Nada encontrado"). As versões geradas por IA ficam atrás de `ENABLE_GENERATIVE_CLINICAL=1`, cada uma bloqueada se o resumo não traz o tema.
- **Pré-condição `requires`:** Populações Especiais e Alertas e Contraindicações só chamam o modelo se o resumo trouxer o tema; caso contrário respondem sem gastar token.
- `POST /api/extract`; reconhecimento de rótulos em inglês, português e espanhol (com dois-pontos ou ponto) e de termos em espanhol.
- Aviso clínico próprio para conteúdo extraído (não afirma "gerado por IA").

### Testes
- De 733 para 792 (extração, Europe PMC, serviço sem IA, bloqueio, flag, API, XSS). Validado com um artigo real da Europe PMC, sem nenhuma chamada ao Groq.

## 2026-10 — Fase 2: custo por chamada, injeção e erros do provedor

### Adicionado
- **Opções de geração** (`generation.py`): temperatura 0,2, teto de saída por nível de detalhe e esforço de raciocínio. O raciocínio reduzido (`low`) só vale para 13 botões de baixo risco e **nunca nas abas clínicas** (medido: −54% de saída, −27% do total nesses botões).
- **Resposta cortada** (`finish_reason=length`) recebe aviso e não vai para o cache; resposta vazia vira erro claro.
- **Defesas contra injeção de prompt em código** (`injection.py`): frases do texto-fonte que parecem ordens ao modelo são removidas antes da análise e o usuário é avisado; respostas com menos de 120 caracteres são descartadas. Padrões estreitos para não apagar frases científicas legítimas.
- **Limpeza de boilerplate** de copyright/licença no fim do abstract.
- `scripts/measure_tokens.py` (mede tokens reais por botão e variante) e novos evals ao vivo (resistência do modelo cru e proteção ponta a ponta).

### Alterado
- Prompt de sistema: regras condensadas, mais duas regras (sem percentuais derivados; sem variantes de "Não descrito"); estrutura original preservada.
- **Erros do provedor** viram mensagens seguras: 429 amigável sem expor ID de organização; outros erros HTTP mostram só o código.
- Eval de dosagem passou a aceitar qualquer redação equivalente de "não descrito".

### Achados (ver `docs/roadmap/plano-economia-de-tokens.md`)
- Só o prompt não basta contra injeção: o modelo cru cede em ~20 a 40% das tentativas, inclusive com o prompt original.
- O Groq limita o plano gratuito a 200.000 tokens/dia por modelo; testes ao vivo consomem a cota da produção.

### Testes
- De 667 para 733 (opções, truncamento, injeção, limpeza, erros do provedor).

## 2026-10 — Economia de tokens: medição, cache e cotas (Fases 0 e 1)

### Adicionado
- **Registro de uso de tokens** por chamada, botão e aba (`usage.py`): usa o `usage` informado pelo Groq (estimativa quando ausente), emite uma linha de log estruturada sem conteúdo nem dados pessoais e agrega média, p95 e taxa de acerto de cache. Relatório em `GET /api/admin/usage` (exige `ADMIN_TOKEN`; 404 se não configurado).
- **Cache de resultados** (6 h): repetir a mesma análise custa 0 token e responde em milissegundos. Chave estável entre PMID, URL e DOI do mesmo artigo.
- **Deduplicação de requisições simultâneas** (`SingleFlight`): análises idênticas ao mesmo tempo chamam o modelo uma vez.
- **Cotas diárias de tokens por identidade** (`quota.py`): visitante 60.000 e conta 200.000 por padrão (`DAILY_TOKEN_BUDGET_GUEST` e `DAILY_TOKEN_BUDGET_USER`, 0 = sem limite).
- A interface mostra se o resultado veio do cache, os tokens da chamada e a cota restante.

### Alterado
- `LLMBackend`/`LLMRouter` ganham `complete()` (texto + uso); `generate()` virou atalho.
- `AnalysisService.analyze/audit/compare` retornam `Reply`, uma `str` com `cached`, `tokens` e `quota_remaining`.

### Testes
- De 613 para 667 (uso, cache, concorrência, cotas, API). Verificado no navegador com o Groq real.

## 2026-10 — Gradio substituído por FastAPI e frontend próprio

### Alterado
- **Interface totalmente nova** em preto e laranja (tema claro opcional), responsiva, acessível (foco visível, abas por teclado, `aria-live`) e sem recursos de terceiros em tempo de execução: HTML (Jinja2), CSS e JS próprios; sem CDN nem fontes externas.
- **Backend FastAPI** com API JSON (`/api/analyze`, `audit`, `compare`, `cite`, `search`, `auth/*`) reutilizando `workflow.py` sem alterações. Gradio e ~40 dependências transitivas removidos (ver ADR-006).
- **Contas e sessões reais**: cookie HttpOnly assinado por HMAC; o limite de uso passa a ser por conta (visitantes por IP). `SESSION_SECRET` obrigatório em produção (gerado no `render.yaml`).
- Respostas do modelo renderizadas no servidor por um renderizador de markdown próprio que escapa todo HTML (testado contra payloads de XSS).

### Segurança
- CSP `default-src 'self'`, checagem de `Origin` (CSRF), validação de tamanho em todos os campos, HSTS em produção, `docs`/`openapi` desativados, erros 500 sem vazamento.
- Assets versionados por hash de modificação (cache longo sem JS/CSS desatualizado).

### Testes
- De 548 para 610+: API (autenticação, 429, CSRF, validação, XSS, cabeçalhos), sessões, markdown e invariantes de página. Suíte validada também em um ambiente limpo com apenas as dependências de produção.

## 2026-10 — Novas abas de área

### Adicionado
- **Sete abas de análise** (antes 2): Geral, **Acadêmico**, Medicina, **Ambiental**, **Saúde Pública**, **Tecnologia e IA**, **Engenharias**, além de Pesquisa e Contas.
- **33 prompts novos**, gerados por `prompt_builders.make_builder` a partir de `prompt_specs.py` (dados). A fábrica anexa sempre a restrição "somente a fonte", então nenhum prompt novo pode omiti-la.
- **Referências ABNT, APA e Vancouver sem IA** (`citations.py`): metadados do Crossref (DOI) ou Europe PMC (PMID/PMCID), formatados por código. Campos ausentes são omitidos, nunca inventados.
- Fontes oficiais ambientais no anexo de verificação (MMA, IBAMA, CONAMA, ODS), marcadas como "pendente de revisão" até validação por especialista.
- Novos públicos-alvo e focos por aba, aplicados ao prompt de sistema.
- Medicina ganhou PICO, Crítica Metodológica, Dados Estatísticos, Interações Medicamentosas e Reações Adversas.

### Alterado
- Seção "Educacional" saiu da aba Geral e vive somente em Acadêmico.
- Especificação das abas movida para `pages.py` (dados); `ui.py` ficou com a mecânica de montagem.
- Abas de saúde (Medicina e Saúde Pública) exibem o aviso clínico persistente.
- Testes: de 293 para 548 (invariantes de todas as abas, fábrica de prompts, citações).

## 2026-10 — Refatoração arquitetural, segurança e qualidade

### Segurança
- `security.safe_get`: bloqueio de SSRF (esquema, IPs privados/loopback/metadata, revalidação a cada redirect, limite de redirects e de bytes) em toda busca de página feita a pedido do usuário.
- Rate limiting por cliente (janela deslizante) nas chamadas de LLM e em login/cadastro; IP do cliente lido do último hop confiável de `X-Forwarded-For`.
- Delimitadores do prompt agora são neutralizados na fonte (um abstract hostil não consegue "fechar" o bloco) e a fonte é truncada.
- Contas: validação de e-mail e política de senha, limite máximo (anti-DoS no PBKDF2), custo de hash equalizado para usuário inexistente, mensagem de login genérica.

### Fidelidade ao texto-fonte
- `grounding.py`: números da resposta (doses, %, decimais) ausentes do título/resumo são sinalizados automaticamente.
- Aviso clínico persistente na aba Medicina e nas comparações clínicas.
- Prompts `Resumo Clínico` passaram a declarar explicitamente a restrição "somente a fonte" (descoberto por teste de contrato).
- Avaliação de fidelidade com LLM real em `evals/` (opt-in).

### Arquitetura
- Camadas explícitas: `domain` → `workflow` (casos de uso sem Gradio) → `ui` (páginas declarativas). `biomedical_data_digger.py` reduzido a composição.
- `LLMBackend` (Protocol) com `GroqBackend`/`OllamaBackend` e `LLMRouter`; cliente criado sob demanda.
- `ArticleRepository` com cache LRU+TTL e chave canônica (PMID, URL do PubMed e DOI equivalentes compartilham entrada).
- `account_store` sem efeitos colaterais no import (`get_account_store()`).
- `Article` imutável e erros de domínio tipados (`DiggerError`, `ArticleNotFoundError`, `BackendUnavailableError`).

### Corrigido
- Botões duplicados/enganosos: "Avaliação Crítica", "Explicação para Iniciantes", "Questões de Discussão" e "Impacto na Sociedade" usavam o prompt de outro botão. "Aplicações no Mundo Real" (clone de "Implicações Práticas") foi removido. Um teste impede a regressão.
- `UnboundLocalError` potencial em `_title_lookup`; `resolve_article` sem retorno em entradas não reconhecidas.
- `_normalize_doi` não era idempotente (achado por teste de propriedade).
- Chamadas HTTP sem timeout (Europe PMC); `print` substituído por logging.
- Filtro de área casava substrings ("law" em "flaw"); agora casa início de palavra.
- Auditoria de resposta agora também disponível na aba Medicina.

### Tooling
- `pyproject.toml` (ruff, mypy, pytest, coverage ≥ 80%), `requirements-dev.txt`, CI no GitHub Actions (3.10/3.11), pre-commit.
- Testes: de 41 para 290+ (unitários, contrato de prompts, propriedades, smoke da UI).
- Scripts avulsos de PDF movidos para `tools/pdf/`.

## 2026-09 — Busca e documentação

### Adicionado
- Busca por palavras-chave agregada em Europe PMC, OpenAlex, Semantic Scholar, Crossref e arXiv.
- Filtros de pesquisa para tecnologia, engenharias, química, física, matemática, ciências sociais, psicologia, economia, educação, direito, sustentabilidade e agricultura.
- Índice de Relevância Bibliográfica com impacto por ano, atualidade, completude dos metadados e cobertura da fonte.
- Documentação específica da busca em `docs/features/busca-artigos.md`.
- Testes automatizados para busca multi-fonte, filtros gerais e cálculo do índice.

### Alterado
- README atualizado para refletir Groq, Ollama, Render, testes e fontes atuais.
- A interface passou a exibir "Relevância bibliográfica" em vez de apresentar o indicador como confiabilidade científica.
- A normalização passou a usar corretamente citações e metadados de cada fonte.

## 2026-09 — Sessão atual

### Adicionado
- 6 novos tipos de análise: Crítica Metodológica, Dados Estatísticos, Pergunta PICO, Alertas e Contraindicações, Checklist Pré-Conduta, Aplicabilidade Brasileira
- Sistema de filtros de personalização (público-alvo, tom, idioma, nível de detalhe, foco temático)
- Cache de artigos em memória (evita chamadas duplicadas às fontes externas)
- Histórico de sessão (últimas 10 consultas)
- Função `fetch_full_text()` para extrair texto completo do XML da Europe PMC (implementada, não exposta na UI)
- Documentação técnica completa (docs/)
- 11 novos botões organizados em 6 seções com accordions: Visão Geral, Clínico/PS, Acadêmico/Pesquisa, Contexto Brasileiro, Educacional, Avaliação do Artigo
- Botão "Confiabilidade do Artigo" para análise crítica baseada no conteúdo do artigo
- Redesign visual completo: tema escuro/claro com toggle ☀️/🌙, CSS customizado, fontes Inter + JetBrains Mono, botões com hover e glow azul
- **Sistema universal de busca de artigos:** suporte a PMID, PMCID, DOI, arXiv ID, OpenAlex ID, Semantic Scholar ID e URLs completas
  - `detect_input_type()` — detecção automática do tipo de ID
  - `fetch_by_doi()` — busca via Semantic Scholar + CrossRef fallback
  - `fetch_by_arxiv()` — busca via arXiv API
  - `fetch_by_openalex()` — busca via OpenAlex (reconstrói abstract do índice invertido)
  - `fetch_by_semantic_scholar()` — busca via Semantic Scholar por ID
  - `resolve_article()` — ponto de entrada universal

### Alterado
- Modelo padrão alterado para GPT-OSS 20B (mais rápido no free tier do Render)
- Dropdown de modelos simplificado para mostrar nomes reais da conta Groq
- Botão "Resumo Simples" substituído por "Resumo" (neutro, personalizável via filtros)
- Emojis removidos dos botões (visual mais profissional)
- Layout alterado para 1/3 controles + 2/3 output (mais espaço para leitura)
- Campo de busca aceita qualquer formato — não mais restrito a PMID/PMCID
- INTRO_TXT e INST_TXT atualizados para refletir todos os formatos aceitos

### Revertido
- Streaming de resposta revertido após causar lentidão no Render free tier (ver ADR-003)
- Toggle "Rápido / Completo" implementado e revertido a pedido do usuário — `fetch_full_text()` mantida no código

### Corrigido
- Bug recorrente: `generate_response is not defined` — função sobrescrita por código duplicado nas edições
- Arquivo corrompido com UI duplicada — reconstruído via sub-agente

---

## Histórico anterior

### Funcionalidades originais (pré-sessão atual)
- Busca de artigos via Europe PMC (PMCID e PMID)
- Sumário, Resumo Acadêmico, Resumo Clínico, Resumo Simples
- Botão "Medicamentos / Protocolos"
- Suporte Groq API + Ollama local
- Deploy no Render
- .env + .gitignore para proteção de secrets
