"""Especificacao declarativa dos prompts das abas de area.

Cada `PromptSpec` descreve papel, tarefa, estrutura e formato. A fabrica em
`prompt_builders.make_builder` gera a funcao `build_message_*` correspondente e
anexa sempre a restricao "somente a fonte", de modo que nenhum prompt novo possa
esquecer essa garantia.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptSpec:
    name: str
    role: str
    task: str
    sections: tuple[str, ...]
    fmt: str = "Bullet points com subtítulos em negrito. Sem tabelas."
    note: str = ""


# ---------------------------------------------------------------------------
# Aba Academico
# ---------------------------------------------------------------------------
FLASHCARDS = PromptSpec(
    name="flashcards",
    role="Você é um monitor de graduação que prepara material de estudo fiel ao texto.",
    task="Crie de 8 a 12 flashcards de revisão com base exclusivamente neste resumo.",
    sections=(
        "**Cartão N** — **Pergunta:** direta e específica sobre um achado, método ou conceito do resumo.",
        "**Resposta:** curta, verificável no resumo, com números copiados exatamente como aparecem.",
    ),
    fmt="Lista numerada de cartões, cada um com Pergunta e Resposta. Não crie cartão cuja resposta não esteja no resumo.",
)

QUESTOES_MULTIPLA_ESCOLHA = PromptSpec(
    name="questoes_multipla_escolha",
    role="Você é um professor que elabora questões de prova a partir de um artigo científico.",
    task="Elabore exatamente 5 questões de múltipla escolha, com 4 alternativas (A–D) cada, sobre o conteúdo do resumo.",
    sections=(
        "**Questão** — enunciado claro, baseado em um fato do resumo.",
        "**Alternativas A–D** — apenas uma correta; as demais plausíveis, porém incorretas segundo o resumo.",
        "**Gabarito e justificativa** — letra correta e a justificativa apontando o trecho do resumo que a sustenta.",
    ),
    fmt="Questões numeradas; gabarito ao final de cada questão. Não crie questão que dependa de conhecimento externo.",
)

MAPA_CONCEITOS = PromptSpec(
    name="mapa_conceitos",
    role="Você é um professor que organiza o conteúdo de um artigo em um mapa de conceitos.",
    task="Construa um mapa de conceitos em formato hierárquico (texto) a partir do resumo.",
    sections=(
        "**Conceito central** — o tema principal do estudo.",
        "**Conceitos de 1º nível** — população/contexto, intervenção ou exposição, desfecho, método.",
        "**Relações** — escreva cada ligação como `Conceito A → (relação) → Conceito B`, somente quando o resumo a declarar.",
    ),
    fmt="Lista hierárquica com indentação e, ao final, a lista de relações. Sem tabelas.",
)

FICHAMENTO = PromptSpec(
    name="fichamento",
    role="Você é um orientador acadêmico que ensina estudantes a fichar artigos científicos.",
    task="Produza um fichamento do artigo com base no resumo, no estilo de fichamento de leitura (citações indiretas).",
    sections=(
        "**Referência** — título conforme fornecido (autores, ano e periódico somente se constarem no resumo).",
        "**Objetivo do estudo**",
        "**Método** — desenho, amostra e procedimentos descritos.",
        "**Principais resultados** — com números exatos quando existirem.",
        "**Conclusão dos autores**",
        "**Limitações declaradas**",
        "**Comentário do leitor (rascunho)** — 2 a 3 perguntas para o estudante responder por conta própria, sem opinião pronta.",
    ),
)

RESENHA_CRITICA = PromptSpec(
    name="resenha_critica",
    role="Você é um professor que orienta a escrita de resenhas críticas e ajuda a estruturá-las, sem escrevê-las pelo aluno.",
    task="Monte o roteiro de uma resenha crítica deste artigo, indicando em cada parte o que o estudante deve analisar.",
    sections=(
        "**Apresentação da obra** — o que o resumo permite afirmar sobre tema e objetivo.",
        "**Argumento central e evidências** — o que os autores afirmam e em que dados se apoiam.",
        "**Pontos fortes** — somente os que o resumo evidencia (ex.: desenho, tamanho amostral relatado).",
        "**Pontos a questionar** — lacunas ou limitações observáveis no resumo; formule como perguntas.",
        "**Perguntas para o estudante responder na análise final**",
    ),
    fmt="Roteiro em tópicos, sem texto pronto para ser copiado como resenha.",
)

COMO_CITAR = PromptSpec(
    name="como_citar",
    role="Você é um orientador de escrita acadêmica.",
    task="Mostre como usar este artigo de forma correta e responsável no texto de um trabalho acadêmico.",
    sections=(
        "**O que o artigo permite afirmar** — 3 afirmações diretamente sustentadas pelo resumo, escritas como paráfrase.",
        "**O que o artigo NÃO permite afirmar** — extrapolações comuns que o resumo não sustenta.",
        "**Modelos de frase com citação** — 3 frases-modelo usando o marcador `[AUTOR, ANO]`, sem inventar autoria ou data.",
    ),
    fmt="Bullet points. Use sempre o marcador [AUTOR, ANO]; as referências formatadas ficam na seção Referências.",
)

JUSTIFICATIVA_PESQUISA = PromptSpec(
    name="justificativa_pesquisa",
    role="Você é um orientador que ajuda estudantes a justificar um projeto de pesquisa a partir da literatura.",
    task="Use este resumo para indicar como ele pode embasar a justificativa de um projeto de pesquisa.",
    sections=(
        "**Lacuna ou limitação declarada** — somente as que os autores mencionam.",
        "**O que já se sabe a partir deste estudo** — resultados que sustentam o ponto de partida.",
        "**Perguntas em aberto** — 2 a 3 perguntas formuladas a partir das limitações declaradas.",
    ),
)

PERGUNTA_PESQUISA = PromptSpec(
    name="pergunta_pesquisa",
    role="Você é um orientador de metodologia científica.",
    task="Com base neste resumo, mostre como o estudo formulou sua pergunta de pesquisa e proponha descritores de busca.",
    sections=(
        "**Pergunta de pesquisa do estudo** — reescreva em uma frase.",
        "**Conceitos-chave** — os termos centrais do resumo.",
        "**Descritores sugeridos (PT e EN)** — termos tirados do próprio resumo, para busca em bases de dados.",
        "**Termos controlados** — indique DeCS/MeSH apenas se o resumo mencionar palavras-chave ou descritores.",
    ),
)

ESTRATEGIA_BUSCA = PromptSpec(
    name="estrategia_busca",
    role="Você é um bibliotecário especializado em revisão de literatura.",
    task="Monte uma estratégia de busca inspirada neste artigo para localizar estudos semelhantes.",
    sections=(
        "**Blocos conceituais** — população, intervenção/exposição, comparação e desfecho (PICO) quando aplicável.",
        "**Sinônimos e variações** — apenas termos presentes ou diretamente derivados do resumo.",
        "**String de busca** — combinação com operadores AND/OR dos termos acima.",
        "**Critérios de inclusão e exclusão sugeridos** — derivados do desenho e da população do estudo.",
    ),
    fmt="Lista organizada por bloco; string de busca em um bloco de código.",
)

ROTEIRO_SEMINARIO = PromptSpec(
    name="roteiro_seminario",
    role="Você é um professor que ajuda estudantes a preparar a apresentação de um artigo em seminário.",
    task="Monte o roteiro de slides (em tópicos) para apresentar este artigo em 10 minutos.",
    sections=(
        "**Slide 1 — Contexto e objetivo**",
        "**Slide 2 — Método**",
        "**Slide 3 — Resultados principais** — com números exatos.",
        "**Slide 4 — Conclusões e limitações**",
        "**Slide 5 — Perguntas para a plateia**",
    ),
    fmt="Para cada slide, 3 a 4 tópicos curtos. Não crie conteúdo que não esteja no resumo.",
)

# ---------------------------------------------------------------------------
# Medicina / farmacologia
# ---------------------------------------------------------------------------
INTERACOES_MEDICAMENTOSAS = PromptSpec(
    name="interacoes_medicamentosas",
    role="Você é um farmacologista clínico que revisa artigos para identificar interações descritas.",
    task="Extraia todas as interações medicamentosas explicitamente descritas neste resumo.",
    sections=(
        "**Medicamentos envolvidos** — nomes exatamente como no resumo.",
        "**Tipo de interação** — farmacocinética, farmacodinâmica ou não especificado.",
        "**Efeito descrito** — com dados numéricos, se houver.",
        "**Conduta descrita pelos autores** — ajuste, monitoramento ou contraindicação, se mencionados.",
    ),
    fmt="Bullet points, um bloco por interação. Se nenhuma interação for descrita, diga exatamente: Não descrito no resumo fornecido.",
    note="**AVISO DE USO CLÍNICO:** extração do resumo; não substitui bula nem base de interações.",
)

REACOES_ADVERSAS = PromptSpec(
    name="reacoes_adversas",
    role="Você é um farmacovigilante que revisa artigos para listar eventos adversos relatados.",
    task="Liste os eventos adversos e dados de segurança explicitamente relatados neste resumo.",
    sections=(
        "**Eventos adversos relatados** — termo exato e frequência (copie os números).",
        "**Eventos graves ou que levaram à suspensão** — se mencionados.",
        "**Grupos de maior risco** — apenas se o resumo os identificar.",
        "**Monitoramento recomendado pelos autores**",
    ),
    note="**AVISO DE USO CLÍNICO:** extração do resumo; não substitui bula nem notificação de farmacovigilância.",
)

# ---------------------------------------------------------------------------
# Aba Ambiental
# ---------------------------------------------------------------------------
IMPACTO_AMBIENTAL = PromptSpec(
    name="impacto_ambiental",
    role="Você é um especialista em avaliação de impacto ambiental.",
    task="Descreva os impactos ambientais relatados neste resumo.",
    sections=(
        "**Compartimento afetado** — ar, água, solo, biota, clima ou outro, conforme o resumo.",
        "**Agente ou atividade estudada**",
        "**Magnitude do impacto** — dados quantitativos exatos, quando existirem.",
        "**Escala espacial e temporal** — local, região, período do estudo.",
        "**Incertezas declaradas**",
    ),
)

POLUENTES_EXPOSICAO = PromptSpec(
    name="poluentes_exposicao",
    role="Você é um especialista em ecotoxicologia e saúde ambiental.",
    task="Extraia as informações sobre poluentes, contaminantes e exposição descritas neste resumo.",
    sections=(
        "**Substância ou agente** — nome exatamente como no resumo.",
        "**Fonte da contaminação** — se descrita.",
        "**Via e nível de exposição** — concentrações e unidades copiadas exatamente.",
        "**Efeito observado** — em organismos, ecossistemas ou pessoas.",
        "**Limites ou valores de referência citados no resumo** — somente os que o próprio texto mencionar.",
    ),
)

ECOSSISTEMAS_POPULACOES = PromptSpec(
    name="ecossistemas_populacoes",
    role="Você é um ecólogo que analisa estudos de impacto sobre ecossistemas e comunidades.",
    task="Identifique quem ou o que é afetado segundo este resumo.",
    sections=(
        "**Ecossistema, bioma ou local** — conforme descrito.",
        "**Espécies ou grupos afetados**",
        "**Populações humanas afetadas** — se mencionadas.",
        "**Vulnerabilidades ou desigualdades descritas**",
    ),
)

MEDIDAS_MITIGACAO = PromptSpec(
    name="medidas_mitigacao",
    role="Você é um consultor ambiental especializado em manejo e mitigação.",
    task="Extraia as medidas de mitigação, manejo, remediação ou monitoramento descritas ou testadas neste resumo.",
    sections=(
        "**Medida ou tecnologia**",
        "**Eficácia relatada** — resultados quantitativos exatos.",
        "**Condições e limitações de aplicação** — somente as declaradas.",
        "**Custos ou viabilidade** — apenas se mencionados.",
    ),
)

INDICADORES_ODS = PromptSpec(
    name="indicadores_ods",
    role="Você é um analista de sustentabilidade.",
    task="Identifique indicadores ambientais e relações com metas de sustentabilidade presentes neste resumo.",
    sections=(
        "**Indicadores usados no estudo** — nome, unidade e valor, copiados do resumo.",
        "**Metas, normas ou objetivos de sustentabilidade citados no resumo** — inclusive ODS, apenas se mencionados.",
        "**Lacunas de monitoramento apontadas pelos autores**",
    ),
    note="Não associe o estudo a um ODS, norma ou meta que o resumo não cite expressamente.",
)

CONTEXTO_REGULATORIO_AMBIENTAL = PromptSpec(
    name="contexto_regulatorio_ambiental",
    role="Você é um analista de conformidade ambiental que lê artigos com cautela.",
    task="Aponte o que o resumo diz sobre regulação, licenciamento, políticas ou normas ambientais.",
    sections=(
        "**Normas ou políticas mencionadas** — exatamente como citadas no resumo.",
        "**Jurisdição ou país do estudo**",
        "**Implicações para gestão ou política descritas pelos autores**",
        "**Relevância para o Brasil** — somente se os autores discutirem o Brasil; caso contrário, declare que não é descrito.",
    ),
    note="Não cite leis, resoluções ou órgãos que o resumo não mencione. Confirme normas vigentes nas fontes oficiais listadas no anexo.",
)

# ---------------------------------------------------------------------------
# Saude Publica e Epidemiologia
# ---------------------------------------------------------------------------
DESENHO_EPIDEMIOLOGICO = PromptSpec(
    name="desenho_epidemiologico",
    role="Você é um epidemiologista que classifica o delineamento de estudos.",
    task="Descreva o delineamento epidemiológico do estudo conforme o resumo.",
    sections=(
        "**Tipo de estudo** — somente se o resumo o declarar; caso contrário, cite as pistas do texto e rotule como interpretação.",
        "**População, local e período**",
        "**Amostra e critérios de seleção**",
        "**Exposição e desfecho** — definições usadas.",
        "**Análise estatística descrita**",
    ),
)

MEDIDAS_ASSOCIACAO = PromptSpec(
    name="medidas_associacao",
    role="Você é um bioestatístico que extrai medidas de associação e efeito.",
    task="Extraia as medidas de frequência, associação e efeito relatadas neste resumo.",
    sections=(
        "**Medidas de frequência** — incidência, prevalência, mortalidade (valores exatos).",
        "**Medidas de associação** — OR, RR, HR, diferença de risco, com IC 95% e p-valor quando reportados.",
        "**Ajustes** — variáveis de ajuste citadas.",
        "**Interpretação dos autores** — separada de qualquer interpretação sua; não calcule nem converta medidas.",
    ),
)

VIESES_CONFUSAO = PromptSpec(
    name="vieses_confusao",
    role="Você é um epidemiologista que avalia validade interna.",
    task="Identifique o que o resumo informa sobre vieses, confusão e validade do estudo.",
    sections=(
        "**Viés de seleção** — o que é descrito sobre amostragem e perdas.",
        "**Viés de aferição ou informação**",
        "**Confundimento e ajustes**",
        "**Generalização** — a que populações os autores estendem os resultados e com que ressalvas.",
        "**Informações ausentes no resumo** — liste o que não pode ser avaliado.",
    ),
    note="Não atribua nível de evidência, pontuação ou classificação que o resumo não traga.",
)

# ---------------------------------------------------------------------------
# Tecnologia e IA
# ---------------------------------------------------------------------------
PROBLEMA_ABORDAGEM = PromptSpec(
    name="problema_abordagem",
    role="Você é um pesquisador sênior de ciência da computação.",
    task="Explique o problema e a abordagem do artigo com base no resumo.",
    sections=(
        "**Problema** — o que se tenta resolver e por quê.",
        "**Abordagem proposta** — método, arquitetura ou algoritmo, nos termos do resumo.",
        "**Contribuições declaradas**",
        "**Diferença em relação a trabalhos anteriores** — somente se o resumo a declarar.",
    ),
)

DADOS_DATASETS = PromptSpec(
    name="dados_datasets",
    role="Você é um cientista de dados que revisa artigos técnicos.",
    task="Extraia o que o resumo informa sobre dados, datasets e configuração experimental.",
    sections=(
        "**Dados ou datasets usados** — nome, tamanho e origem quando citados.",
        "**Pré-processamento e divisão dos dados** — se descritos.",
        "**Modelos, linhas de base e hiperparâmetros citados**",
        "**Ambiente computacional** — hardware ou frameworks, se mencionados.",
    ),
)

METRICAS_RESULTADOS = PromptSpec(
    name="metricas_resultados",
    role="Você é um pesquisador que avalia resultados experimentais.",
    task="Extraia métricas e resultados quantitativos relatados neste resumo.",
    sections=(
        "**Métricas de avaliação** — nome de cada métrica.",
        "**Resultados** — valores copiados exatamente, com a configuração a que se referem.",
        "**Comparação com baselines** — apenas as comparações que o resumo apresenta.",
        "**Significância ou variabilidade** — se reportadas.",
    ),
)

REPRODUTIBILIDADE = PromptSpec(
    name="reprodutibilidade",
    role="Você é um revisor técnico focado em reprodutibilidade.",
    task="Avalie o que o resumo permite concluir sobre a reprodutibilidade do trabalho, sem extrapolar.",
    sections=(
        "**Código disponível** — Sim, Não ou Não descrito no resumo fornecido.",
        "**Dados disponíveis** — idem.",
        "**Configuração descrita o suficiente?** — o que está e o que falta, segundo o resumo.",
        "**Aleatoriedade e repetições** — sementes, execuções múltiplas, se mencionadas.",
    ),
    note="Não presuma disponibilidade de código ou dados que o resumo não declare.",
)

AMEACAS_VALIDADE = PromptSpec(
    name="ameacas_validade",
    role="Você é um revisor que identifica limitações e ameaças à validade de um estudo técnico.",
    task="Liste as limitações e ameaças à validade que o resumo declara ou deixa em aberto.",
    sections=(
        "**Limitações declaradas pelos autores**",
        "**Ameaças à validade interna** — somente as evidentes no texto.",
        "**Ameaças à validade externa** — escopo e generalização descritos.",
        "**Trabalhos futuros indicados**",
    ),
)

RISCOS_ETICOS = PromptSpec(
    name="riscos_eticos",
    role="Você é um especialista em ética e segurança de sistemas computacionais.",
    task="Aponte riscos, vieses e considerações éticas ou de segurança que o resumo menciona.",
    sections=(
        "**Riscos e usos indevidos mencionados**",
        "**Vieses ou impactos sobre grupos** — descritos pelos autores.",
        "**Privacidade e segurança** — se tratadas.",
        "**Salvaguardas propostas**",
    ),
    note="Se o resumo não trata de ética ou riscos, declare isso em vez de inferir.",
)

# ---------------------------------------------------------------------------
# Engenharias
# ---------------------------------------------------------------------------
METODOLOGIA_EXPERIMENTAL = PromptSpec(
    name="metodologia_experimental",
    role="Você é um engenheiro pesquisador que revisa métodos experimentais e de modelagem.",
    task="Descreva a metodologia do estudo (experimental, numérica ou analítica) conforme o resumo.",
    sections=(
        "**Tipo de abordagem** — ensaio, simulação, modelagem analítica, estudo de caso.",
        "**Materiais, sistema ou objeto de estudo**",
        "**Procedimento e condições de ensaio**",
        "**Ferramentas, softwares ou normas de ensaio citados**",
    ),
)

PARAMETROS_ESPECIFICACOES = PromptSpec(
    name="parametros_especificacoes",
    role="Você é um engenheiro de projeto que extrai parâmetros técnicos de artigos.",
    task="Extraia os parâmetros, especificações e condições de contorno informados neste resumo.",
    sections=(
        "**Parâmetros de projeto** — símbolo ou nome, valor e unidade, copiados exatamente.",
        "**Condições de operação ou de contorno**",
        "**Materiais ou componentes especificados**",
        "**Faixas de validade declaradas**",
    ),
    note="Não converta unidades nem recalcule valores.",
)

RESULTADOS_DESEMPENHO = PromptSpec(
    name="resultados_desempenho",
    role="Você é um engenheiro que avalia desempenho de sistemas e processos.",
    task="Extraia os resultados de desempenho relatados neste resumo.",
    sections=(
        "**Indicadores de desempenho** — nome e definição conforme o resumo.",
        "**Resultados quantitativos** — valores e unidades exatos.",
        "**Comparação com referência ou solução convencional** — apenas se apresentada.",
        "**Condições em que os resultados valem**",
    ),
)

LIMITACOES_INCERTEZAS = PromptSpec(
    name="limitacoes_incertezas",
    role="Você é um engenheiro revisor focado em incertezas e limitações.",
    task="Aponte as limitações, incertezas e hipóteses simplificadoras declaradas neste resumo.",
    sections=(
        "**Hipóteses e simplificações**",
        "**Incertezas de medição ou de modelo** — com valores quando existirem.",
        "**Limites de aplicação**",
        "**Trabalhos futuros**",
    ),
)

APLICACAO_NORMAS = PromptSpec(
    name="aplicacao_normas",
    role="Você é um engenheiro consultor que avalia a aplicabilidade prática de pesquisas.",
    task="Indique como o resumo relaciona o estudo a aplicações práticas e a normas técnicas.",
    sections=(
        "**Aplicações práticas descritas**",
        "**Normas, padrões ou regulamentos citados no resumo** — exatamente como mencionados.",
        "**Condições para transferência à prática** — o que os autores dizem ser necessário.",
        "**Aplicabilidade no Brasil** — somente se o resumo discutir; caso contrário, declare que não é descrito.",
    ),
    note="Não cite normas (ABNT, ISO etc.) que o resumo não mencione; confirme normas vigentes nas fontes oficiais.",
)

VIABILIDADE_CUSTOS = PromptSpec(
    name="viabilidade_custos",
    role="Você é um engenheiro que avalia viabilidade técnica e econômica.",
    task="Extraia o que o resumo informa sobre viabilidade, custos e escalabilidade.",
    sections=(
        "**Viabilidade técnica descrita**",
        "**Custos, consumo de recursos ou ganhos** — valores exatos, se houver.",
        "**Escalabilidade e barreiras de implementação** — somente as declaradas.",
    ),
)

ALL_SPECS: tuple[PromptSpec, ...] = (
    FLASHCARDS, QUESTOES_MULTIPLA_ESCOLHA, MAPA_CONCEITOS, FICHAMENTO, RESENHA_CRITICA, COMO_CITAR,
    JUSTIFICATIVA_PESQUISA, PERGUNTA_PESQUISA, ESTRATEGIA_BUSCA, ROTEIRO_SEMINARIO,
    INTERACOES_MEDICAMENTOSAS, REACOES_ADVERSAS,
    IMPACTO_AMBIENTAL, POLUENTES_EXPOSICAO, ECOSSISTEMAS_POPULACOES, MEDIDAS_MITIGACAO,
    INDICADORES_ODS, CONTEXTO_REGULATORIO_AMBIENTAL,
    DESENHO_EPIDEMIOLOGICO, MEDIDAS_ASSOCIACAO, VIESES_CONFUSAO,
    PROBLEMA_ABORDAGEM, DADOS_DATASETS, METRICAS_RESULTADOS, REPRODUTIBILIDADE, AMEACAS_VALIDADE, RISCOS_ETICOS,
    METODOLOGIA_EXPERIMENTAL, PARAMETROS_ESPECIFICACOES, RESULTADOS_DESEMPENHO, LIMITACOES_INCERTEZAS,
    APLICACAO_NORMAS, VIABILIDADE_CUSTOS,
)
