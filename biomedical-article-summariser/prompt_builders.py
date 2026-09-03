"""Prompts e montadores de mensagens enviados aos backends de LLM."""

from typing import Dict, List

SYS_PROMPT = """
You are an expert in biomedical text mining and information extraction. You excel at breaking down complex articles into digestible contents for your audience, which comprises students, early researchers, and professionals in the field.

Summarize the key findings in the following article: [ARTICLE].

**Language & Translation Guidelines:**

* Generate the entire summary in **Brazilian Portuguese**.
* Preserve technical terms, specialized domain jargon, or acronyms in their original English whenever a direct translation would compromise accuracy, obscure meaning, or sound unnatural to professionals in the field (e.g., *machine learning*, *gene knockout*, *single-cell RNA sequencing*, *western blot*, *p-value*).

**Strict Constraint:** All information presented in the summary must be derived strictly and exclusively from the provided article. Do not include external knowledge, assumptions, or any information not directly supported by the text.

Your summary should provide crucial points covered in the paper that help your diverse audience quickly understand the most vital information.

Crucial points to consider:

* Main objectives of the study
* Key findings and results
* Methodologies used
* Implications of the findings (if any)
* Any limitations or future directions mentioned

Format: Provide your summary in bullet points highlighting key areas, followed by a concise paragraph that encapsulates the results of the paper.

The tone should be professional and clear.

"""

def build_message_resumo_academico(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    user_prompt = f"""Você é um pesquisador sênior com experiência em revisão de periódicos científicos nas áreas da saúde e ciências da vida. Analise o artigo a seguir e forneça um resumo técnico de alto nível para acadêmicos, pesquisadores e estudantes de pós-graduação.

Título: {article_title}
Abstract:
{abstract_text}

Estruture a resposta com os tópicos:
1. Desenho do Estudo e Amostra (N)
2. Racional Científico e Hipótese
3. Metodologia e Principais Achados (com métricas quando disponíveis: p-value, IC 95%, HR, N)
4. Análise Crítica: Limitações e Lacunas de Conhecimento
5. Conclusão Acadêmica (parágrafo síntese)

**FORMATO:** Bullet points e linguagem científica rigorosa. Sem tabelas.
**Restrição absoluta:** Somente informações do artigo."""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_resumo_clinico(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """
    Constructs the payload for a Clinical Summary (Practical application for physicians).
    """
    user_prompt = f"""Você é um médico especialista focado em medicina baseada em evidências. Analise o artigo a seguir e extraia as informações essenciais para a prática médica e tomada de decisão à beira do leito (bedside).

Título: {article_title}
Abstract:
{abstract_text}

Instruções de Estrutura:
- Mantenha o tom profissional, direto e pragmático.
- Foque na utilidade do achado para diagnóstico, prognóstico, intervenção ou conduta terapêutica.
- Estruture a resposta com os tópicos:
  1. Pergunta Clínica / População-Alvo
  2. Intervenção ou Fator Estudado vs. Controle
  3. Desfechos Clínicos Principais (Primary Endpoints) e Segurança/Efeitos Adversos
  4. Implicações Práticas para a Conduta Médica
  5. Recado para a Prática (em um parágrafo conciso ao final)"""

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ]

def build_message_resumo(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    user_prompt = f"""Analise o artigo científico a seguir e produza um resumo equilibrado. O artigo pode ser de qualquer área científica — adapte a linguagem ao contexto do texto, priorizando clareza para profissionais da área da saúde e ciências correlatas.

Título: {article_title}
Abstract:
{abstract_text}

Estruture a resposta com os tópicos:
1. **O que foi estudado** — contexto e objetivo
2. **Como foi feito** — metodologia em linguagem direta
3. **O que foi encontrado** — principais resultados com dados relevantes
4. **O que isso significa** — implicações práticas ou científicas
5. **Síntese final** — parágrafo curto de fechamento

**FORMATO:** Bullet points e parágrafos curtos. Sem tabelas.
**Restrição absoluta:** Somente informações do artigo."""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_sumario(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    user_prompt = f"""Analise o artigo científico a seguir e produza um sumário direto e objetivo, adequado para profissionais e pesquisadores da área da saúde e ciências da vida.

Título: {article_title}
Abstract:
{abstract_text}

Comece com uma frase de até 2 linhas que sintetize o tema principal. Em seguida, liste de 4 a 6 bullet points com os pontos mais importantes (objetivo, métodos, resultados e conclusão). Finalize com um parágrafo curto de fechamento.

**FORMATO:** Bullet points concisos. Sem tabelas.
**Restrição absoluta:** Somente informações presentes no artigo."""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_medicamentos(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """
    Constructs the payload for a Pharmacology / Protocols summary (clinical use in emergency settings).
    """
    user_prompt = f"""Você é um farmacologista clínico sênior com especialização em medicina de urgência e emergência. Analise o artigo a seguir e extraia todas as informações farmacológicas e de protocolos clínicos mencionados, com rigor técnico e precisão para uso em ambiente de pronto-socorro.

Título: {article_title}
Abstract:
{abstract_text}

**AVISO DE USO CLÍNICO:** As informações abaixo são extraídas exclusivamente do artigo fornecido. Não substitui bulas, diretrizes institucionais ou julgamento clínico individualizado.

**FORMATO OBRIGATÓRIO:** Use exclusivamente títulos em negrito e listas com marcadores (bullet points). Não use tabelas, colunas ou qualquer formatação tabular. O texto deve ser legível em telas de celular.

Para cada medicamento ou intervenção terapêutica identificado no artigo, apresente:

1. **Nome do Medicamento / Intervenção**
   - Nome genérico e comercial (se mencionado no artigo)
   - Classe farmacológica e mecanismo de ação (se descrito)

2. **Posologia por Perfil de Paciente**
   Para cada população estudada no artigo (ex: saudáveis, insuficiência renal, diálise, idosos, pediátricos), detalhe:
   - Dose recomendada (mg, mg/kg, UI, etc.)
   - Via de administração
   - Diluição recomendada (diluente, volume final, concentração resultante — se descrito)
   - Velocidade de administração (ex: EV em bolus, infusão lenta em X minutos, gotejamento em X mL/h — se descrito)
   - Intervalo entre doses e duração do tratamento
   - Ajuste de dose necessário em populações especiais

3. **Compatibilidade e Estabilidade**
   - Diluentes compatíveis e incompatíveis (se descritos)
   - Compatibilidade com outros medicamentos na mesma via ou solução (se descrito)
   - Tempo de estabilidade após diluição e condições de armazenamento (temperatura, proteção da luz — se descrito)

4. **Farmacocinética Clínica**
   - Meia-vida de eliminação (t½) por perfil de paciente
   - Pico de ação (Tmax) e início do efeito
   - Ligação proteica e volume de distribuição (se mencionado)
   - Metabolismo e via de eliminação
   - Impacto de disfunção renal ou hepática sobre a farmacocinética

5. **Eficácia e Desfechos Clínicos**
   - Desfechos primários e secundários avaliados
   - Resultados quantitativos (ex: redução de X%, NNT, p-value, IC 95%)

6. **Segurança e Efeitos Adversos**
   - Efeitos adversos relatados com frequência (%)
   - Efeitos graves ou que exijam monitoramento especial
   - Contraindicações mencionadas
   - Interações medicamentosas relevantes (se descritas)

7. **Monitoramento Terapêutico**
   - Parâmetros clínicos e laboratoriais a monitorar durante o uso (ex: função renal, PA, FC, nível sérico)
   - Momento e frequência do monitoramento recomendados (se descritos)
   - Valores de alerta ou limiares de toxicidade mencionados

8. **Conduta em Toxicidade ou Superdose**
   - Sinais e sintomas de toxicidade descritos no artigo
   - Antídoto ou tratamento de suporte mencionado
   - Dose tóxica ou letal citada (se houver)

9. **Considerações Práticas para o Pronto-Socorro**
   - Pontos de atenção para uso em urgência/emergência
   - Populações que requerem maior cautela
   - O que o artigo sugere que deve ser monitorado durante o uso
   - Comparação direta entre populações quando o artigo apresentar dados para mais de um perfil de paciente (ex: saudável vs. diálise)

**Restrição absoluta:** Apresente somente informações explicitamente descritas no artigo. Se algum campo não for abordado, indique "Não descrito no artigo" — nunca preencha com conhecimento externo ou suposições."""

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ]

def build_message_critica_metodologica(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """
    Constructs the payload for a Methodological Critique.
    """
    user_prompt = f"""Você é um epidemiologista clínico sênior e revisor de periódicos de alto impacto. Analise criticamente o artigo a seguir sob a perspectiva metodológica, avaliando a qualidade da evidência produzida.

Título: {article_title}
Abstract:
{abstract_text}

**FORMATO OBRIGATÓRIO:** Use exclusivamente títulos em negrito e listas com marcadores (bullet points). Não use tabelas. O texto deve ser legível em telas de celular.

Estruture a análise com os seguintes tópicos:

1. **Desenho do Estudo**
   - Tipo de estudo (RCT, coorte, caso-controle, transversal, revisão sistemática, etc.)
   - Nível de evidência segundo a pirâmide de evidências
   - Adequação do desenho à pergunta de pesquisa

2. **Amostra e População**
   - Tamanho amostral (N) e se há cálculo de poder estatístico mencionado
   - Critérios de inclusão e exclusão
   - Representatividade e generalizabilidade da amostra

3. **Vieses Potenciais**
   - Viés de seleção (se identificável)
   - Viés de informação ou aferição
   - Viés de confundimento e estratégias de controle utilizadas
   - Viés de publicação (se aplicável)

4. **Validade Interna**
   - Randomização e cegamento (se aplicável)
   - Controle de variáveis de confundimento
   - Perdas de seguimento e análise por intenção de tratar (se aplicável)

5. **Validade Externa**
   - Aplicabilidade dos resultados a outras populações
   - Limitações geográficas, étnicas ou contextuais

6. **Qualidade Estatística**
   - Adequação dos testes estatísticos ao tipo de dado
   - Presença de intervalos de confiança e tamanho de efeito
   - Significância estatística vs. relevância clínica

7. **Conclusão Crítica**
   - Pontos fortes do estudo
   - Principais limitações que impactam a confiança nos resultados
   - Grau de confiança recomendado na evidência apresentada (em um parágrafo síntese)

**Restrição absoluta:** Baseie a análise exclusivamente no que está descrito no artigo. Se algum campo não puder ser avaliado pelo abstract, indique "Não avaliável pelo abstract disponível"."""

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ]

def build_message_estatisticas(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """
    Constructs the payload for a Statistical Data extraction and explanation.
    """
    user_prompt = f"""Você é um bioestatístico clínico com experiência em ensinar medicina baseada em evidências para médicos e residentes. Extraia e explique todos os dados estatísticos presentes no artigo a seguir, traduzindo seu significado clínico de forma acessível.

Título: {article_title}
Abstract:
{abstract_text}

**FORMATO OBRIGATÓRIO:** Use exclusivamente títulos em negrito e listas com marcadores (bullet points). Não use tabelas. O texto deve ser legível em telas de celular.

Estruture a resposta com os seguintes tópicos:

1. **Métricas de Efeito Encontradas**
   Para cada medida estatística identificada no artigo, apresente:
   - O valor reportado (ex: RR = 0,72; OR = 1,45; HR = 0,88)
   - O intervalo de confiança (IC 95%) quando disponível
   - O valor de p quando disponível
   - O que essa medida representa em linguagem clínica simples

2. **Significância Estatística vs. Relevância Clínica**
   - O resultado é estatisticamente significativo? (p < 0,05)
   - O tamanho do efeito é clinicamente relevante?
   - Há diferença entre significância estatística e importância prática?

3. **NNT / NNH (se aplicável)**
   - Número necessário para tratar (NNT) — se não reportado, calcule a partir dos dados disponíveis
   - Número necessário para causar dano (NNH) — se disponível
   - Interpretação clínica direta (ex: "a cada 10 pacientes tratados, 1 se beneficia")

4. **Medidas de Acurácia Diagnóstica (se aplicável)**
   - Sensibilidade e Especificidade
   - Valor Preditivo Positivo (VPP) e Negativo (VPN)
   - Área sob a curva ROC (AUC) se disponível
   - Interpretação prática de cada medida

5. **Poder Estatístico e Tamanho Amostral**
   - N total e por grupo
   - Cálculo de poder mencionado (beta, poder do estudo)
   - Risco de erro tipo II (falso negativo) se amostra for pequena

6. **Resumo Estatístico para a Prática**
   - Síntese em linguagem direta do que os números significam para a decisão clínica (em um parágrafo final)

**Restrição absoluta:** Apresente somente dados explicitamente descritos no artigo. Se um campo não estiver disponível, indique "Não reportado no artigo". Não calcule nem estime valores não presentes no texto, exceto NNT quando houver dados suficientes."""

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ]

def build_message_pico(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """
    Constructs the payload for a PICO framework analysis.
    """
    user_prompt = f"""Você é um especialista em medicina baseada em evidências (MBE) com ampla experiência em ensinar o framework PICO para médicos e estudantes. Estruture o artigo a seguir no formato PICO de forma precisa e completa.

Título: {article_title}
Abstract:
{abstract_text}

**FORMATO OBRIGATÓRIO:** Use exclusivamente títulos em negrito e listas com marcadores (bullet points). Não use tabelas. O texto deve ser legível em telas de celular.

Estruture a resposta com os seguintes tópicos:

1. **P — Paciente / População / Problema**
   - Quem são os pacientes estudados?
   - Características demográficas principais (idade, sexo, comorbidades)
   - Condição clínica ou problema de saúde investigado
   - Critérios de inclusão e exclusão relevantes (se descritos)

2. **I — Intervenção**
   - O que foi feito, aplicado ou exposto ao grupo de intervenção?
   - Dose, duração, frequência ou protocolo (se descritos)
   - Contexto de aplicação (ambulatorial, hospitalar, PS, etc.)

3. **C — Comparação / Controle**
   - Qual foi o grupo comparador? (placebo, tratamento padrão, outra dose, sem intervenção)
   - Características relevantes do grupo controle

4. **O — Outcome / Desfecho**
   - Desfecho primário: o que foi medido como resultado principal?
   - Desfechos secundários (se descritos)
   - Como e quando os desfechos foram medidos?
   - Resultado encontrado para cada desfecho (com valores se disponíveis)

5. **T — Tipo de Estudo (extensão PICOT)**
   - Desenho do estudo
   - Duração do seguimento
   - Nível de evidência

6. **Pergunta PICO Formatada**
   - Escreva a pergunta clínica completa no formato: "Em [P], a [I] comparada a [C] resulta em [O]?"

7. **Aplicabilidade Clínica**
   - O perfil do paciente estudado corresponde aos pacientes que você atende?
   - A intervenção é disponível e aplicável no seu contexto?
   - Os desfechos medidos são relevantes para a prática clínica? (em um parágrafo final)

**Restrição absoluta:** Preencha cada elemento PICO exclusivamente com informações do artigo. Se algum componente não estiver explícito, indique "Não descrito no artigo"."""

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ]

def build_message_alertas(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """
    Constructs the payload for a Safety Alerts and Contraindications summary.
    """
    user_prompt = f"""Você é um médico de urgência e emergência com foco em segurança do paciente. Analise o artigo a seguir e extraia exclusivamente as informações de segurança, alertas e contraindicações, organizadas para consulta rápida à beira do leito.

Título: {article_title}
Abstract:
{abstract_text}

**AVISO:** As informações abaixo são extraídas exclusivamente do artigo fornecido. Não substitui bulas, diretrizes institucionais ou julgamento clínico individualizado.

**FORMATO OBRIGATÓRIO:** Use exclusivamente títulos em negrito e listas com marcadores (bullet points). Não use tabelas. Seja direto e objetivo — este material será consultado em situações de urgência.

Estruture a resposta com os seguintes tópicos:

1. **Contraindicações Absolutas**
   - Situações em que a intervenção/medicamento NÃO deve ser usado em hipótese alguma (conforme descrito no artigo)

2. **Contraindicações Relativas e Populações de Risco**
   - Grupos que requerem cautela especial ou ajuste de conduta
   - Ex: gestantes, idosos, insuficiência renal/hepática, crianças, imunossuprimidos

3. **Efeitos Adversos Graves**
   - Reações adversas com risco de vida ou que exijam interrupção imediata
   - Frequência reportada (%) quando disponível

4. **Efeitos Adversos Relevantes**
   - Efeitos adversos frequentes ou que impactem adesão/conduta
   - Frequência reportada (%) quando disponível

5. **Interações Medicamentosas**
   - Interações descritas no artigo com potencial de dano clínico
   - Mecanismo da interação (se descrito)

6. **Sinais de Alerta para Monitoramento**
   - Parâmetros clínicos e laboratoriais que indicam toxicidade ou falha terapêutica
   - Valores limítrofes de alerta mencionados

7. **Conduta em Caso de Reação Grave**
   - O que o artigo descreve como manejo de toxicidade ou reação adversa grave
   - Antídoto ou tratamento de suporte mencionado

8. **Checklist de Segurança Pré-Uso**
   - Lista rápida de verificações recomendadas antes de iniciar a intervenção (baseada nos dados do artigo)

**Restrição absoluta:** Inclua apenas informações de segurança explicitamente descritas no artigo. Se um campo não for abordado, indique "Não descrito no artigo". Nunca infira riscos não documentados."""

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ]

def build_message_checklist(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """
    Constructs the payload for a Pre-Conduct Checklist for bedside use.
    """
    user_prompt = f"""Você é um médico intensivista com vasta experiência em protocolos operacionais de pronto-socorro. Com base no artigo a seguir, elabore um checklist prático pré-conduta para ser usado diretamente à beira do leito antes de aplicar a intervenção descrita.

Título: {article_title}
Abstract:
{abstract_text}

**AVISO:** Este checklist é baseado exclusivamente nos dados do artigo fornecido. Não substitui protocolos institucionais ou julgamento clínico individualizado.

**FORMATO OBRIGATÓRIO:** Use exclusivamente títulos em negrito e listas com marcadores (bullet points) em formato de checklist (itens curtos e diretos com "[ ]" antes de cada item). Não use tabelas. Otimizado para leitura rápida em celular.

Estruture o checklist com os seguintes tópicos:

1. **Critérios de Elegibilidade do Paciente**
   - [ ] Perfil do paciente que se beneficia da intervenção (conforme o artigo)
   - [ ] Critérios de inclusão que devem estar presentes

2. **Critérios de Exclusão — Não Aplicar Se:**
   - [ ] Condições que contraindicam a intervenção (conforme o artigo)

3. **Exames e Avaliações Pré-Intervenção**
   - [ ] Exames laboratoriais necessários antes de iniciar
   - [ ] Avaliações clínicas recomendadas (PA, FC, função renal, etc.)

4. **Preparo da Intervenção / Medicamento**
   - [ ] Dose correta para o perfil do paciente
   - [ ] Diluição e preparo (se aplicável)
   - [ ] Via e velocidade de administração

5. **Monitoramento Durante a Intervenção**
   - [ ] Parâmetros a monitorar e frequência
   - [ ] Sinais de alerta que indicam interrupção imediata

6. **Documentação e Seguimento**
   - [ ] O que deve ser registrado em prontuário
   - [ ] Quando reavaliar o paciente após a intervenção
   - [ ] Exames de controle pós-intervenção (se descritos)

7. **Plano de Contingência**
   - [ ] O que fazer se ocorrer reação adversa grave
   - [ ] Antídoto ou suporte disponível (se descrito no artigo)

**Restrição absoluta:** Preencha os itens do checklist exclusivamente com informações do artigo. Se um campo não puder ser preenchido, indique "[ ] Verificar protocolo institucional — não descrito no artigo"."""

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ]

def build_message_aplicabilidade_br(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """
    Constructs the payload for a Brazilian applicability analysis.
    """
    user_prompt = f"""Você é um médico brasileiro com experiência em saúde pública, medicina baseada em evidências e no sistema de saúde nacional (SUS e saúde suplementar). Analise o artigo a seguir sob a perspectiva da aplicabilidade ao contexto clínico brasileiro.

Título: {article_title}
Abstract:
{abstract_text}

**FORMATO OBRIGATÓRIO:** Use exclusivamente títulos em negrito e listas com marcadores (bullet points). Não use tabelas. O texto deve ser legível em telas de celular.

Estruture a análise com os seguintes tópicos:

1. **Origem do Estudo e Contexto Original**
   - País(es) onde o estudo foi conduzido (se mencionado)
   - Perfil da população estudada e sistema de saúde envolvido
   - Contexto clínico original (ambulatorial, hospitalar, PS, atenção primária)

2. **Comparação Populacional**
   - Semelhanças e diferenças entre a população do estudo e a população brasileira
   - Diferenças étnicas, epidemiológicas ou de comorbidades relevantes (se inferíveis do artigo)
   - Faixa etária e perfil socioeconômico estudado vs. realidade brasileira

3. **Disponibilidade dos Medicamentos / Intervenções no Brasil**
   - Os medicamentos ou tecnologias estudados estão disponíveis no Brasil?
   - Estão na RENAME (Relação Nacional de Medicamentos Essenciais) ou disponíveis pelo SUS?
   - Há alternativas nacionais equivalentes?

4. **Aplicabilidade por Nível de Atenção**
   - A intervenção é viável na Atenção Primária (UBS)?
   - É aplicável em Pronto-Socorro ou UPA?
   - Requer estrutura hospitalar especializada (UTI, centro cirúrgico)?

5. **Barreiras e Facilitadores para Implementação no Brasil**
   - Principais barreiras: custo, infraestrutura, treinamento, regulação (ANVISA)
   - Facilitadores: políticas públicas, protocolos do Ministério da Saúde, disponibilidade

6. **Força da Evidência para o Contexto Brasileiro**
   - Os resultados são diretamente extrapoláveis para o Brasil?
   - Quais adaptações seriam necessárias?
   - Qual o grau de confiança recomendado para aplicar esses resultados na prática brasileira?

7. **Recomendação Prática para o Médico Brasileiro**
   - Síntese objetiva sobre se e como aplicar os achados do artigo no contexto clínico brasileiro (em um parágrafo final direto)

**Restrição absoluta:** Base a análise nos dados do artigo. Para a seção de disponibilidade no Brasil e contexto do SUS, é permitido usar conhecimento geral sobre o sistema de saúde brasileiro, mas indique claramente quando uma informação vai além do que está no artigo."""

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ]

def build_dynamic_sys_prompt(
    publico: str,
    tom: str,
    idioma: str,
    detalhe: str,
    foco: str,
) -> str:
    """
    Builds a dynamic system prompt by appending user-selected filters
    to the base SYS_PROMPT. Empty/default values are ignored.
    """
    prompt = SYS_PROMPT.strip()
    extras = []

    PUBLICO_MAP = {
        "Médico / Especialista":  "Dirija a resposta a um médico ou especialista clínico com pleno domínio da linguagem técnica médica.",
        "Residente / Interno":    "Dirija a resposta a um médico residente ou interno: use linguagem técnica, mas explique brevemente conceitos avançados quando necessário.",
        "Estudante de Medicina":  "Dirija a resposta a um estudante de medicina: use linguagem didática, explique termos técnicos e contextualize os achados.",
        "Paciente / Leigo":       "Dirija a resposta a um paciente ou leigo: use linguagem simples, evite jargões e explique tudo de forma acessível.",
        "Enfermagem / Farmácia":  "Dirija a resposta a profissionais de enfermagem ou farmácia: foque em aspectos práticos de administração, monitoramento e segurança.",
    }
    TOM_MAP = {
        "Formal e Técnico":   "Use um tom formal, científico e altamente técnico.",
        "Direto e Objetivo":  "Use um tom direto e objetivo, sem rodeios. Priorize clareza e brevidade.",
        "Didático":           "Use um tom didático e explicativo, como se estivesse ensinando o conteúdo a alguém.",
    }
    IDIOMA_MAP = {
        "Português (BR)": "Responda inteiramente em português brasileiro.",
        "English":        "Respond entirely in English.",
        "Español":        "Responde completamente en español.",
    }
    DETALHE_MAP = {
        "Resumido":        "Seja conciso: priorize os pontos mais importantes e evite detalhes excessivos.",
        "Completo":        "Seja completo: cubra todos os pontos relevantes com nível de detalhe adequado.",
        "Ultra-detalhado": "Seja extremamente detalhado: explore cada ponto em profundidade, incluindo nuances e informações secundárias.",
    }
    FOCO_MAP = {
        "Farmacologia":    "Dê ênfase especial a informações farmacológicas: doses, mecanismos, interações e efeitos adversos.",
        "Estatística":     "Dê ênfase especial aos dados estatísticos: métricas de efeito, intervalos de confiança, NNT e significância clínica.",
        "Segurança":       "Dê ênfase especial à segurança do paciente: contraindicações, alertas, efeitos adversos e monitoramento.",
        "Metodologia":     "Dê ênfase especial à qualidade metodológica: desenho do estudo, vieses e nível de evidência.",
        "Clínico/Prático": "Dê ênfase especial à aplicabilidade clínica direta: o que muda na conduta, como e quando aplicar.",
    }

    if publico and publico in PUBLICO_MAP:
        extras.append(PUBLICO_MAP[publico])
    if tom and tom in TOM_MAP:
        extras.append(TOM_MAP[tom])
    if idioma and idioma in IDIOMA_MAP:
        extras.append(IDIOMA_MAP[idioma])
    if detalhe and detalhe in DETALHE_MAP:
        extras.append(DETALHE_MAP[detalhe])
    if foco and foco in FOCO_MAP:
        extras.append(FOCO_MAP[foco])

    if extras:
        prompt += "\n\n**Instruções de Personalização (aplicar sobre o prompt acima):**\n"
        for item in extras:
            prompt += f"- {item}\n"

    return prompt

def build_message_pontos_chave(article_title, abstract_text, sys_prompt=SYS_PROMPT):
    user_prompt = f"""Você é um especialista em síntese científica. Leia o artigo a seguir e extraia exatamente os 5 achados mais importantes, apresentados como frases curtas e diretas.

Título: {article_title}
Abstract:
{abstract_text}

**FORMATO OBRIGATÓRIO:** Liste exatamente 5 pontos numerados. Cada ponto deve ter no máximo 2 linhas. Sem subtópicos, sem parágrafos adicionais.

**Restrição absoluta:** Todos os pontos devem ser extraídos exclusivamente do texto fornecido. Nenhuma inferência, complemento ou conhecimento externo."""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_conduta_urgencia(article_title, abstract_text, sys_prompt=SYS_PROMPT):
    user_prompt = f"""Você é um médico emergencista. Extraia EXCLUSIVAMENTE o protocolo de manejo de urgência/emergência descrito no artigo a seguir.

Título: {article_title}
Abstract:
{abstract_text}

**AVISO DE USO CLÍNICO:** Informações extraídas exclusivamente do artigo. Não substitui protocolos institucionais ou julgamento clínico. Validar antes de aplicar em pacientes reais.

**FORMATO OBRIGATÓRIO:** Bullet points curtos. Sem tabelas.

1. **Indicação de Uso em Urgência** — quando aplicar (critérios do artigo)
2. **Sequência de Ações (passo a passo)** — ordem e tempo entre etapas (se mencionado)
3. **Doses Agudas e Vias de Administração** — dose de ataque, manutenção, velocidade de infusão
4. **Sinais de Resposta e Falha Terapêutica** — como reconhecer sucesso ou falha
5. **O que NÃO fazer** — contraindicações em urgência

**Restrição absoluta:** Se o artigo não descrever protocolo de urgência explícito, informe: "Este artigo não descreve um protocolo de manejo agudo de urgência." Nunca complete com conhecimento externo."""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_populacoes_especiais(article_title, abstract_text, sys_prompt=SYS_PROMPT):
    user_prompt = f"""Você é um clínico especializado em populações vulneráveis. Extraia como a intervenção descrita no artigo se modifica para populações especiais.

Título: {article_title}
Abstract:
{abstract_text}

**AVISO:** Informações extraídas exclusivamente do artigo.

**FORMATO OBRIGATÓRIO:** Para cada população presente no artigo, subtítulo em negrito seguido de bullet points. Se não mencionada: "Não descrito no artigo".

Analise: Gestantes/Lactantes, Idosos (≥65 anos), Pediátricos, Insuficiência Renal, Insuficiência Hepática, Imunossuprimidos, Outras populações mencionadas.

Para cada uma: ajuste de dose, contraindicações, monitoramento adicional, precauções.

**Restrição absoluta:** Somente informações do artigo. Nenhum ajuste baseado em conhecimento externo."""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_lacunas_pesquisa(article_title, abstract_text, sys_prompt=SYS_PROMPT):
    user_prompt = f"""Você é um pesquisador sênior. Extraia as lacunas de conhecimento e direções futuras mencionadas pelos autores do artigo.

Título: {article_title}
Abstract:
{abstract_text}

**FORMATO OBRIGATÓRIO:** Bullet points por subtópico em negrito.

1. **O que o estudo NÃO respondeu** — perguntas em aberto, limitações impeditivas
2. **Direções Futuras Sugeridas pelos Autores** — estudos recomendados, populações a investigar
3. **Lacunas Metodológicas** — o que precisaria ser feito diferente em estudos futuros
4. **Aplicabilidade Clínica Pendente** — o que ainda precisa ser demonstrado antes de aplicar na prática

**Restrição absoluta:** Somente lacunas e direções explicitamente mencionadas pelos autores. Não inferir lacunas baseadas em conhecimento externo."""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_comparacao_literatura(article_title, abstract_text, sys_prompt=SYS_PROMPT):
    user_prompt = f"""Você é um revisor científico. Analise como o artigo se posiciona em relação à literatura prévia, conforme descrito pelos autores.

Título: {article_title}
Abstract:
{abstract_text}

**FORMATO OBRIGATÓRIO:** Bullet points com subtítulos em negrito.

1. **O que os autores dizem sobre estudos anteriores** — estado atual da evidência, estudos citados
2. **Como este estudo se diferencia** — o que é novo, vantagens metodológicas citadas
3. **Concordâncias com literatura prévia** — achados que confirmam estudos anteriores
4. **Contradições ou Discordâncias** — achados que contradizem literatura (e como os autores explicam)

**Restrição absoluta:** Somente comparações que os próprios autores fazem. Não adicionar comparações baseadas em conhecimento externo."""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_disponibilidade_sus(article_title, abstract_text, sys_prompt=SYS_PROMPT):
    user_prompt = f"""Você é um médico com experiência no sistema público de saúde brasileiro. Avalie a disponibilidade das intervenções descritas no artigo no contexto do SUS.

Título: {article_title}
Abstract:
{abstract_text}

**FORMATO OBRIGATÓRIO:** Bullet points. Indique claramente quando informação vem do artigo e quando é conhecimento geral sobre o SUS.

1. **Intervenções Descritas no Artigo** *(do artigo)*
2. **Disponibilidade no SUS** — disponível/não disponível/parcial, presença na RENAME *[conhecimento geral - sinalizado]*
3. **Alternativas Disponíveis no SUS** *[conhecimento geral - sinalizado]*
4. **Impacto para o Médico do SUS** — o que pode ou não aplicar com base neste artigo"""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_vigilancia_sanitaria(article_title, abstract_text, sys_prompt=SYS_PROMPT):
    user_prompt = f"""Você é um médico com conhecimento em regulação sanitária brasileira. Analise o artigo sob perspectiva regulatória para o contexto brasileiro.

Título: {article_title}
Abstract:
{abstract_text}

**FORMATO OBRIGATÓRIO:** Bullet points. Diferencie o que vem do artigo e o que é contexto regulatório geral.

1. **Intervenções Estudadas** *(do artigo)*
2. **Situação Regulatória no Brasil** — aprovação ANVISA, restrições *[conhecimento geral - sinalizado]*
3. **Considerações para Prescrição** — receituário especial, restrições por especialidade *[conhecimento geral - sinalizado]*
4. **Riscos Regulatórios** — o que o médico deve considerar legalmente ao aplicar os achados no Brasil"""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_resumo_paciente(article_title, abstract_text, sys_prompt=SYS_PROMPT):
    user_prompt = f"""Explique os achados deste artigo científico para uma pessoa leiga — sem formação técnica na área. Use linguagem simples, acessível e clara, como se estivesse explicando para um familiar ou paciente.

Título: {article_title}
Abstract:
{abstract_text}

Estruture a resposta com os tópicos:
**O que os pesquisadores estavam tentando descobrir?**
**Como eles fizeram a pesquisa?**
**O que eles descobriram?**
**Por que isso importa para mim ou para a sociedade?**
**O que ainda não sabemos?**

**FORMATO:** Parágrafos curtos e simples. Explique termos técnicos entre parênteses. Sem bullet points densos.
**Restrição absoluta:** Somente informações do artigo."""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_resumo_estudante(article_title, abstract_text, sys_prompt=SYS_PROMPT):
    user_prompt = f"""Você é um professor com experiência em ensino nas áreas da saúde e ciências da vida. Explique este artigo para um estudante de graduação de forma didática e formativa — adaptando a linguagem ao contexto do artigo.

Título: {article_title}
Abstract:
{abstract_text}

Estruture a resposta com os tópicos:
1. **Contexto** — por que este tema é relevante na área científica do artigo?
2. **O Estudo** — desenho e metodologia de forma didática
3. **Os Achados** — resultados com explicação dos termos técnicos e estatísticos
4. **Para a Prática** — como aplicar esse conhecimento profissionalmente
5. **Conceitos-Chave** — termos técnicos do artigo com breve definição

**FORMATO:** Misture bullet points e parágrafos curtos. Linguagem técnica correta mas explicativa.
**Restrição absoluta:** Somente informações do artigo."""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_questoes_discussao(article_title, abstract_text, sys_prompt=SYS_PROMPT):
    user_prompt = f"""Você é um professor de medicina baseada em evidências. Elabore exatamente 5 perguntas para debate em grupo de estudo ou journal club baseadas neste artigo.

Título: {article_title}
Abstract:
{abstract_text}

**FORMATO OBRIGATÓRIO:** 5 perguntas numeradas em negrito, cada uma seguida de justificativa de 1-2 linhas. Sem respostas.

Cubra: validade metodológica, aplicabilidade clínica, aspectos éticos/segurança, comparação com conhecimento prévio (mencionado no artigo), direções futuras.

**Restrição absoluta:** Perguntas baseadas nos achados específicos do artigo."""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_confiabilidade(article_title, abstract_text, sys_prompt=SYS_PROMPT):
    user_prompt = f"""Você é um epidemiologista clínico sênior. Avalie a confiabilidade deste artigo de forma rigorosa. Esta é a ÚNICA análise em que você deve expressar sua própria opinião fundamentada. Seja extremamente rigoroso — este resultado pode influenciar condutas em pacientes reais em pronto-socorro. Em caso de dúvida, seja conservador.

Título: {article_title}
Abstract:
{abstract_text}

**FORMATO OBRIGATÓRIO:** Bullet points com subtítulos em negrito.

Avalie cada dimensão e indique impacto na confiabilidade (alto/médio/baixo):

1. **Desenho do Estudo** — tipo, nível de evidência, adequação. Impacto: [alto/médio/baixo]
2. **Tamanho Amostral e Poder** — N reportado, risco de erro tipo II. Impacto: [alto/médio/baixo]
3. **Controle de Vieses** — randomização, cegamento, grupos comparáveis. Impacto: [alto/médio/baixo]
4. **Qualidade Estatística** — IC 95%, significância vs. relevância clínica. Impacto: [alto/médio/baixo]
5. **Conflito de Interesses** — financiamento declarado. Impacto: [alto/médio/baixo]
6. **Generalizabilidade** — representatividade, extrapolação. Impacto: [alto/médio/baixo]
7. **Limitações Declaradas** — limitações reconhecidas pelos autores. Impacto: [alto/médio/baixo]

---

**VEREDICTO FINAL**

**Score de Confiabilidade: X%**

- 90–100%: Evidência muito sólida
- 70–89%: Evidência boa, aplicável com cautela
- 50–69%: Evidência moderada, referência auxiliar
- 30–49%: Evidência fraca, não aplicar diretamente
- 0–29%: Evidência insuficiente, não utilizar para condutas

**Justificativa do Score:** (2-3 linhas)

**Recomendação para uso em Pronto-Socorro:** [PODE USAR COM SEGURANÇA / USAR COM CAUTELA / NÃO USAR COMO BASE PRINCIPAL / NÃO RECOMENDADO]

*Esta avaliação é uma opinião técnica fundamentada nos dados do abstract. Avaliação completa requer leitura do artigo na íntegra.*"""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]


# ===========================================================================

def build_message_implicacoes_praticas(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """Universal: what this research changes in the real world."""
    user_prompt = f"""Analise o artigo a seguir e extraia exclusivamente as implicações práticas dos achados — o que este estudo muda ou pode mudar no mundo real, na prática profissional ou na sociedade.

Título: {article_title}
Abstract:
{abstract_text}

Estruture em:
1. **Implicação Imediata** — o que muda agora com base nestes achados
2. **Impacto para Profissionais** — como afeta quem trabalha na área
3. **Impacto para a Sociedade** — benefícios ou riscos para o público geral
4. **Próximos Passos Necessários** — o que precisa acontecer para essa descoberta ter impacto real

**FORMATO:** Bullet points diretos. Sem tabelas.
**Restrição absoluta:** Somente informações do artigo. Se o artigo não mencionar implicações práticas, indique explicitamente."""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_glossario(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """Universal: extract and explain technical terms from the article."""
    user_prompt = f"""Analise o artigo a seguir e extraia todos os termos técnicos, siglas, metodologias e jargões especializados presentes no texto, explicando cada um de forma clara e concisa.

Título: {article_title}
Abstract:
{abstract_text}

Para cada termo identificado, apresente:
- **Termo / Sigla**
- **Definição:** explicação clara em 1-3 linhas
- **Contexto no artigo:** como o termo é usado neste estudo específico

Ordene do mais ao menos técnico. Priorize termos que um leitor sem formação na área não conheceria.

**FORMATO:** Lista estruturada. Sem tabelas.
**Restrição absoluta:** Somente termos presentes no artigo. Definições podem usar conhecimento geral para explicar, mas o contexto deve ser do artigo."""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_impacto_brasil(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """Universal Brazilian context - not health-specific."""
    user_prompt = f"""Analise o artigo a seguir e avalie sua relevância e aplicabilidade ao contexto brasileiro, considerando aspectos sociais, econômicos, regulatórios e práticos — independentemente da área do artigo.

Título: {article_title}
Abstract:
{abstract_text}

**FORMATO:** Bullet points. Indique quando informação vem do artigo e quando é contexto geral sobre o Brasil.

Estruture em:
1. **Contexto Original do Estudo** — onde foi conduzido, qual população/contexto *(do artigo)*
2. **Relevância para o Brasil** — por que este estudo importa para o contexto brasileiro
3. **Barreiras de Implementação no Brasil** — custo, infraestrutura, regulação, cultura *[contexto geral - sinalizado]*
4. **Oportunidades** — onde o Brasil pode se beneficiar ou já está avançado nesta área *[contexto geral - sinalizado]*
5. **Recomendação Prática** — o que um profissional brasileiro deve considerar ao aplicar estes achados"""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]

def build_message_resumo_introdutorio(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """For someone starting to learn about the topic."""
    user_prompt = f"""Você é um professor com habilidade em introduzir tópicos complexos para iniciantes. Explique este artigo para alguém que está começando a estudar a área — com contexto suficiente para entender a importância do estudo.

Título: {article_title}
Abstract:
{abstract_text}

Estruture em:
1. **Contexto da Área** — o que é importante saber sobre este campo para entender o artigo (baseado no que o próprio artigo menciona)
2. **O Problema que o Estudo Aborda** — qual questão estava sem resposta
3. **O que os Pesquisadores Fizeram** — metodologia simplificada
4. **O que Descobriram** — resultados principais em linguagem acessível
5. **Por que é Importante** — relevância para a área e para a prática
6. **O que Estudar Mais** — conceitos-chave mencionados no artigo para aprofundar

**FORMATO:** Parágrafos curtos e didáticos. Evite jargões sem explicação.
**Restrição absoluta:** O contexto da área deve ser baseado no que o artigo menciona, não em conhecimento externo adicionado."""
    return [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user_prompt}]



# ===========================================================================
# PÁGINAS INDEPENDENTES
# ===========================================================================
