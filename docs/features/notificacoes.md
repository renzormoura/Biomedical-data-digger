# Feature: Interesses e avisos de artigos novos (sininho)

## Objetivo
O usuário escolhe o que quer acompanhar (áreas, subtemas, idiomas e palavras-chave) e recebe um aviso no sininho quando aparece um artigo novo sobre isso.

## Status
Em produção, com limites. Os avisos aparecem no sininho, ao abrir o site, e por uma verificação agendada que precisa ser ativada (ver "Verificação agendada"). **Não há e-mail nem notificação do navegador.**

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
