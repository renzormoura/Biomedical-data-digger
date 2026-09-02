import re
import os

from dotenv import load_dotenv
load_dotenv()  # carrega o .env automaticamente em modo local

import requests
import functools
from typing import List, Tuple, Dict, Any

from loguru import logger

from bs4 import BeautifulSoup as bs

import gradio as gr

# ---------------------------------------------------------------------------
# Backend de LLM: usa Groq (nuvem) se GROQ_API_KEY estiver definida,
# caso contrário usa Ollama local.
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
USE_GROQ = bool(GROQ_API_KEY)

if USE_GROQ:
    from groq import Groq
    groq_client = Groq(api_key=GROQ_API_KEY)
    # Mapeamento de nomes amigáveis → modelos Groq disponíveis
    GROQ_MODEL_MAP = {
        "GPT-OSS 120B (Groq)": "openai/gpt-oss-120b",
        "GPT-OSS 20B (Groq)":  "openai/gpt-oss-20b",
        "Qwen 3.6 27B (Groq)": "qwen/qwen3.6-27b",
        "Qwen 3.8 27B (Groq)": "qwen/qwen3.8-27b",
        "Llama (local)":        "llama3.2",
    }
else:
    import ollama



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




def catch_request_error(func):
    """
    Função wrapper para capturar erros de requisição e retornar None caso ocorra um erro.
    Utilizada como decorador.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.RequestException as e:
            print(f"Request error in {func.__name__}: {e}")
            return None
    return wrapper



@catch_request_error
@logger.catch
def get_xml_from_url(url: str) -> bs:
    """
    Fetches the XML content from Europe PMC website.

    Args:
        url (str): Europe PMC's production url to fetch the XML from.

    Returns:
        soup (bs4.BeautifulSoup): Parsed XML content.
    """
    response = requests.get(url)
    response.raise_for_status() #check for request errors
    return bs(response.content, "lxml-xml")  




def clean_text(text:str) -> str:
    """
    This function cleans a text by filtering reference patterns in text, 
    extra whitespaces, escaped latex-style formatting appearing in text body instead of predefined latex tags

    Args: 
    text(str): The text to be cleaned
    
    Returns: 
    tex(str): The cleaned text 
    
    """
   
    # Remove LaTeX-style math and formatting tags #already filtered from soup content but some still appear
    text = re.sub(r"\{.*?\}", "", text)  # Matches and removes anything inside curly braces {}
    text = re.sub(r"\\[a-zA-Z]+", "", text)  # Matches and removes characters that appears with numbers
    
    # Remove reference tags like [34] or [1,2,3]
    text = re.sub(r"\[\s*(\d+\s*(,\s*\d+\s*)*)\]", "", text)
    
    # Remove extra whitespace
    text = re.sub(r"\s+", " ", text).strip()
    
    return text


def fetch_article_abstract(soup: bs) -> Tuple[str, str]:
    """
    Extracts the abstract text from the XML soup.

    Args:
        soup (bs4.BeautifulSoup): Parsed XML content.
    Returns:
        Tuple(article_title (str), abstract_text (str)): A tuple of the article's title and its extracted abstract text.
    """
    if soup is None:
        return "No XML found", ""
    article_title = soup.find("article-title").get_text(strip=True) if soup.find("article-title") else "No Title Found for this article"

    abstract_tag = soup.find("abstract")
    if abstract_tag:
        abstract_text = ' '.join([clean_text(p.get_text(strip=True)) for p in abstract_tag.find_all("p") if p.get_text(strip=True)])
    else:
        abstract_text = ""
    return article_title, abstract_text



from typing import List, Dict

def build_message_resumo_academico(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """
    Constructs the payload for an Academic/Scientific Summary (Research & Methodology focus).
    """
    user_prompt = f"""Você é um pesquisador sênior e revisor de periódicos médicos. Analise o artigo a seguir e forneça um resumo técnico de alto nível, voltado para acadêmicos, cientistas e estudantes de pós-graduação.

Título: {article_title}
Abstract:
{abstract_text}

Instruções de Estrutura:
- Use linguagem científica avançada, rigorosa e precisa.
- Apresente métricas estatísticas e quantitativas sempre que disponíveis no texto (ex: p-value, IC 95%, HR, N).
- Estruture a resposta com os tópicos:
  1. Desenho do Estudo e Amostra (N)
  2. Racional Científico & Hipótese
  3. Metodologia e Principais Achados
  4. Análise Crítica: Limitações do Estudo e Lacunas de Conhecimento
  5. Conclusão Acadêmica (em um parágrafo síntese ao final)"""

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ]


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
    """
    Constructs the payload for a balanced general summary — not too simple, not too advanced.
    Designed to be the neutral starting point, refined by user filters.
    """
    user_prompt = f"""Analise o artigo biomédico a seguir e produza um resumo equilibrado, adequado para qualquer profissional da área da saúde independentemente do nível de especialização.

Título: {article_title}
Abstract:
{abstract_text}

Instruções:
- Use linguagem clara e acessível, sem ser simplista. Mantenha termos técnicos essenciais, mas não sobrecarregue com jargões desnecessários.
- Seja completo sem ser excessivamente longo.
- Estruture a resposta com os tópicos:
  1. **O que foi estudado** — contexto e objetivo do estudo
  2. **Como foi feito** — desenho e metodologia em linguagem direta
  3. **O que foi encontrado** — principais resultados com dados relevantes
  4. **O que isso significa** — implicações práticas ou científicas
  5. **Síntese final** — um parágrafo curto de fechamento"""

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ]


def build_message_sumario(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """
    Constructs the payload for a Quick Bulleted Summary / Overview.
    """
    user_prompt = f"""Você está analisando um artigo médico com o título: {article_title}.
O abstract do artigo é o seguinte:
{abstract_text}

Resuma o artigo em português de forma direta e objetiva. Comece com uma frase curta (de até 2 linhas) que sintetize o tema principal do artigo, seguida de uma lista em marcadores (bullet points) destacando os 4 a 6 pontos mais importantes do estudo (objetivo, métodos, resultados e conclusão). Finalize com um parágrafo curto de fechamento."""

    return [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_prompt}
    ]

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

1. **🚫 Contraindicações Absolutas**
   - Situações em que a intervenção/medicamento NÃO deve ser usado em hipótese alguma (conforme descrito no artigo)

2. **⚠️ Contraindicações Relativas e Populações de Risco**
   - Grupos que requerem cautela especial ou ajuste de conduta
   - Ex: gestantes, idosos, insuficiência renal/hepática, crianças, imunossuprimidos

3. **🔴 Efeitos Adversos Graves**
   - Reações adversas com risco de vida ou que exijam interrupção imediata
   - Frequência reportada (%) quando disponível

4. **🟡 Efeitos Adversos Relevantes**
   - Efeitos adversos frequentes ou que impactem adesão/conduta
   - Frequência reportada (%) quando disponível

5. **💊 Interações Medicamentosas**
   - Interações descritas no artigo com potencial de dano clínico
   - Mecanismo da interação (se descrito)

6. **📊 Sinais de Alerta para Monitoramento**
   - Parâmetros clínicos e laboratoriais que indicam toxicidade ou falha terapêutica
   - Valores limítrofes de alerta mencionados

7. **🆘 Conduta em Caso de Reação Grave**
   - O que o artigo descreve como manejo de toxicidade ou reação adversa grave
   - Antídoto ou tratamento de suporte mencionado

8. **✅ Checklist de Segurança Pré-Uso**
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

1. **👤 Critérios de Elegibilidade do Paciente**
   - [ ] Perfil do paciente que se beneficia da intervenção (conforme o artigo)
   - [ ] Critérios de inclusão que devem estar presentes

2. **🚫 Critérios de Exclusão — Não Aplicar Se:**
   - [ ] Condições que contraindicam a intervenção (conforme o artigo)

3. **🔬 Exames e Avaliações Pré-Intervenção**
   - [ ] Exames laboratoriais necessários antes de iniciar
   - [ ] Avaliações clínicas recomendadas (PA, FC, função renal, etc.)

4. **💊 Preparo da Intervenção / Medicamento**
   - [ ] Dose correta para o perfil do paciente
   - [ ] Diluição e preparo (se aplicável)
   - [ ] Via e velocidade de administração

5. **🩺 Monitoramento Durante a Intervenção**
   - [ ] Parâmetros a monitorar e frequência
   - [ ] Sinais de alerta que indicam interrupção imediata

6. **📋 Documentação e Seguimento**
   - [ ] O que deve ser registrado em prontuário
   - [ ] Quando reavaliar o paciente após a intervenção
   - [ ] Exames de controle pós-intervenção (se descritos)

7. **🆘 Plano de Contingência**
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

1. **🌍 Origem do Estudo e Contexto Original**
   - País(es) onde o estudo foi conduzido (se mencionado)
   - Perfil da população estudada e sistema de saúde envolvido
   - Contexto clínico original (ambulatorial, hospitalar, PS, atenção primária)

2. **👥 Comparação Populacional**
   - Semelhanças e diferenças entre a população do estudo e a população brasileira
   - Diferenças étnicas, epidemiológicas ou de comorbidades relevantes (se inferíveis do artigo)
   - Faixa etária e perfil socioeconômico estudado vs. realidade brasileira

3. **💊 Disponibilidade dos Medicamentos / Intervenções no Brasil**
   - Os medicamentos ou tecnologias estudados estão disponíveis no Brasil?
   - Estão na RENAME (Relação Nacional de Medicamentos Essenciais) ou disponíveis pelo SUS?
   - Há alternativas nacionais equivalentes?

4. **🏥 Aplicabilidade por Nível de Atenção**
   - A intervenção é viável na Atenção Primária (UBS)?
   - É aplicável em Pronto-Socorro ou UPA?
   - Requer estrutura hospitalar especializada (UTI, centro cirúrgico)?

5. **⚖️ Barreiras e Facilitadores para Implementação no Brasil**
   - Principais barreiras: custo, infraestrutura, treinamento, regulação (ANVISA)
   - Facilitadores: políticas públicas, protocolos do Ministério da Saúde, disponibilidade

6. **📊 Força da Evidência para o Contexto Brasileiro**
   - Os resultados são diretamente extrapoláveis para o Brasil?
   - Quais adaptações seriam necessárias?
   - Qual o grau de confiança recomendado para aplicar esses resultados na prática brasileira?

7. **🎯 Recomendação Prática para o Médico Brasileiro**
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
        "Farmacologia":  "Dê ênfase especial a informações farmacológicas: doses, mecanismos, interações e efeitos adversos.",
        "Estatística":   "Dê ênfase especial aos dados estatísticos: métricas de efeito, intervalos de confiança, NNT e significância clínica.",
        "Segurança":     "Dê ênfase especial à segurança do paciente: contraindicações, alertas, efeitos adversos e monitoramento.",
        "Metodologia":   "Dê ênfase especial à qualidade metodológica: desenho do estudo, vieses e nível de evidência.",
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


def generate_response(messages: List[Dict[str, str]], model: str) -> str:
    """
    Generates a response from the LLM based on the provided messages.
    Uses Groq API when GROQ_API_KEY is set, otherwise falls back to local Ollama.
    """
    if USE_GROQ:
        groq_model = GROQ_MODEL_MAP.get(model, "openai/gpt-oss-120b")
        response = groq_client.chat.completions.create(
            model=groq_model,
            messages=messages,
        )
        return response.choices[0].message.content
    else:
        ollama.pull(model)
        response = ollama.chat(model=model, messages=messages)
        return response["message"]["content"]


@catch_request_error
@logger.catch
def get_abstract_from_pmid(pmid: str) -> Tuple[str, str]:
    """
    Busca o título e abstract de um artigo pelo PMID via endpoint de busca do Europe PMC.

    Args:
        pmid (str): O PMID numérico do artigo.

    Returns:
        Tuple(article_title (str), abstract_text (str)): Título e abstract do artigo.
    """
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:{pmid}&resultType=core&format=json"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()
    results = data.get("resultList", {}).get("result", [])
    if not results:
        return "Artigo não encontrado", ""
    article = results[0]
    title = article.get("title", "Título não encontrado")
    abstract = clean_text(article.get("abstractText", ""))
    return title, abstract


def summariser(article_id: str, model: str, build_fn,
               publico: str = "", tom: str = "", idioma: str = "",
               detalhe: str = "", foco: str = "") -> str:
    # Validação do ID
    if not article_id or not article_id.strip():
        raise gr.Error("Por favor, digite um PMCID ou PMID antes de gerar o resumo.")

    article_id = article_id.strip()

    if not re.match(r"^(PMC\d{5,8}|\d{5,9})$", article_id):
        raise gr.Error("Formato de ID inválido. Use um PMCID (ex: 'PMC1234567') ou um PMID numérico (ex: '12345678').")

    # Verificação do backend LLM
    if not USE_GROQ:
        raise gr.Error("Nenhum backend de LLM disponível. Configure a variável GROQ_API_KEY.")

    # Busca do artigo
    try:
        if re.match(r"^\d+$", article_id):
            article_title, abstract_text = get_abstract_from_pmid(article_id)
        else:
            url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{article_id}/fullTextXML"
            soup = get_xml_from_url(url)
            article_title, abstract_text = fetch_article_abstract(soup)
    except Exception as e:
        raise gr.Error(f"Erro ao buscar artigo: {str(e)}")

    if not abstract_text:
        raise gr.Error(f"Nenhum abstract encontrado para: {article_title}")

    # Monta o sys_prompt dinâmico com os filtros selecionados
    dynamic_prompt = build_dynamic_sys_prompt(publico, tom, idioma, detalhe, foco)

    # Geração do resumo
    try:
        messages = build_fn(article_title, abstract_text, sys_prompt=dynamic_prompt)
        summary = generate_response(messages, model)
    except Exception as e:
        raise gr.Error(f"Erro ao gerar resumo com a LLM: {str(e)}")

    return f"## 📝 Título do Artigo: {article_title}\n\n### 📌 Resumo:\n{summary}"


def summariser_with_label(article_id: str, model: str, build_fn, label: str,
                          publico: str = "", tom: str = "", idioma: str = "",
                          detalhe: str = "", foco: str = "") -> str:
    result = summariser(article_id, model, build_fn, publico, tom, idioma, detalhe, foco)
    filtros_ativos = [f for f in [publico, tom, idioma, detalhe, foco] if f]
    filtros_str = "  |  ".join(filtros_ativos) if filtros_ativos else "Padrão"
    return f"---\n> 🔖 **{label}**  &nbsp;·&nbsp;  🎛️ Filtros: *{filtros_str}*\n\n---\n{result}"

INTRO_TXT = "Este é um sumarizador simples de artigos biomédicos. Ele aceita PMCID ou PMID para buscar artigos do Europe PMC (EPMC). Atualmente utiliza apenas o abstract do artigo. Melhorias futuras incluirão integração com o texto completo."
INST_TXT = "Digite um **PMCID** (ex: `PMC1234567`) ou **PMID** numérico (ex: `33970586`) e selecione um modelo para gerar um resumo estruturado"
def gradio_ui():
  with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown(INTRO_TXT)
    gr.Markdown(INST_TXT)

    with gr.Row():
      with gr.Column(scale=1):
        article_id = gr.Textbox(label="Digite o PMCID ou PMID do artigo", placeholder="ex: PMC1234567 ou 12345678")
        model_choice = gr.Dropdown(
            choices=["GPT-OSS 120B (Groq)", "GPT-OSS 20B (Groq)", "Qwen 3.6 27B (Groq)", "Qwen 3.8 27B (Groq)", "Llama (local)"],
            value="GPT-OSS 120B (Groq)",
            label="Modelo"
        )

        # ── Painel de personalização ──────────────────────────────────────
        with gr.Accordion("🎛️ Personalização (opcional)", open=False):
          gr.Markdown("Selecione os filtros desejados. Sem seleção, o comportamento é o padrão de cada botão.")
          filtro_publico = gr.Radio(
              choices=["Médico / Especialista", "Residente / Interno", "Estudante de Medicina", "Paciente / Leigo", "Enfermagem / Farmácia"],
              value=None, label="👤 Público-alvo", interactive=True
          )
          filtro_tom = gr.Radio(
              choices=["Formal e Técnico", "Direto e Objetivo", "Didático"],
              value=None, label="🗣️ Tom da resposta", interactive=True
          )
          filtro_idioma = gr.Radio(
              choices=["Português (BR)", "English", "Español"],
              value=None, label="🌐 Idioma", interactive=True
          )
          filtro_detalhe = gr.Radio(
              choices=["Resumido", "Completo", "Ultra-detalhado"],
              value=None, label="📏 Nível de detalhe", interactive=True
          )
          filtro_foco = gr.Radio(
              choices=["Farmacologia", "Estatística", "Segurança", "Metodologia", "Clínico/Prático"],
              value=None, label="🔍 Foco temático", interactive=True
          )
          btn_limpar_filtros = gr.Button("Limpar filtros", size="sm")
        # ─────────────────────────────────────────────────────────────────

        with gr.Row():
          btn_sumario          = gr.Button("Sumário",              variant="secondary")
          btn_academico        = gr.Button("Resumo Acadêmico", variant="secondary")
        with gr.Row():
          btn_clinico          = gr.Button("Resumo Clínico",   variant="secondary")
          btn_resumo           = gr.Button("Resumo",           variant="secondary")
        with gr.Row():
          btn_medicamentos     = gr.Button("Medicamentos / Protocolos",  variant="secondary")
          btn_alertas          = gr.Button("Alertas e Contraindicações",  variant="secondary")
        with gr.Row():
          btn_checklist        = gr.Button("Checklist Pré-Conduta",      variant="secondary")
          btn_pico             = gr.Button("Pergunta PICO",               variant="secondary")
        with gr.Row():
          btn_estatisticas     = gr.Button("Dados Estatísticos",           variant="secondary")
          btn_aplicabilidade   = gr.Button("Aplicabilidade Brasileira",    variant="secondary")
        with gr.Row():
          btn_critica          = gr.Button("Crítica Metodológica",         variant="secondary")

      with gr.Column(scale=1):
        output_box = gr.Markdown(value="*O resumo aparecerá aqui...*")

    # inputs comuns a todos os botões
    common_inputs = [article_id, model_choice, filtro_publico, filtro_tom, filtro_idioma, filtro_detalhe, filtro_foco]

    btn_limpar_filtros.click(
        fn=lambda: (None, None, None, None, None),
        inputs=[], outputs=[filtro_publico, filtro_tom, filtro_idioma, filtro_detalhe, filtro_foco]
    )

    btn_sumario.click(
        fn=lambda aid, mdl, pub, tom, idi, det, foc: summariser_with_label(aid, mdl, build_message_sumario, "Súmario", pub or "", tom or "", idi or "", det or "", foc or ""),
        inputs=common_inputs, outputs=output_box, show_progress="full"
    )
    btn_academico.click(
        fn=lambda aid, mdl, pub, tom, idi, det, foc: summariser_with_label(aid, mdl, build_message_resumo_academico, "Resumo Acadêmico", pub or "", tom or "", idi or "", det or "", foc or ""),
        inputs=common_inputs, outputs=output_box, show_progress="full"
    )
    btn_clinico.click(
        fn=lambda aid, mdl, pub, tom, idi, det, foc: summariser_with_label(aid, mdl, build_message_resumo_clinico, "Resumo Clínico", pub or "", tom or "", idi or "", det or "", foc or ""),
        inputs=common_inputs, outputs=output_box, show_progress="full"
    )
    btn_resumo.click(
        fn=lambda aid, mdl, pub, tom, idi, det, foc: summariser_with_label(aid, mdl, build_message_resumo, "Resumo", pub or "", tom or "", idi or "", det or "", foc or ""),
        inputs=common_inputs, outputs=output_box, show_progress="full"
    )
    btn_medicamentos.click(
        fn=lambda aid, mdl, pub, tom, idi, det, foc: summariser_with_label(aid, mdl, build_message_medicamentos, "💊 Medicamentos / Protocolos", pub or "", tom or "", idi or "", det or "", foc or ""),
        inputs=common_inputs, outputs=output_box, show_progress="full"
    )
    btn_alertas.click(
        fn=lambda aid, mdl, pub, tom, idi, det, foc: summariser_with_label(aid, mdl, build_message_alertas, "⚠️ Alertas e Contraindicações", pub or "", tom or "", idi or "", det or "", foc or ""),
        inputs=common_inputs, outputs=output_box, show_progress="full"
    )
    btn_checklist.click(
        fn=lambda aid, mdl, pub, tom, idi, det, foc: summariser_with_label(aid, mdl, build_message_checklist, "📋 Checklist Pré-Conduta", pub or "", tom or "", idi or "", det or "", foc or ""),
        inputs=common_inputs, outputs=output_box, show_progress="full"
    )
    btn_pico.click(
        fn=lambda aid, mdl, pub, tom, idi, det, foc: summariser_with_label(aid, mdl, build_message_pico, "🩺 Pergunta PICO", pub or "", tom or "", idi or "", det or "", foc or ""),
        inputs=common_inputs, outputs=output_box, show_progress="full"
    )
    btn_estatisticas.click(
        fn=lambda aid, mdl, pub, tom, idi, det, foc: summariser_with_label(aid, mdl, build_message_estatisticas, "📊 Dados Estatísticos", pub or "", tom or "", idi or "", det or "", foc or ""),
        inputs=common_inputs, outputs=output_box, show_progress="full"
    )
    btn_aplicabilidade.click(
        fn=lambda aid, mdl, pub, tom, idi, det, foc: summariser_with_label(aid, mdl, build_message_aplicabilidade_br, "🌍 Aplicabilidade Brasileira", pub or "", tom or "", idi or "", det or "", foc or ""),
        inputs=common_inputs, outputs=output_box, show_progress="full"
    )
    btn_critica.click(
        fn=lambda aid, mdl, pub, tom, idi, det, foc: summariser_with_label(aid, mdl, build_message_critica_metodologica, "🔬 Crítica Metodológica", pub or "", tom or "", idi or "", det or "", foc or ""),
        inputs=common_inputs, outputs=output_box, show_progress="full"
    )

  return demo


if __name__ == "__main__":
  app = gradio_ui()
  # Render injeta a porta via variável de ambiente PORT
  port = int(os.environ.get("PORT", 7860))
  app.launch(server_name="0.0.0.0", server_port=port)



