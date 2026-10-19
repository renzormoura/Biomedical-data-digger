# Feature: Notificações do sininho (interesses, retratações, mudanças regulatórias e relatórios)

## Objetivo
O usuário escolhe o que quer acompanhar (áreas, subtemas, idiomas e palavras-chave) e recebe um aviso no sininho quando aparece um artigo novo sobre isso.

## Status
Em produção, com limites. Além dos artigos novos por interesse, o sininho avisa de **retratação**, **mudança regulatória** e **novidades dos relatórios** (ver a seção "Todos os tipos de aviso"). Os avisos aparecem no sininho, ao abrir o site, e por uma verificação agendada que precisa ser ativada (ver "Verificação agendada"). **Não há e-mail nem notificação do navegador.**

## Todos os tipos de aviso do sininho

O sininho é a **única** forma de aviso por enquanto (e-mail, push e outros canais virão depois). Entram os avisos de prioridade **alta** e **média**:

| Tipo | Prioridade | Quando avisa |
|---|---|---|
| **Artigo retratado** (`retratacao`) | Alta | Um artigo da sua biblioteca, de uma lista ou de um relatório (estudos incluídos) passou a constar como retratado na fonte |
| **Mudança regulatória** (`regulatorio`) | Alta | Uma substância confirmada em um relatório teve mudança na Conitec (decisão nova ou removida), na Rename (passou a constar, deixou de constar ou mudou de componente) ou na ANVISA (passou a ter ou perdeu o registro ativo) |
| **Novidades dos relatórios** (`relatorio-lista`) | Média | Entraram artigos novos na lista de origem de um relatório |
| **Artigos novos nos interesses** (`novo-artigo`) | Média | O que está descrito acima neste documento |

Avisos de prioridade alta e não lidos aparecem **no topo** do painel, com o selo de cor (Retratado, Regulatório). Cada tipo pode ser ligado ou desligado em **Perfil > Notificações** (tudo vem ligado).

### Como cada aviso é produzido (`notifications.py`)
- **Retratação.** O sistema junta os artigos que a conta guarda (biblioteca, listas e estudos incluídos em relatórios) e **reconfere cada um na fonte uma vez por semana** (até 15 por verificação de uma conta e 40 por execução agendada, para respeitar o limite das fontes). O resultado fica numa tabela global (`retraction_status`), então o mesmo artigo guardado por várias pessoas é conferido uma vez só. Um artigo que já estava marcado como retratado quando foi guardado também avisa. Só funciona quando a fonte do registro informa a retratação (Europe PMC, PubMed e OpenAlex); **correções (errata) não são detectadas**.
- **Mudança regulatória.** Para cada substância confirmada em um relatório, guarda um resumo do estado (decisões da Conitec, componente na Rename, registro ativo na ANVISA) e compara com o da verificação seguinte. **A primeira vez só memoriza o estado**, sem avisar. Como as bases são instantâneos do repositório (atualizados por scripts), uma mudança só aparece depois que um instantâneo novo é publicado no site. Um aviso novo da mesma substância substitui o anterior ainda não lido.
- **Novidades dos relatórios.** Para cada relatório com lista de origem, compara a lista com o que já está no relatório. Um aviso novo do mesmo relatório substitui o anterior ainda não lido, e o mesmo conjunto de artigos não avisa duas vezes.
- Nenhum texto de aviso é gerado por IA: tudo vem de comparação por código.

### Quando verificam
- Com o site aberto: ao entrar e a cada 15 minutos (se a aba estiver visível), com intervalo mínimo de 6 horas (15 minutos no "Verificar agora"). **A verificação agora roda sempre**, não só para quem tem interesses, porque retratação e relatórios não dependem deles.
- Com o site fechado: a rota agendada (`POST /api/internal/alerts/run`) também executa o vigia: reconfere um lote global de artigos e depois verifica as contas vencidas (até 40 por execução). A resposta traz `watch` com `due`, `ran`, `notified`, `failed` e `refreshed`.

### API dos avisos
| Rota | O que faz |
|---|---|
| `GET /api/alerts` | Caixa unificada: cada item traz `kind`, `priority`, `title`, `body`, `href`, `topic`, `read` e, nos artigos novos, `work` |
| `POST /api/alerts/check` | Verifica agora; devolve `new`, `notified` (por tipo) e a caixa |
| `POST /api/alerts/read`, `DELETE /api/alerts` | Marcam como lido (um ou todos) e dispensam; valem para os dois tipos de aviso |
| `GET/PUT /api/notifications/prefs` | Tipos de aviso, o que cada um faz e se estão ligados |

Tabelas: `notifications`, `retraction_status`, `regulatory_state`, `watch_state` e `notification_prefs`, criadas por `NotificationStore.initialize()`. A exportação de dados e a exclusão de conta incluem os avisos.

### Limites dos novos avisos
- Retratação só é detectada nas fontes que informam; uma biblioteca grande leva alguns dias para ser conferida inteira (15 artigos por verificação, uma vez por semana cada).
- Mudança regulatória só vale para substâncias confirmadas em relatórios (é onde a pessoa diz que acompanha a substância). Os dados do Brasil seguem sem revisão de farmacêutico ou médico.
- Os avisos de relatório dependem de o relatório ter lista de origem (relatórios criados antes da fase 3 não têm).
- O texto "Constar na Rename ou ter registro não significa disponibilidade na unidade" vai em todo aviso regulatório.

## O que o usuário vê
- **Sininho** no canto superior direito, só para quem está logado. Mostra o número de avisos não lidos. O painel lista os artigos (título, revista, ano e o tema que gerou o aviso) e oferece "Marcar como lidas", dispensar um aviso, "Verificar agora" e "Gerenciar interesses". No celular o painel desce da barra, em largura total.
- **Interesses e alertas**, dentro da aba Perfil (`#/perfil/interesses`; o endereço antigo `#/interesses` redireciona):
  - 14 áreas do conhecimento (Medicina, Farmácia, Enfermagem, Odontologia, Nutrição, Biologia, Psicologia, Computação e IA, Engenharias, Física/Química/Matemática, Meio ambiente, Agrárias, Ciências sociais, Educação), cada uma com subtemas (por exemplo, Medicina: Pediatria, Oncologia, Cardiologia...). Marcar "Toda a área" acompanha a área inteira.
  - Até 4 idiomas (sem escolher nenhum, todos valem), até 5 palavras-chave livres e no máximo 15 temas.
  - O botão "Salvar interesses" grava e dispara a primeira verificação.

## Como funciona

### 1. Preferências
`interests.py` guarda o catálogo (áreas, subtemas, idiomas) e valida o que o usuário envia: área e subtema precisam existir, idiomas e palavras-chave têm limite e repetições são removidas. Cada tema tem duas listas de termos, em inglês e em português, separadas por `|`. **O primeiro termo é o que vai para as fontes**; todos servem para conferir se o artigo trata do assunto.

### 2. Verificação
`alerts.py` (`AlertService.check`) faz, para uma conta:

1. **Intervalo mínimo.** 6 horas entre verificações automáticas e 15 minutos no "Verificar agora". Salvar os interesses zera o relógio, então a verificação pode rodar logo em seguida.
2. **Buscas.** Uma por tema e idioma, e uma por palavra-chave e idioma (no máximo 24), em "Todas as fontes", ordenadas por mais recentes, do ano atual e do anterior, 20 resultados cada. Para português a busca usa o termo em português.
3. **Linha de base.** A primeira vez que uma busca roda, os artigos recentes que já existem são só **memorizados**, sem aviso. Assim artigo antigo não é tratado como novo. Cada busca (tema, idioma, palavra-chave) tem a sua linha de base, então adicionar um tema depois só memoriza o que já existia nele.
4. **Filtros do que conta como novo**, nesta ordem:
   - ignora retratados e registros sem título;
   - **relevância:** o título, as palavras-chave ou a revista precisam tratar do tema, ou o resumo precisa citar ao menos dois termos diferentes (a checagem é por palavras inteiras, sem acento, com plural simples);
   - **data:** com data de publicação conhecida, só entra o que tem até 60 dias. Datas futuras (fascículos programados) contam como "sem data", e anos absurdos (até 2099 no OpenAIRE) são descartados;
   - **ainda não visto:** o mesmo artigo vindo de duas fontes é reconhecido pelo DOI (ou pela referência da fonte) e avisa uma vez só.
5. **Tetos.** No máximo 5 avisos por tema por verificação e 30 no total. O que passa do teto é descartado sem formar fila. A caixa guarda os 200 avisos mais recentes.
6. **Falhas de fonte.** Se uma fonte não responde, a verificação segue com as outras. Se nenhuma responde, nada é registrado e o intervalo não é consumido.

### 3. Quando a verificação roda
- **Com o site aberto:** ao entrar e a cada 15 minutos (com a aba visível), o navegador chama `POST /api/alerts/check`; o servidor decide se o intervalo já passou.
- **Com o site fechado:** pela rota agendada, descrita abaixo.

### 4. Verificação agendada
`POST /api/internal/alerts/run` percorre as contas vencidas (nunca verificadas primeiro), até 40 por chamada, e devolve `{due, ran, new, failed}`. Uma conta com erro não interrompe as outras.

- Protegida por `Authorization: Bearer <ALERTS_CRON_TOKEN>`. Sem a variável de ambiente, a rota responde 404; token errado, 401.
- O fluxo `.github/workflows/alertas.yml` a chama a cada 6 horas (e manualmente por "Run workflow"), com novas tentativas porque o plano gratuito do Render dorme.
- **Para ativar:** definir `ALERTS_CRON_TOKEN` no Render (24+ caracteres) e os segredos `APP_URL` (sem barra no fim) e `ALERTS_CRON_TOKEN` no GitHub. Sem isso nada quebra, o fluxo apenas avisa que não está configurado.

## API

| Rota | Quem | O que faz |
|---|---|---|
| `GET /api/interests/options` | público | Catálogo de áreas, subtemas, idiomas e limites |
| `GET /api/interests` | logado | Interesses salvos e data da última verificação |
| `PUT /api/interests` | logado | Valida e salva (400 se inválido) |
| `GET /api/alerts` | logado | Avisos e contagem de não lidos |
| `POST /api/alerts/check` | logado | Verifica agora (`{"force": true}` usa o intervalo curto) |
| `POST /api/alerts/read` | logado | Marca um aviso (`{"id": ...}`) ou todos como lidos |
| `DELETE /api/alerts?id=` | logado | Dispensa um aviso |
| `POST /api/internal/alerts/run` | token | Verificação agendada de todas as contas |

## Dados
Tabelas criadas por `AlertStore.initialize()`, em SQLite ou PostgreSQL, sempre filtradas pela conta: `interest_prefs` (preferências e última verificação), `interest_baselines` (buscas já memorizadas), `alert_seen` (artigos já vistos, até 5.000 por conta) e `alerts` (a caixa de avisos, com um retrato dos metadados do artigo). Os módulos novos são `interests.py` e `alerts.py`; a interface está em `static/browse.js` (sininho e a seção Interesses e alertas da aba Perfil).

## Limites conhecidos
- **Não detecta a publicação em si:** detecta artigos que passaram a aparecer na busca. Um artigo pode demorar dias para ser indexado, e um antigo só indexado agora pode aparecer como novo se a fonte não informar a data.
- **Precisão boa, não perfeita:** em buscas reais a maior parte dos resultados é pertinente, mas ainda passam itens de passagem. Para português o volume é bem menor que para inglês, e alguns registros chegam sem idioma ou com o idioma da revista.
- **Temas amplos** (como "Toda a área") geram muitos artigos; só os 5 mais recentes por verificação viram aviso. Palavras-chave refinam.
- **Só os 20 mais recentes por busca:** se saírem mais que isso entre duas verificações, o excedente passa sem aviso.
- **Sem e-mail** nem notificação do navegador. E-mail exige escolher um provedor e uma chave.
- **Termos por tema** precisam de revisão por especialistas de cada área.
- **PostgreSQL (Neon)** ainda não foi validado para as tabelas de alertas; só o SQLite foi testado.

## Testes
`tests/test_alerts.py` (preferências, linha de base, filtros, tetos, intervalo, isolamento entre contas, rotas e verificação agendada) e `tests/test_published_date.py` (data de publicação em cada fonte).
