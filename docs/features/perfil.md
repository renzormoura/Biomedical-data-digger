# Feature: aba Perfil (perfil de uso, interesses, conta e dados) e pacote "Saúde no Brasil"

## Objetivo
Reunir numa só aba tudo o que é da pessoa: quem ela é no produto, o que ela acompanha e os dados dela. O **Perfil** (`#/perfil`) abre pelo **botão com o nome do usuário** (o e-mail) no canto superior direito, no computador e no celular; não há item "Perfil" no menu nem na barra inferior. O botão fica destacado quando o Perfil está aberto. Tem cinco seções.

Origem do perfil de uso: `docs/roadmap/plano-relatorio-de-tema.md`, seção 2 e fase 4.

## Seções

| Seção | Endereço | O que tem |
|---|---|---|
| **Visão geral** | `#/perfil` | E-mail e "membro desde"; contadores (artigos salvos, listas, relatórios, análises salvas) que levam à biblioteca; resumo do perfil de uso e dos interesses (temas, palavras-chave, avisos não lidos, última verificação); botão **Sair da conta** |
| **Perfil de uso** | `#/perfil/uso` | O que a pessoa faz e o pacote de saúde (ver abaixo) |
| **Interesses e alertas** | `#/perfil/interesses` | Áreas, subtemas, idiomas e palavras-chave dos alertas (a antiga página "Meus interesses", agora dentro do Perfil); `#/interesses` redireciona para cá |
| **Notificações** | `#/perfil/notificacoes` | Liga e desliga cada tipo de aviso do sininho (retratação, mudança regulatória, novidades dos relatórios e artigos novos nos interesses) e explica como funcionam; botão "Verificar agora" |
| **Conta e dados** | `#/perfil/conta` | Trocar senha; **baixar uma cópia dos dados** (JSON); **excluir a conta** |

Sem conta, o mesmo botão mostra "Entrar" e abre o diálogo de entrada; quem acessa `#/perfil` sem conta vê um convite para entrar. "Sair da conta" fica na Visão geral do Perfil. O sininho e os atalhos da página inicial apontam para a seção de interesses.

## Perfil de uso e pacote "Saúde no Brasil"
O produto é um só, com um núcleo para qualquer área. O perfil só **destaca** ferramentas e **liga ou desliga** o pacote de saúde (ANVISA, Conitec e Rename); nunca bloqueia uma função do núcleo.

- **Perfis:** estudante, pesquisador, profissional de saúde ou farmácia, consultoria ou assessoria, outro uso. Só "profissional de saúde ou farmácia" liga o pacote por padrão; a caixa "Mostrar a situação de medicamentos no Brasil" muda isso à parte.
- **Primeira entrada:** quem tem conta e ainda não escolheu vê a pergunta "Como você vai usar o Biomedical Data Digger?", com "Agora não" (guardado em `localStorage`).
- **Sem perfil ou sem conta, o pacote fica visível**, para não esconder o diferencial de quem ainda não disse o que faz.

| | Pacote ligado | Pacote desligado |
|---|---|---|
| Página do artigo | Cartão "Situação no Brasil" | Sem o cartão |
| Relatório de tema | Seção "Situação no Brasil (medicamentos)" | Seção escondida, **a menos que o relatório já tenha substâncias confirmadas** |
| Página inicial | Atalhos "Para você" do perfil | Idem |

## Conta e dados
- **Trocar senha** (`POST /api/account/password`): pede a senha atual e a nova duas vezes; a nova segue a mesma regra do cadastro e precisa ser diferente da atual. Passa pelo mesmo limite de tentativas do login. A sessão é um cookie assinado sem estado no servidor: **trocar a senha não encerra a sessão de outros aparelhos** (ela expira em até 7 dias).
- **Baixar meus dados** (`GET /api/account/export`): `meus-dados.json` com a conta (sem senha), perfil, biblioteca (com etiquetas), listas, análises salvas (com o texto), relatórios (estudos, notas, histórico), interesses e avisos. Portabilidade, no espírito da LGPD.
- **Excluir conta** (`DELETE /api/account`): pede a senha e **não tem volta**. Apaga a conta e tudo o que ela guardou: biblioteca, listas (incluindo os links compartilhados), análises, relatórios (versões, histórico e substâncias), interesses, linhas de base, avisos e perfil. A sessão é encerrada e o mesmo e-mail pode ser cadastrado de novo, vazio.
- **Conta que deixou de existir:** o servidor confere (com cache de 30 segundos) se a conta da sessão ainda existe; um cookie de conta excluída, em outro aparelho, deixa de valer em até 30 segundos. Se o banco de contas estiver fora do ar, a sessão não é derrubada.

## Código
- `account_routes.py`: resumo, troca de senha, exportação e exclusão. `account_store.py`: `exists`, `created_at`, `change_password`, `delete_user`. `delete_user_data` em `LibraryStore`, `ReportStore` e `AlertStore`; `ProfileStore.delete`.
- `profiles.py`: perfis, `ProfileStore` (tabela `user_profiles`). `web.py`: confere a conta na sessão e entrega o perfil na primeira pintura (`data-profile` e `data-health-pack` no botão da conta).
- `static/browse.js`: `renderProfile` (abas), `profileOverview`, `profileUse`, `profileAccount`, `profileForm`, `askProfile`, `showHealth` e os atalhos.

## API
| Rota | Quem | O que faz |
|---|---|---|
| `GET /api/profile/options` | público | Perfis, rótulos e o padrão do pacote de cada um |
| `GET /api/profile`, `PUT /api/profile` | logado | Perfil de uso e pacote de saúde |
| `GET /api/account` | logado | E-mail, data de criação, contadores, resumo de interesses e perfil |
| `POST /api/account/password` | logado | Troca de senha |
| `GET /api/account/export` | logado | Cópia dos dados em JSON |
| `DELETE /api/account` | logado | Exclusão da conta e dos dados |

## Limites
- Não há troca de e-mail, recuperação de senha por e-mail, confirmação de e-mail, verificação em duas etapas nem encerramento remoto de outras sessões. Isso exige envio de e-mail e sessões com estado no servidor.
- O perfil não muda a busca, os alertas nem os modelos de relatório, só os destaques e o pacote de saúde.
- A recusa da pergunta de perfil fica no navegador, não na conta.
- A exclusão apaga o que está no banco da aplicação. Cópias em backups do provedor de banco seguem as regras dele.
- Os dados do pacote de saúde continuam sem revisão de farmacêutico ou médico.
- As tentativas de senha (troca e exclusão) contam no limite de 5 por minuto do login.

## Testes
`tests/test_account.py` (armazenamento de contas, rotas, exportação sem senha, exclusão completa com isolamento entre contas, sessão de conta excluída), `tests/test_profiles.py` (perfil de uso) e `tests/js/browse-lib.test.js` (rotas `#/perfil/...`).
