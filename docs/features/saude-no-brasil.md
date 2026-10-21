# Funcionalidade: Pacote "Saúde no Brasil" (ANVISA, Conitec e Rename)

## Objetivo
Para quem trabalha com saúde no Brasil, cruzar os **medicamentos citados nos artigos** com três bases oficiais e dizer, com fonte e data, se a substância tem registro, se foi avaliada para o SUS e se consta na lista nacional de medicamentos essenciais. **Tudo por consulta em código, sem IA e sem rede** em tempo de uso.

É um pacote **opcional**: o núcleo do produto serve qualquer área. O pacote vem ligado por padrão para o perfil "Saúde" e fica visível para quem ainda não tem conta ou perfil (ver [Perfil](perfil.md)).

## As três bases
| Base | O que informa | Dados no repositório | Aviso de defasagem |
|---|---|---|---|
| **ANVISA** — medicamentos registrados (dados abertos, DATAVISA) | Por substância: registros ativos e inativos, categorias regulatórias (genérico, similar, novo, biológico…), classes, nº de empresas com registro e validade mais distante | `dados_brasil/anvisa.json`: 3.857 substâncias, 72.824 registros ativos (arquivo da ANVISA de 13/10/2026; extraído em 17/10/2026) | 60 dias |
| **Conitec** — recomendações sobre tecnologias avaliadas (planilha oficial) | Tecnologia, indicação, recomendação, decisão do Ministério da Saúde, portaria, data de publicação e links dos relatórios técnico e da sociedade | `dados_brasil/conitec.json`: 782 decisões sobre medicamentos (planilha de 15/06/2026; 1.251 linhas no total, só medicamentos entram) | 60 dias |
| **Rename 2024** (2ª ed., 2025) — Relação Nacional de Medicamentos Essenciais | Componente de financiamento (básico, estratégico, especializado), apresentações | `dados_brasil/rename.json`: 968 itens, 514 substâncias (extraído do PDF oficial por script) | 400 dias |

Cada resposta traz a fonte, a data do arquivo e a data da extração. Se a base estiver velha, a interface avisa.

## O que a pessoa vê
- **Na página do artigo:** o bloco **Situação no Brasil** lista as substâncias que o resumo *parece* citar, cada uma como **"possível correspondência, confirme"**, com o que cada base diz (registro ativo e categorias; decisões da Conitec; componente na Rename) e os avisos obrigatórios.
- **Consulta manual:** campo para digitar a substância em português (mínimo de 3 caracteres), na página do artigo e no relatório.
- **No relatório de tema:** a seção **Situação no Brasil**, só para substâncias que **o autor confirmou**. O sistema apenas sugere nomes a partir dos resumos dos estudos incluídos (até 12 sugestões); nenhuma sugestão automática entra no documento sozinha.
- **No sininho:** avisos de **mudança regulatória** para substâncias confirmadas em relatórios (ver [Notificações](notificacoes.md)).

### Avisos que acompanham todo resultado
- Registro ativo na ANVISA significa que o produto pode ser comercializado no país; **não** que o SUS o forneça nem que haja estoque.
- Constar na Rename **não** significa disponibilidade na unidade de saúde do usuário.
- A decisão da Conitec trata da incorporação ao SUS.
- Os dados ainda **não foram revisados** por farmacêutico ou médico (pendência registrada no [Roadmap](../roadmap/roadmap.md)).

## Disponibilidade no SUS
O bloco **Disponibilidade no SUS** (página do artigo e botão "Disponib. SUS" do Laboratório) cruza estas três bases com a **Tabela SIGTAP** do DATASUS para dizer, por item, se medicamentos, cirurgias, exames e técnicas constam no SUS. Ver [Disponibilidade no SUS](disponibilidade-sus.md).

## Como funciona
1. **Instantâneos versionados.** Os dados ficam em arquivos JSON no repositório (`dados_brasil/`), gerados por scripts (`scripts/atualizar_anvisa.py`, `atualizar_conitec.py`, `atualizar_rename.py`; ver [Atualização dos dados do Brasil](../operacao/dados-brasil.md)). Nenhuma consulta de usuário faz requisição à ANVISA, Conitec ou Rename.
2. **Ligação inglês ↔ português** (`brasil/nomes.py`). Os artigos citam *metformin*, as bases dizem *metformina*. A ligação usa, nesta ordem: (a) tabela curada de sinônimos (`aliases_en_pt.json`) e (b) cognatos por regras de sufixo e grafia (ine/ina, ide/ida, ate/ato, ph/f, y/i…). Toda ligação é só *possível*: a pessoa confirma. A correspondência por distância de edição foi **removida** de propósito, porque ligava "valganciclovir" a "valaciclovir" (medicamentos diferentes): o produto prefere perder cobertura a errar a substância.
3. **Consulta unificada** (`brasil/consulta.py`): `situacao(termo)` junta ANVISA + Conitec + Rename; `situacoes_do_texto(texto)` acha as substâncias que um resumo parece citar (até 8).
4. **Casamento conservador:** normalização (minúsculas, sem acento), termo mínimo de 5 caracteres, correspondência por palavra inteira, remoção de sais e formas farmacêuticas.
5. **Contexto institucional** (`contexto_brasil.py`): orientações gerais curadas sobre SUS e vigilância sanitária usadas pelo Laboratório de IA, com ponto de origem e o aviso "pendente de revisão". Não traz listas nem recomendações específicas: o que depende disso é respondido como "não verificável".

## API
`GET /api/brasil/conitec?q=`, `GET /api/brasil/medicamento?q=`, `GET /api/discover/brasil?ref=` e `GET /api/reports/{id}/brasil`. Ver [Referência da API](../api/referencia.md).

## Licenças e uso comercial
- ANVISA e Conitec publicam dados abertos governamentais.
- **Rename:** o PDF oficial está sob **CC BY-NC-SA 4.0** (uso não comercial, com atribuição e mesma licença). **Resolver antes de cobrar pelo produto** (ver [Licenças e termos das fontes](../legal/licencas-e-termos.md)).

## Limites
- Dados de instantâneo: refletem a data de extração, não o dia de hoje.
- A extração da Rename vem de PDF por script e foi conferida por amostra.
- A ligação artigo → substância pode falhar para nomes comerciais, siglas e associações.
- Sem revisão de especialista: não usar como fonte única de decisão regulatória ou clínica.

## Arquivos
`brasil/` (`anvisa.py`, `conitec.py`, `rename.py`, `nomes.py`, `consulta.py` e os `*_build.py` que montam os instantâneos), `dados_brasil/`, `report_brasil.py`, `contexto_brasil.py`, `scripts/atualizar_*.py`. Testes: `tests/test_brasil_*.py`, `tests/test_contexto_brasil*.py`.
