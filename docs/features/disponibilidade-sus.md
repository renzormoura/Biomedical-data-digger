# Funcionalidade: Disponibilidade no SUS

## Objetivo
Responder, para o que um artigo estuda ou para um termo digitado, **"isso existe no SUS?"**: medicamentos, cirurgias, exames, técnicas e produtos. A resposta vem de **bases oficiais, por consulta em código, sem IA e sem rede** em tempo de uso. Quando há IA (Laboratório), ela só explica o que as bases já mostraram.

É parte do pacote **Saúde no Brasil** (ver [Saúde no Brasil](saude-no-brasil.md)): aparece para quem tem o pacote ligado e para quem ainda não tem conta ou perfil.

## As quatro bases
| Base | O que diz sobre o item |
|---|---|
| **Rename 2024** | Medicamento essencial da lista nacional, com o componente de financiamento (básico, estratégico, especializado) |
| **Conitec** | Decisão do Ministério da Saúde sobre incorporar, ampliar, excluir ou não incorporar o medicamento (vale a decisão mais recente) |
| **ANVISA** | Registro ativo: o produto pode ser vendido no país. **Não** indica oferta pelo SUS |
| **SIGTAP** (DATASUS) | Tabela de Procedimentos, Medicamentos, Órteses, Próteses e Materiais do SUS: o catálogo de tudo que o SUS codifica e paga. É a fonte de **cirurgias, exames e técnicas**, e também traz os medicamentos do Componente Especializado (grupo 06) |

## O veredito de cada item
| Veredito | Quando |
|---|---|
| **Consta no SUS** | Medicamento na Rename ou com código de medicamento na SIGTAP; procedimento, exame, técnica ou produto com código na SIGTAP |
| **Incorporado ao SUS** | Sem Rename nem SIGTAP, mas a decisão mais recente da Conitec é incorporar, ampliar, manter ou aprovar |
| **Avaliado e não incorporado** | A decisão mais recente da Conitec é não incorporar ou não ampliar |
| **Excluído do SUS** | A decisão mais recente da Conitec é excluir |
| **Registrado, sem oferta encontrada** | Só há registro ativo na ANVISA |
| **Não encontrado nas bases** | Nada em nenhuma base. Pode ser outro nome, ou o SUS pode cobrir o item sob outro código |

Cada item traz os **detalhes por base** (componente da Rename, decisão e portaria da Conitec, número de registros na ANVISA, procedimentos da SIGTAP com código, grupo e complexidade) e a lista de fontes. Procedimentos aparecem em uma lista recolhível, com até 8 por item.

### Avisos em todo resultado
- Constar em uma lista oficial **não garante** que a unidade de saúde da pessoa tenha o item: a oferta depende do município, do serviço habilitado e do estoque.
- Os dados são de instantâneo e **ainda sem revisão** de farmacêutico ou médico.
- A interface mostra a competência da SIGTAP e avisa se alguma base estiver defasada.

## Onde aparece
1. **Página do artigo → "Disponibilidade no SUS":** lista o que o resumo parece estudar, cada item com a origem ("no texto: *bariatric surgery*") e o tipo de ligação (sinônimo conhecido ou nome parecido). Todas são **possíveis correspondências, a confirmar**. Abaixo, um campo para buscar qualquer termo em português.
2. **Laboratório de IA → botão "Disponib. SUS":** o prompt agora recebe o resultado das bases como contexto marcado **[BASES OFICIAIS]**. O modelo repete o veredito sem acrescentar nada, trata o que não está nas bases como **[NÃO VERIFICADO]** (nunca como "não está no SUS") e lembra que constar nas bases não garante a oferta local.

## Como o artigo é lido
- **Medicamentos:** a mesma ligação inglês ↔ português do pacote Brasil (tabela de sinônimos mais cognatos).
- **Cirurgias, exames e técnicas** (`brasil/sigtap.py`), em duas etapas:
  1. **Sinônimos curados** (`dados_brasil/aliases_procedimentos.json`, cerca de 90 termos): *hip replacement* → artroplastia total de quadril, *cesarean section* → operação cesariana, *bariatric surgery* → gastroplastia, *hemodialysis*, *chemotherapy*, *MRI*, transplantes etc. Cada termo foi conferido contra a tabela. Esses podem aparecer como "não encontrado".
  2. **Cognatos por sufixo:** *-ectomy, -otomy, -ostomy, -plasty, -scopy, -graphy, -pexy, -rrhaphy, -centesis* viram *-ectomia, -otomia...* com ajuste de grafia (*ph/f, y/i, ch/c*) e só valem se a tabela tem a palavra, com no máximo 2 letras a mais na raiz portuguesa (assim *mastectomy* não liga a *mastoidectomia*). Esses **nunca** aparecem como "não encontrado": o "não achei" só vale para o que sabemos ligar.
- **Vacinas ficam de fora de propósito:** pertencem ao Programa Nacional de Imunizações, que não está na SIGTAP, e dizer "não consta" seria enganoso.

## Busca manual
`GET /api/brasil/sus?q=` aceita medicamento, cirurgia, exame, técnica ou produto, em português e sem acento. Se o termo é um medicamento reconhecido, os exames de mesmo nome são omitidos (buscar "insulina" não deve listar "dosagem de insulina"); para exames, refine: "dosagem de insulina". A busca casa por palavra inteira, com prefixo e plural simples ("operações cesarianas" acha "operação cesariana"), exige todas as palavras e põe o nome exato primeiro.

## Atualização dos dados
`python scripts/atualizar_sigtap.py` descobre a tabela mais recente na página do DATASUS, baixa o ZIP por FTP (servidor `ftp2.datasus.gov.br`, tamanho limitado, link de outro servidor é recusado), lê os arquivos de largura fixa em latin-1 pelo layout publicado em cada pacote e grava `dados_brasil/sigtap.json` (procedimentos, grupos e subgrupos; cerca de 5.000 itens e 370 KB). Menos de 3.000 procedimentos é tratado como leitura errada. A tabela sai **todo mês**; o aviso de defasagem é de 120 dias, porque os procedimentos mudam pouco. Ver [Atualização dos dados do Brasil](../operacao/dados-brasil.md).

## API
`GET /api/brasil/sus?q=` (pública, 3–100 caracteres) e `GET /api/discover/sus?ref=`. Ambas devolvem `items`, `notice` e `meta` com as quatro bases. Os itens trazem `kind`, `name`, `verdict`, `label`, `tone`, `source`, `method`, `details`, `sources`, `totalProcedures` e `procedures`. Sem a tabela no servidor, respondem 503. Ver [Referência da API](../api/referencia.md).

## Limites
- **Cirurgias novas ou com nome diferente** podem não ser achadas; "não encontrado" quer dizer "não achamos nas bases", não "o SUS não oferece".
- **Tecnologias não medicamentosas da Conitec** (procedimentos e produtos avaliados que ainda não têm código na SIGTAP) **não entram**: hoje o instantâneo da Conitec guarda só medicamentos (782 de 1.251 linhas). É o próximo passo natural.
- Só a competência mais recente da SIGTAP é guardada; não há histórico de quando um procedimento passou a existir.
- Sem revisão de especialista.

## Licenças
A SIGTAP é dado público do DATASUS (Ministério da Saúde); citamos a fonte e a competência, e os termos de uso do DATASUS devem ser confirmados antes do lançamento comercial. A **Rename** continua com o impedimento de licença descrito em [Licenças e termos das fontes](../legal/licencas-e-termos.md).

## Arquivos
`brasil/sigtap.py`, `brasil/sigtap_build.py`, `brasil/disponibilidade.py`, `dados_brasil/sigtap.json`, `dados_brasil/aliases_procedimentos.json`, `scripts/atualizar_sigtap.py`, `contexto_brasil.bloco_disponibilidade`, `routes/discover.py` e `routes/payloads.py`. Testes: `tests/test_sus_availability.py`.
