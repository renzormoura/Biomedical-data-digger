# Funcionalidade: Nota de confiabilidade

## Objetivo
Dar a cada artigo uma pontuação de **0 a 100** baseada em sinais **verificáveis** no registro e no resumo, mostrando o cálculo inteiro. Não usa IA e não afirma que um estudo é "bom" ou "ruim": diz quanto dos sinais de qualidade e transparência aparece no que a fonte informa.

## O que a pessoa vê
- Na página do artigo: a nota, a faixa (**Alta**, **Moderada**, **Baixa**, **Indeterminada** ou **Retratado**), a cobertura (quanto da nota foi realmente avaliado) e um resumo em uma frase.
- Cada um dos 8 critérios com o status (atendido, parcial, não atendido, não se aplica, desconhecido), os pontos, o detalhe e a **evidência** (a frase do resumo ou o dado do registro que sustenta o resultado), além de "como é calculado".
- Avisos (por exemplo, "nota calculada com 60% dos critérios avaliáveis") e o aviso permanente sobre os limites da nota.
- No relatório de tema e no panorama da busca, a mesma nota é reutilizada.

## Os 8 critérios (100 pontos no total)
| Critério | Peso | O que verifica | Pontuação |
|---|---:|---|---|
| Integridade (retratação) | 20 | Marca de retratação no registro da fonte | Atendido 20; **retratado** zera a nota inteira |
| Desenho do estudo | 25 | Melhor tipo de estudo do registro oficial | Revisão sistemática e meta-análise 100%; ensaio randomizado 90%; diretriz e ensaio controlado 75%; ensaio 70%; observacional, multicêntrico, comparativo 55%; revisão 50%; relato de caso 25%; carta, editorial, comentário 10% |
| Revisão por pares | 10 | Preprint = não revisado; artigo em periódico = considerado revisado | 10 ou 0 |
| Tamanho da amostra informado | 10 | "n = …", "N participantes" ou nº de estudos incluídos (revisões) | 10 ou 0; *não se aplica* a carta, editorial, comentário e diretriz |
| Resultado principal quantificado | 10 | Medida de efeito numérica (HR, OR, RR, diferença de médias) | 10; só percentuais/números = 5 (parcial) |
| Precisão estatística (IC ou p) | 10 | Intervalo de confiança (melhor) ou valor de p | IC = 10; p = 5 (parcial) |
| Método descrito no resumo | 10 | Resumo estruturado com seção de Métodos | Seção de Métodos = 10; resumo longo (≥600 caracteres) sem seção = 5 |
| Registro prévio do ensaio | 5 | Só para ensaios: número de registro (ClinicalTrials.gov, ReBEC, ISRCTN, ChiCTR, ACTRN, EUCTR, CTRI, DRKS, UMIN, PACTR) no resumo | 5 ou 0; *não se aplica* se não é ensaio |

## Como a nota é calculada
1. Cada critério vira um status e uma pontuação (tabela acima).
2. Critérios **"não se aplica"** e **"desconhecido"** saem do denominador: *faltar dado na fonte não pune o artigo*.
3. `nota = 100 × soma dos pontos ÷ soma dos pesos dos critérios avaliados`.
4. **Cobertura** = peso avaliado ÷ peso total. Abaixo de 80%, a nota vem com aviso; abaixo de **50%**, a nota é **indeterminada** (não há dados suficientes).
5. **Faixas:** ≥75 Alta · ≥50 Moderada · <50 Baixa. Artigo retratado: nota 0 e faixa "Retratado", qualquer que seja o resto.
6. Sem resumo: só o registro é avaliado e a nota avisa.

Os sinais do resumo (amostra, medida de efeito, IC, p) vêm de `extraction.py`, que **copia frases** do resumo por padrões; nada é interpretado nem reescrito.

## Limites declarados (também exibidos na interface)
- A nota resume sinais verificáveis; **não avalia a qualidade da execução, o risco de viés nem a validade clínica**, e não substitui a leitura crítica do texto completo.
- Sinais ausentes do **resumo** podem existir no texto completo (amostra, registro do ensaio); a nota diz "pode constar no texto completo".
- A checagem de retratação cobre a fonte consultada (Europe PMC, PubMed ou OpenAlex); retratações recentes podem ainda não constar. O vigia de retratação do [sininho](notificacoes.md) reconfere artigos salvos semanalmente.
- Estudos de áreas fora da saúde recebem menos sinais (tipos de estudo oficiais existem principalmente na Europe PMC e PubMed).

## Arquivos
`reliability.py` (critérios, pesos, faixas), `extraction.py` (sinais do resumo), `discovery.py` (`_analyze`), `browse_api.py` (`reliability_payload`), `static/browse.js` (exibição). Testes: `tests/test_reliability.py`, `tests/test_extraction.py`.
