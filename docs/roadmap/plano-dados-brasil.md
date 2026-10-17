# Plano: dados reais do Brasil (ANVISA, RENAME e CONITEC)

Status: fases 1 (CONITEC) e 2 (ANVISA) implementadas em 2026-10-17; fase 3 (Rename) pendente. Escrito depois de verificar as três bases ao vivo.

## 1. Problema

Hoje os botões "Disponib. SUS", "Vigilância Sanitária" e "Aplicabilidade BR" só dispõem de seis parágrafos genéricos
e de um modelo de linguagem proibido de afirmar o que não sabe. O resultado correto, e quase sempre o que sai, é "não
verificável". O diferencial prometido ao público brasileiro só existe se houver **dado oficial consultado por código**,
com fonte, edição e data, sem IA no meio.

Princípio: a pergunta "este princípio ativo tem registro, está na lista nacional, foi avaliado para o SUS?" é de
consulta, não de geração. Responde-se com tabela e link, no mesmo estilo do "Extrair do artigo (sem IA)".

## 2. O que cada base oferece (verificado)

| Base | Formato e acesso | Conteúdo útil | Atualização | Limites |
|---|---|---|---|---|
| **ANVISA, medicamentos registrados** | CSV aberto, sem login: `dados.anvisa.gov.br/dados/DADOS_ABERTOS_MEDICAMENTOS.csv` (45,9 MB, modificado em 13/10/2026). Dicionário de dados em PDF no mesmo domínio. Separador `;`, codificação Latin-1 | `NOME_PRODUTO`, `PRINCIPIO_ATIVO`, `CLASSE_TERAPEUTICA`, `CATEGORIA_REGULATORIA`, `SITUACAO_REGISTRO`, `NUMERO_REGISTRO_PRODUTO`, `DATA_VENCIMENTO_REGISTRO`, `EMPRESA_DETENTORA_REGISTRO` | Diária (segundo a documentação, extraída do DATAVISA) | Registro **não** significa disponível no SUS. Nomes em português, sem equivalente em inglês |
| **RENAME 2024** | Só PDF (252 páginas) e o painel "Rename em Tempo Real" (sem exportação documentada). Página oficial: `gov.br/saude/pt-br/composicao/sectics/rename`. Portaria GM/MS nº 6.324/2024 | Medicamentos e insumos por DCB, forma farmacêutica e componente de financiamento (básico, estratégico, especializado) | Edição a cada dois anos, com alterações no painel | Sem planilha oficial. Constar na lista nacional **não** garante estoque na unidade do usuário |
| **CONITEC, recomendações** | Planilha Excel aberta (127 KB, 1.251 linhas): `gov.br/conitec/pt-br/midias/dados-em-excel/recomendacoesdaconitec_AAAAMMDD.xlsx`. O nome do arquivo muda com a data | `ANO`, tecnologia e indicação, relatório técnico, relatório para a sociedade, recomendação final (incorporar, não incorporar, ampliar, excluir...), decisão do MS, portaria, data, tipo e indicação | Atualizada pela Conitec (página modificada em 18/08/2026) | Nome livre da tecnologia, em português; o link do arquivo precisa ser descoberto na página |

Fontes consultadas: [dados.anvisa.gov.br](https://dados.anvisa.gov.br/dados/DADOS_ABERTOS_MEDICAMENTOS.csv),
[Rename, Ministério da Saúde](https://www.gov.br/saude/pt-br/composicao/sectics/rename),
[Recomendações da Conitec](https://www.gov.br/conitec/pt-br/assuntos/avaliacao-de-tecnologias-em-saude/recomendacoes-da-conitec).

## 3. O ponto difícil: ligar o artigo ao medicamento

Os artigos vêm em inglês (aspirin, metformin) e as bases em português (ácido acetilsalicílico, metformina). Sem
tradução automática, a ligação é o maior risco de erro. Proposta:

1. **Confirmação humana:** a tela mostra "Substâncias que o artigo parece citar", cada uma com o nome em português
   proposto, e o usuário confirma ou digita a substância (com autocompletar vindo das próprias bases).
2. **Casamento conservador:** normalizar (minúsculas, sem acento) e aceitar só correspondência exata ou cognata com
   regras explícitas de sufixo (`-ine/-ina`, `-ide/-ida`, `-ate/-ato`); exceções em tabela revisada. Sem
   adivinhação fora disso.
3. **Rótulo de incerteza:** "possível correspondência, confirme" quando não for exata; nunca resultado silencioso.

## 4. Arquitetura

- Pacote novo `brasil/` com um módulo por base (`anvisa.py`, `rename.py`, `conitec.py`) e `consulta.py`, que devolve
  fatos estruturados: `{fato, valor, fonte, edicao_ou_data_dos_dados, link, aviso}`.
- **Instantâneos compactos versionados** (JSON de dezenas a centenas de KB, gerados por script) em vez de baixar 46 MB
  em tempo de execução. O servidor gratuito dorme e reinicia; instantâneo no repositório dá partida rápida e funciona
  mesmo se a fonte cair. Cada arquivo guarda URL de origem, data de extração e contagem de linhas.
- **Atualização:** `scripts/atualizar_brasil.py` (baixa, valida, gera o instantâneo) mais uma rotina agendada mensal no
  GitHub Actions que abre um pull request com a mudança. Nada entra sem revisão.
- **CONITEC:** ler o XLSX com a biblioteca padrão (zip + XML), sem nova dependência; descobrir o link atual na página.
- **ANVISA:** ler o CSV em Latin-1, reduzir a princípio ativo: situação do registro (ativo, inativo, caduco), classes
  terapêuticas, número de registros ativos, data de vencimento mais recente.
- **RENAME:** extração única do PDF por script de desenvolvimento (a biblioteca de PDF fica só no ambiente de
  desenvolvimento), com **conferência manual de uma amostra** antes de aceitar; edição e componente de financiamento
  guardados com a página do PDF para auditoria. Refazer a cada nova edição.

## 5. Mudanças na interface

- **Cartão "Situação no Brasil (dados oficiais)"** na página do artigo, ao lado de "Registro e dados": por substância
  confirmada, mostra registro na ANVISA (situação e data), presença na Rename 2024 (componente) e decisões da Conitec
  (recomendação, portaria e link do relatório). Sem IA, com a data de cada base.
- **Laboratório:** "Disponib. SUS" e "Vigilância Sanitária" passam a ser **botões extrativos** (como "Doses e
  protocolos (trechos)"). A parte generativa fica opcional, recebendo os fatos oficiais como contexto e marcada como
  interpretação.
- **Texto de cautela fixo:** "Constar na Rename ou ter registro não garante disponibilidade na sua unidade de saúde.
  Confirme com a Secretaria Municipal."

## 6. Fases

| Fase | Entrega | Verificação |
|---|---|---|
| 0. Decisões | Escopo (só medicamentos), política de redação, nome do revisor | Seção 8 respondida |
| 1. CONITEC | Leitor do XLSX, instantâneo, consulta por substância, cartão na página do artigo | Testes com trecho real da planilha; conferência de 20 itens à mão |
| 2. ANVISA | Redução do CSV por princípio ativo, consulta, cartão | Conferir 30 substâncias no site da ANVISA |
| 3. RENAME | Extração do PDF 2024, conferência de amostra, consulta | Amostra de 50 itens conferida contra o PDF |
| 4. Laboratório | Botões extrativos e contexto oficial nos botões generativos | Testes de contrato dos prompts |
| 5. Avaliação | Conjunto de 50 artigos reais, medir acertos e falsos positivos do casamento de nomes | Meta de precisão definida antes (ex.: 95% das correspondências sem falso positivo) |
| 6. Atualização | Script e rotina mensal com pull request | Rotina executada uma vez com sucesso |

Ordem recomendada: **Conitec (a mais simples e informativa), depois ANVISA, depois Rename**, que tem o pior formato.

## 7. Riscos

- **Falso positivo no casamento de nomes** (substância errada com resultado "oficial"): mitigado pela confirmação humana
  e pela avaliação da fase 5.
- **Dado desatualizado:** mostrar sempre edição e data; alerta no CI quando o instantâneo passa de 60 dias.
- **Leitura errada do PDF da Rename:** conferência manual por amostra, guardando a página de origem.
- **Mudança de formato ou de URL:** a rotina de atualização falha com erro claro, nunca com dado parcial.
- **Interpretação indevida:** o texto de cautela e a linguagem ("consta", não "está disponível") são parte da entrega.
- **Licença e uso:** são dados públicos de órgãos federais; confirmar a licença de cada conjunto e citar a fonte e a data.
- **Valor clínico:** sem revisão por farmacêutico ou médico, o rótulo "pendente de revisão por especialista" permanece.

## 8. Decisões que preciso de você

1. Começar só por **medicamentos** (sem procedimentos, produtos para saúde ou vacinas)?
2. **Instantâneos no repositório** (recomendado) ou baixar em tempo de execução?
3. Você ou a sua faculdade consegue indicar **um farmacêutico ou médico** para revisar a amostra das fases 1 a 3?
4. Posso usar a ordem Conitec, ANVISA, Rename?
