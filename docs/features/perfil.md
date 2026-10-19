# Feature: Perfil de uso e pacote "Saúde no Brasil"

## Objetivo
O produto é um só, com um núcleo para qualquer área do conhecimento. O perfil diz o que a pessoa faz para **destacar** as ferramentas certas e **ligar ou desligar** o pacote de saúde (ANVISA, Conitec e Rename). Ele nunca bloqueia uma função do núcleo (busca, biblioteca, alertas, relatórios, exportação).

Origem: `docs/roadmap/plano-relatorio-de-tema.md`, seção 2 e fase 4.

## Como funciona
- **Perfis:** estudante, pesquisador, profissional de saúde ou farmácia, consultoria ou assessoria, outro uso. Só "profissional de saúde ou farmácia" liga o pacote por padrão; o usuário pode ligar ou desligar à parte (caixa "Mostrar a situação de medicamentos no Brasil").
- **Primeira entrada:** quem tem conta e ainda não escolheu vê uma pergunta ("Como você vai usar o Biomedical Data Digger?"), com a opção "Agora não". Quem pula não é perguntado de novo naquele navegador (guardado em `localStorage`).
- **Perfil e preferências:** tela `#/perfil`, acessível pelo diálogo da conta, para mudar quando quiser.
- **Sem perfil ou sem conta, o pacote fica visível.** Ele só some se a pessoa escolher um perfil que o desliga e deixar a caixa desmarcada. Assim o diferencial não fica escondido de quem ainda não disse o que faz.

## O que muda na interface
| | Pacote ligado | Pacote desligado |
|---|---|---|
| Página do artigo | Cartão "Situação no Brasil" | Sem o cartão |
| Relatório de tema | Seção "Situação no Brasil (medicamentos)" | Seção escondida, **a menos que o relatório já tenha substâncias confirmadas** (para não prender o autor a elas) |
| Página inicial | Atalhos "Para você" do perfil (3 por perfil) | Idem |

O que o autor já confirmou num relatório continua no documento exportado, mesmo com o pacote desligado.

## Código
- `profiles.py`: `PROFILES`, `ProfileStore` (tabela `user_profiles`), `Profile`, `DEFAULT`.
- `web.py`: a página inicial recebe o perfil do servidor (`data-profile` e `data-health-pack` no botão da conta) para desenhar certo na primeira vez, sem piscar.
- `browse_api.py`: rotas. `static/browse.js`: `showHealth`, `profileForm`, `askProfile`, `renderProfile` e os atalhos.

## API
| Rota | Quem | O que faz |
|---|---|---|
| `GET /api/profile/options` | público | Perfis, rótulos e o padrão do pacote de cada um |
| `GET /api/profile` | logado | `{profile, healthPack, configured}` |
| `PUT /api/profile` | logado | `{profile, healthPack?}`; sem `healthPack`, usa o padrão do perfil (400 se o perfil não existe) |

## Limites
- O perfil não muda a busca, os alertas nem os modelos de relatório; só os destaques e o pacote de saúde. Modelos por perfil ficam para a camada comercial (fase 6).
- A recusa da pergunta fica no navegador, não na conta: em outro aparelho a pergunta aparece de novo.
- Os dados do pacote de saúde continuam sem revisão de farmacêutico ou médico.

## Testes
`tests/test_profiles.py` (padrões, isolamento entre contas, perfil que deixou de existir, rotas e atributos da página inicial) e `tests/js/browse-lib.test.js` (rota `#/perfil`).
