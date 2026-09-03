import re
import os
import threading
from functools import lru_cache
from dotenv import load_dotenv
load_dotenv()  # carrega o .env automaticamente em modo local

import requests
import functools
from typing import List, Tuple, Dict, Any, Generator

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


# ---------------------------------------------------------------------------
# Cache de artigos em memória (evita buscar o mesmo artigo duas vezes)
# ---------------------------------------------------------------------------
_article_cache: Dict[str, Tuple[str, str]] = {}
_cache_lock = threading.Lock()

def get_cached_article(article_id: str) -> Tuple[str, str] | None:
    with _cache_lock:
        return _article_cache.get(article_id)

def set_cached_article(article_id: str, title: str, abstract: str) -> None:
    with _cache_lock:
        # mantém no máximo 20 artigos em cache
        if len(_article_cache) >= 20:
            oldest = next(iter(_article_cache))
            del _article_cache[oldest]
        _article_cache[article_id] = (title, abstract)


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
    response.raise_for_status()  # check for request errors
    return bs(response.content, "lxml-xml")


def clean_text(text: str) -> str:
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


def fetch_full_text(soup: bs) -> Tuple[str, str]:
    """
    Extracts the full text from the XML soup, combining all main sections.
    Falls back to abstract-only if no body sections are found.

    Returns:
        Tuple(article_title (str), full_text (str))
    """
    if soup is None:
        return "No XML found", ""

    article_title = soup.find("article-title").get_text(strip=True) if soup.find("article-title") else "No Title Found"

    # Seções principais do artigo
    SECTION_LABELS = {
        "intro":        "Introdução",
        "methods":      "Métodos",
        "results":      "Resultados",
        "discussion":   "Discussão",
        "conclusions":  "Conclusão",
        "abstract":     "Abstract",
    }

    sections = []

    # Tenta extrair pelo atributo sec-type
    for sec in soup.find_all("sec"):
        sec_type = (sec.get("sec-type") or "").lower()
        label = None
        for key, name in SECTION_LABELS.items():
            if key in sec_type:
                label = name
                break
        if label is None:
            title_tag = sec.find("title")
            if title_tag:
                label = title_tag.get_text(strip=True)
            else:
                continue
        paragraphs = [clean_text(p.get_text(strip=True)) for p in sec.find_all("p") if p.get_text(strip=True)]
        if paragraphs:
            sections.append(f"**{label}:**\n" + " ".join(paragraphs))

    # Se não encontrou seções, usa o abstract como fallback
    if not sections:
        abstract_tag = soup.find("abstract")
        if abstract_tag:
            abstract_text = ' '.join([clean_text(p.get_text(strip=True)) for p in abstract_tag.find_all("p") if p.get_text(strip=True)])
            return article_title, abstract_text
        return article_title, ""

    return article_title, "\n\n".join(sections)


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


def generate_response_stream(messages: List[Dict[str, str]], model: str) -> Generator[str, None, None]:
    """
    Streams the LLM response token by token.
    Yields accumulated text so Gradio can update the UI progressively.
    """
    if USE_GROQ:
        groq_model = GROQ_MODEL_MAP.get(model, "openai/gpt-oss-120b")
        stream = groq_client.chat.completions.create(
            model=groq_model,
            messages=messages,
            stream=True,
            timeout=120,
        )
        accumulated = ""
        for chunk in stream:
            delta = chunk.choices[0].delta.content or ""
            accumulated += delta
            yield accumulated
    else:
        ollama.pull(model)
        accumulated = ""
        for chunk in ollama.chat(model=model, messages=messages, stream=True):
            delta = chunk["message"]["content"] or ""
            accumulated += delta
            yield accumulated


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
            timeout=120,
        )
        return response.choices[0].message.content
    else:
        ollama.pull(model)
        response = ollama.chat(model=model, messages=messages)
        return response["message"]["content"]


@catch_request_error
@logger.catch
def get_abstract_from_pmid(pmid: str) -> Tuple[str, str]:
    """Busca título e abstract via Europe PMC por PMID."""
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


# ---------------------------------------------------------------------------
# Sistema universal de detecção e busca de artigos
# ---------------------------------------------------------------------------

def detect_input_type(raw: str) -> Tuple[str, str]:
    """
    Detecta o tipo de identificador ou URL fornecido pelo usuário.
    Retorna (tipo, valor_normalizado).
    """
    s = raw.strip()

    url_patterns = [
        (r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", "pmid"),
        (r"ncbi\.nlm\.nih\.gov/pubmed/(\d+)", "pmid"),
        (r"pmc\.ncbi\.nlm\.nih\.gov/articles/(PMC\d+)", "pmcid"),
        (r"ncbi\.nlm\.nih\.gov/pmc/articles/(PMC\d+)", "pmcid"),
        (r"europepmc\.org/article/MED/(\d+)", "pmid"),
        (r"europepmc\.org/articles/(PMC\d+)", "pmcid"),
        (r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)", "arxiv"),
        (r"arxiv\.org/(?:abs|pdf)/([a-z\-]+/\d+)", "arxiv"),
        (r"doi\.org/(10\.\d{4,}/\S+)", "doi"),
        (r"openalex\.org/(W\d+)", "openalex"),
        (r"semanticscholar\.org/paper/[^/]+/([a-f0-9]{40})", "semantic_scholar"),
    ]

    for pattern, id_type in url_patterns:
        m = re.search(pattern, s, re.IGNORECASE)
        if m:
            return id_type, m.group(1)

    if re.match(r"^PMC\d{4,}$", s, re.IGNORECASE):
        return "pmcid", s.upper()
    if re.match(r"^\d{6,9}$", s):
        return "pmid", s
    if re.match(r"^10\.\d{4,}/\S+$", s):
        return "doi", s
    if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", s):
        return "arxiv", s
    if re.match(r"^[a-z\-]+/\d{7}$", s, re.IGNORECASE):
        return "arxiv", s
    if re.match(r"^W\d{6,}$", s, re.IGNORECASE):
        return "openalex", s.upper()
    if re.match(r"^[a-f0-9]{40}$", s):
        return "semantic_scholar", s

    return "unknown", s


def fetch_by_doi(doi: str) -> Tuple[str, str]:
    """Busca abstract via Semantic Scholar por DOI."""
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=title,abstract"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            title = data.get("title", "")
            abstract = clean_text(data.get("abstract") or "")
            if title and abstract:
                return title, abstract
    except Exception:
        pass

    url2 = f"https://api.crossref.org/works/{doi}"
    try:
        r2 = requests.get(url2, timeout=10,
                          headers={"User-Agent": "BiomedicalDataDigger/1.0"})
        if r2.status_code == 200:
            item = r2.json().get("message", {})
            title_raw = item.get("title", [""])
            title = title_raw[0] if title_raw else "Título não encontrado"
            abstract_raw = item.get("abstract", "")
            abstract = clean_text(re.sub(r"<[^>]+>", " ", abstract_raw))
            if title and abstract:
                return title, abstract
            if title:
                return title, ""
    except Exception:
        pass

    return "Artigo não encontrado via DOI", ""


def fetch_by_arxiv(arxiv_id: str) -> Tuple[str, str]:
    """Busca abstract via arXiv API."""
    clean_id = re.sub(r"v\d+$", "", arxiv_id)
    url = f"https://export.arxiv.org/api/query?id_list={clean_id}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        soup = bs(r.content, "lxml-xml")
        entry = soup.find("entry")
        if not entry:
            return "Artigo não encontrado no arXiv", ""
        title_tag = entry.find("title")
        summary_tag = entry.find("summary")
        t = clean_text(title_tag.get_text()) if title_tag else "Título não encontrado"
        a = clean_text(summary_tag.get_text()) if summary_tag else ""
        return t, a
    except Exception as e:
        return f"Erro ao buscar no arXiv: {e}", ""


def fetch_by_openalex(openalex_id: str) -> Tuple[str, str]:
    """Busca abstract via OpenAlex por ID (Wxxxxxxx)."""
    url = f"https://api.openalex.org/works/{openalex_id}"
    try:
        r = requests.get(url, timeout=10,
                         headers={"User-Agent": "BiomedicalDataDigger/1.0"})
        r.raise_for_status()
        data = r.json()
        title = data.get("title", "Título não encontrado")
        inv_index = data.get("abstract_inverted_index")
        if inv_index:
            max_pos = max(pos for positions in inv_index.values() for pos in positions)
            words = [""] * (max_pos + 1)
            for word, positions in inv_index.items():
                for pos in positions:
                    words[pos] = word
            abstract = clean_text(" ".join(words))
        else:
            abstract = ""
        return title, abstract
    except Exception as e:
        return f"Erro ao buscar no OpenAlex: {e}", ""


def fetch_by_semantic_scholar(s2_id: str) -> Tuple[str, str]:
    """Busca abstract via Semantic Scholar por ID de 40 chars."""
    url = f"https://api.semanticscholar.org/graph/v1/paper/{s2_id}?fields=title,abstract"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        data = r.json()
        title = data.get("title", "Título não encontrado")
        abstract = clean_text(data.get("abstract") or "")
        return title, abstract
    except Exception as e:
        return f"Erro ao buscar no Semantic Scholar: {e}", ""


def resolve_article(raw_input: str) -> Tuple[str, str, str]:
    """
    Ponto de entrada universal. Aceita qualquer ID ou URL.
    Retorna (article_title, abstract_text, fonte_descricao).
    """
    id_type, value = detect_input_type(raw_input.strip())

    if id_type == "pmcid":
        url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{value}/fullTextXML"
        soup = get_xml_from_url(url)
        title, abstract = fetch_article_abstract(soup)
        return title, abstract, "Europe PMC (PMCID)"

    if id_type == "pmid":
        title, abstract = get_abstract_from_pmid(value)
        return title, abstract, "PubMed / Europe PMC (PMID)"

    if id_type == "doi":
        title, abstract = fetch_by_doi(value)
        return title, abstract, "DOI via Semantic Scholar / CrossRef"

    if id_type == "arxiv":
        title, abstract = fetch_by_arxiv(value)
        return title, abstract, "arXiv"

    if id_type == "openalex":
        title, abstract = fetch_by_openalex(value)
        return title, abstract, "OpenAlex"

    if id_type == "semantic_scholar":
        title, abstract = fetch_by_semantic_scholar(value)
        return title, abstract, "Semantic Scholar"

    if value.isdigit():
        title, abstract = get_abstract_from_pmid(value)
        return title, abstract, "PubMed (PMID)"

    raise gr.Error(
        "Não foi possível identificar o formato do ID ou URL.\n\n"
        "Formatos aceitos:\n"
        "• PMID: 33984217\n"
        "• PMCID: PMC8234567\n"
        "• DOI: 10.1038/nature12373\n"
        "• arXiv: 2301.00001\n"
        "• OpenAlex: W2741809807\n"
        "• URL completa de qualquer uma dessas fontes"
    )


def summariser(article_id: str, model: str, build_fn,
               publico: str = "", tom: str = "", idioma: str = "",
               detalhe: str = "", foco: str = "") -> str:
    if not article_id or not article_id.strip():
        raise gr.Error("Por favor, cole um ID ou URL de artigo antes de gerar a análise.")

    if not USE_GROQ:
        raise gr.Error("Nenhum backend de LLM disponível. Configure a variável GROQ_API_KEY.")

    cache_key = article_id.strip()
    cached = get_cached_article(cache_key)
    if cached:
        article_title, abstract_text = cached
    else:
        try:
            article_title, abstract_text, fonte = resolve_article(article_id)
            if article_title and abstract_text:
                set_cached_article(cache_key, article_title, abstract_text)
        except gr.Error:
            raise
        except Exception as e:
            raise gr.Error(f"Erro ao buscar artigo: {str(e)}")

    if not abstract_text:
        raise gr.Error(
            f"Nenhum abstract encontrado para: {article_title}\n\n"
            "O artigo pode ser de acesso restrito (paywall). "
            "Tente buscar pelo DOI em outra fonte ou use um PMCID de artigo Open Access."
        )

    dynamic_prompt = build_dynamic_sys_prompt(publico, tom, idioma, detalhe, foco)

    try:
        messages = build_fn(article_title, abstract_text, sys_prompt=dynamic_prompt)
        summary = generate_response(messages, model)
    except Exception as e:
        raise gr.Error(f"Erro ao gerar resumo com a LLM: {str(e)}")

    return f"## Título do Artigo: {article_title}\n\n### Resumo:\n{summary}"


def summariser_with_label(article_id: str, model: str, build_fn, label: str,
                          publico: str = "", tom: str = "", idioma: str = "",
                          detalhe: str = "", foco: str = "") -> str:
    result = summariser(article_id, model, build_fn, publico, tom, idioma, detalhe, foco)
    filtros_ativos = [f for f in [publico, tom, idioma, detalhe, foco] if f]
    filtros_str = "  |  ".join(filtros_ativos) if filtros_ativos else "Padrão"
    return f"---\n> **{label}**  ·  Filtros: *{filtros_str}*\n\n---\n{result}"


INTRO_TXT = "Análise inteligente de artigos científicos. Cole qualquer ID ou URL de artigo."
INST_TXT = "Cole um **PMID**, **PMCID**, **DOI**, **arXiv ID**, **OpenAlex ID** ou a **URL completa** do artigo"


# ===========================================================================
# NOVAS FUNÇÕES DE PROMPT
# ===========================================================================

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
# INTERFACE GRADIO
# ===========================================================================

# ===========================================================================
# TEMA VISUAL CUSTOMIZADO
# ===========================================================================

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* ── Variáveis de tema ─────────────────────────────────────────────────── */
:root {
    --bg-primary:    #0a0e1a;
    --bg-secondary:  #111827;
    --bg-card:       #1a2236;
    --bg-input:      #151e2e;
    --accent:        #3b82f6;
    --accent-hover:  #2563eb;
    --accent-glow:   rgba(59,130,246,0.18);
    --accent-dim:    rgba(59,130,246,0.10);
    --text-primary:  #e2e8f0;
    --text-muted:    #94a3b8;
    --text-dim:      #64748b;
    --border:        rgba(59,130,246,0.18);
    --border-hover:  rgba(59,130,246,0.45);
    --radius:        10px;
    --radius-lg:     14px;
    --font-main:     'Inter', system-ui, sans-serif;
    --font-mono:     'JetBrains Mono', monospace;
    --shadow:        0 4px 24px rgba(0,0,0,0.45);
    --shadow-glow:   0 0 20px rgba(59,130,246,0.12);
}

/* Tema claro */
.light-theme {
    --bg-primary:    #f0f4ff;
    --bg-secondary:  #e8edf8;
    --bg-card:       #ffffff;
    --bg-input:      #f8faff;
    --accent:        #2563eb;
    --accent-hover:  #1d4ed8;
    --accent-glow:   rgba(37,99,235,0.12);
    --accent-dim:    rgba(37,99,235,0.07);
    --text-primary:  #0f172a;
    --text-muted:    #475569;
    --text-dim:      #94a3b8;
    --border:        rgba(37,99,235,0.18);
    --border-hover:  rgba(37,99,235,0.40);
    --shadow:        0 4px 24px rgba(0,0,0,0.10);
    --shadow-glow:   0 0 20px rgba(37,99,235,0.08);
}

/* ── Base ──────────────────────────────────────────────────────────────── */
body, .gradio-container {
    background: var(--bg-primary) !important;
    font-family: var(--font-main) !important;
    color: var(--text-primary) !important;
}

.gradio-container {
    max-width: 1400px !important;
    margin: 0 auto !important;
    padding: 24px !important;
}

/* ── Header ────────────────────────────────────────────────────────────── */
.app-header {
    text-align: center;
    padding: 32px 0 20px 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 28px;
}

.app-header h1 {
    font-family: var(--font-main) !important;
    font-size: 2rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.5px !important;
    color: var(--text-primary) !important;
    margin: 0 0 6px 0 !important;
}

.app-header .accent { color: var(--accent) !important; }

.app-subtitle {
    color: var(--text-muted) !important;
    font-size: 0.9rem !important;
    font-weight: 400 !important;
    margin: 0 !important;
}

/* ── Painel de controles ───────────────────────────────────────────────── */
.control-panel {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    padding: 20px !important;
    box-shadow: var(--shadow) !important;
}

/* ── Input / Textbox ───────────────────────────────────────────────────── */
input[type="text"], textarea, .gr-text-input, .gr-textbox textarea {
    background: var(--bg-input) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    color: var(--text-primary) !important;
    font-family: var(--font-mono) !important;
    font-size: 0.95rem !important;
    padding: 12px 16px !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}

input[type="text"]:focus, textarea:focus {
    border-color: var(--accent) !important;
    box-shadow: 0 0 0 3px var(--accent-dim) !important;
    outline: none !important;
}

/* ── Labels ────────────────────────────────────────────────────────────── */
label, .gr-form label, span.svelte-1gfkn6j {
    font-family: var(--font-main) !important;
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    color: var(--text-muted) !important;
}

/* ── Dropdown ──────────────────────────────────────────────────────────── */
.gr-dropdown select, select {
    background: var(--bg-input) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    color: var(--text-primary) !important;
    font-family: var(--font-main) !important;
    padding: 10px 14px !important;
}

/* ── Botões secundários ────────────────────────────────────────────────── */
button.secondary, .gr-button-secondary, button[variant="secondary"] {
    background: var(--bg-input) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    color: var(--text-primary) !important;
    font-family: var(--font-main) !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    padding: 10px 14px !important;
    transition: all 0.2s !important;
    cursor: pointer !important;
}

button.secondary:hover, .gr-button-secondary:hover {
    background: var(--accent-dim) !important;
    border-color: var(--accent) !important;
    color: var(--accent) !important;
    box-shadow: var(--shadow-glow) !important;
    transform: translateY(-1px) !important;
}

/* ── Botão primário (Confiabilidade) ───────────────────────────────────── */
button.primary, .gr-button-primary, button[variant="primary"] {
    background: var(--accent) !important;
    border: none !important;
    border-radius: var(--radius) !important;
    color: #fff !important;
    font-family: var(--font-main) !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.04em !important;
    padding: 12px 18px !important;
    transition: all 0.2s !important;
    box-shadow: 0 0 16px var(--accent-glow) !important;
    cursor: pointer !important;
}

button.primary:hover, .gr-button-primary:hover {
    background: var(--accent-hover) !important;
    box-shadow: 0 0 24px rgba(59,130,246,0.35) !important;
    transform: translateY(-1px) !important;
}

/* ── Accordion ─────────────────────────────────────────────────────────── */
.gr-accordion, details {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    margin-bottom: 8px !important;
    overflow: hidden !important;
    transition: border-color 0.2s !important;
}

.gr-accordion:hover, details:hover {
    border-color: var(--border-hover) !important;
}

.gr-accordion summary, details summary {
    font-family: var(--font-main) !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
    color: var(--text-muted) !important;
    padding: 14px 18px !important;
    cursor: pointer !important;
    transition: color 0.2s !important;
    user-select: none !important;
}

.gr-accordion summary:hover, details summary:hover {
    color: var(--accent) !important;
}

/* ── Output box ────────────────────────────────────────────────────────── */
.output-panel {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-lg) !important;
    padding: 24px !important;
    min-height: 400px !important;
    box-shadow: var(--shadow) !important;
    font-family: var(--font-main) !important;
    font-size: 0.95rem !important;
    line-height: 1.75 !important;
    color: var(--text-primary) !important;
}

.output-panel h2 {
    font-size: 1.15rem !important;
    font-weight: 700 !important;
    color: var(--accent) !important;
    border-bottom: 1px solid var(--border) !important;
    padding-bottom: 10px !important;
    margin-bottom: 16px !important;
}

.output-panel h3 {
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    margin-bottom: 12px !important;
}

.output-panel ul, .output-panel ol {
    padding-left: 20px !important;
}

.output-panel li {
    margin-bottom: 6px !important;
    color: var(--text-primary) !important;
}

.output-panel strong {
    color: var(--text-primary) !important;
    font-weight: 600 !important;
}

.output-panel blockquote, .output-panel > blockquote {
    border-left: 3px solid var(--accent) !important;
    background: var(--accent-dim) !important;
    padding: 10px 16px !important;
    border-radius: 0 var(--radius) var(--radius) 0 !important;
    margin: 12px 0 !important;
    color: var(--text-muted) !important;
    font-size: 0.85rem !important;
}

/* ── Radio buttons ─────────────────────────────────────────────────────── */
.gr-radio input[type="radio"] + label,
.gr-form .gr-radio span {
    font-family: var(--font-main) !important;
    font-size: 0.85rem !important;
    color: var(--text-muted) !important;
}

/* ── Dataframe / Tabela ────────────────────────────────────────────────── */
.gr-dataframe table, table {
    background: var(--bg-input) !important;
    border-radius: var(--radius) !important;
    font-family: var(--font-mono) !important;
    font-size: 0.8rem !important;
}

.gr-dataframe th {
    background: var(--bg-card) !important;
    color: var(--text-muted) !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    padding: 10px 14px !important;
}

.gr-dataframe td {
    color: var(--text-primary) !important;
    padding: 8px 14px !important;
    border-color: var(--border) !important;
}

/* ── Toggle de tema ────────────────────────────────────────────────────── */
.theme-toggle {
    position: fixed !important;
    top: 16px !important;
    right: 16px !important;
    z-index: 9999 !important;
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-radius: 20px !important;
    padding: 6px 14px !important;
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    cursor: pointer !important;
    color: var(--text-muted) !important;
    transition: all 0.2s !important;
    letter-spacing: 0.04em !important;
}

.theme-toggle:hover {
    border-color: var(--accent) !important;
    color: var(--accent) !important;
}

/* ── Scrollbar ─────────────────────────────────────────────────────────── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--bg-primary); }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: var(--accent); }

/* ── Progress bar ──────────────────────────────────────────────────────── */
.progress-bar { background: var(--accent) !important; height: 2px !important; }
"""

THEME_TOGGLE_JS = """
function() {
    const container = document.querySelector('.gradio-container');
    if (container) {
        container.classList.toggle('light-theme');
        const btn = document.getElementById('theme-toggle-btn');
        if (btn) {
            btn.textContent = container.classList.contains('light-theme') ? '🌙 Escuro' : '☀️ Claro';
        }
    }
}
"""


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

def make_page_geral():
    """Cria a página Geral como um gr.Blocks independente."""
    with gr.Blocks(
        theme=gr.themes.Base(
            primary_hue=gr.themes.colors.blue,
            neutral_hue=gr.themes.colors.slate,
            font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
            font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
        ),
        css=CUSTOM_CSS,
    ) as page:

        gr.HTML("""
        <div class="app-header">
          <h1><span class="accent">Biomedical</span> Data Digger</h1>
          <p class="app-subtitle">Análise científica universal · Europe PMC · arXiv · DOI · OpenAlex</p>
        </div>
        <button class="theme-toggle" id="theme-toggle-btn-geral"
          onclick="(function(){
            const c=document.querySelector('.gradio-container');
            c.classList.toggle('light-theme');
            this.textContent=c.classList.contains('light-theme')?'🌙 Escuro':'☀️ Claro';
          }).call(this)">☀️ Claro</button>
        """)

        session_history = gr.State([])

        with gr.Row(equal_height=False):
          with gr.Column(scale=1, min_width=320):

            with gr.Group():
              article_id = gr.Textbox(
                  label="ID ou URL do artigo",
                  placeholder="ex: 33984217 · PMC8234567 · 10.1038/nature · arxiv.org/abs/2301.00001",
              )
              model_choice = gr.Dropdown(
                  choices=["GPT-OSS 20B (Groq)", "GPT-OSS 120B (Groq)", "Qwen 3.6 27B (Groq)", "Qwen 3.8 27B (Groq)", "Llama (local)"],
                  value="GPT-OSS 20B (Groq)",
                  label="Modelo de linguagem",
              )

            with gr.Accordion("Como encontrar o ID ou URL?", open=False):
              gr.Markdown("""
**Cole qualquer um destes formatos — o sistema detecta automaticamente:**

**PubMed (PMID):** `33984217` ou `https://pubmed.ncbi.nlm.nih.gov/33984217/`

**PubMed Central (PMCID):** `PMC8234567` ou `https://pmc.ncbi.nlm.nih.gov/articles/PMC8234567/`

**DOI (qualquer área):** `10.1038/s41586-021-03819-2` ou `https://doi.org/10.1038/s41586-021-03819-2`

**arXiv:** `2301.00001` ou `https://arxiv.org/abs/2301.00001`

**OpenAlex:** `W2741809807` ou `https://openalex.org/W2741809807`

💡 **Dica:** Copie a URL da barra do navegador e cole aqui diretamente.
              """)

            with gr.Accordion("Histórico da sessão", open=False):
              history_display = gr.Dataframe(
                  headers=["ID", "Título"], datatype=["str", "str"],
                  interactive=False, label=None, wrap=True,
              )

            with gr.Accordion("Personalização (opcional)", open=False):
              gr.Markdown("<small>Filtros opcionais — sem seleção, cada botão usa seu padrão.</small>")
              filtro_publico = gr.Radio(choices=["Médico / Especialista", "Residente / Interno", "Estudante", "Pesquisador", "Leigo / Paciente"], value=None, label="Público-alvo")
              filtro_tom     = gr.Radio(choices=["Formal e Técnico", "Direto e Objetivo", "Didático"], value=None, label="Tom")
              filtro_idioma  = gr.Radio(choices=["Português (BR)", "English", "Español"], value=None, label="Idioma")
              filtro_detalhe = gr.Radio(choices=["Resumido", "Completo", "Ultra-detalhado"], value=None, label="Detalhe")
              filtro_foco    = gr.Radio(choices=["Farmacologia", "Estatística", "Segurança", "Metodologia", "Clínico/Prático"], value=None, label="Foco")
              btn_limpar     = gr.Button("↺  Limpar filtros", size="sm", variant="secondary")

            with gr.Accordion("Visão Geral", open=True):
              with gr.Row():
                btn_sumario      = gr.Button("Sumário",            variant="secondary")
                btn_resumo       = gr.Button("Resumo",             variant="secondary")
              with gr.Row():
                btn_pontos_chave = gr.Button("Pontos-Chave",       variant="secondary")
                btn_resumo_intro = gr.Button("Resumo Introdutório",variant="secondary")

            with gr.Accordion("Análise Científica", open=False):
              with gr.Row():
                btn_academico  = gr.Button("Resumo Acadêmico",     variant="secondary")
                btn_critica    = gr.Button("Crítica Metodológica", variant="secondary")
              with gr.Row():
                btn_estatist   = gr.Button("Dados Estatísticos",   variant="secondary")
                btn_pico       = gr.Button("PICO",                 variant="secondary")
              with gr.Row():
                btn_lacunas    = gr.Button("Lacunas de Pesquisa",  variant="secondary")
                btn_comparacao = gr.Button("Comparação Literatura",variant="secondary")
              with gr.Row():
                btn_implicacoes = gr.Button("Implicações Práticas", variant="secondary")
              with gr.Row():
                btn_confiab    = gr.Button("Confiabilidade do Artigo", variant="primary")

            with gr.Accordion("Educacional", open=False):
              with gr.Row():
                btn_leigo    = gr.Button("Para Leigo / Paciente",  variant="secondary")
                btn_estudante = gr.Button("Para Estudante",        variant="secondary")
              with gr.Row():
                btn_questoes  = gr.Button("Questões para Discussão",variant="secondary")
                btn_glossario = gr.Button("Glossário de Termos",   variant="secondary")

            with gr.Accordion("Contexto Brasileiro", open=False):
              with gr.Row():
                btn_impacto_br = gr.Button("Impacto no Brasil",    variant="secondary")
                btn_aplicab    = gr.Button("Aplicabilidade BR",    variant="secondary")

          with gr.Column(scale=2, min_width=480):
            output_box = gr.Markdown(
                value="*Selecione um tipo de análise e clique em um botão para começar.*",
                elem_classes=["output-panel"],
            )

        def update_history(aid_val, history):
            aid = aid_val.strip() if aid_val else ""
            if not aid: return history, gr.update()
            cached = get_cached_article(aid)
            if cached and not any(r[0] == aid for r in history):
                title = cached[0][:60] + "..." if len(cached[0]) > 60 else cached[0]
                history = [[aid, title]] + history
                history = history[:10]
            rows = history if history else [["—", "Nenhum artigo consultado ainda"]]
            return history, gr.update(value=rows)

        btn_limpar.click(fn=lambda: (None,None,None,None,None), inputs=[],
                         outputs=[filtro_publico, filtro_tom, filtro_idioma, filtro_detalhe, filtro_foco])

        ci = [article_id, model_choice, filtro_publico, filtro_tom, filtro_idioma, filtro_detalhe, filtro_foco]
        ai = ci + [session_history]
        ao = [output_box, session_history, history_display]

        def mfh(build_fn, label):
            def fn(aid, mdl, pub, tom, idi, det, foc, hist):
                result = summariser_with_label(aid, mdl, build_fn, label, pub or "", tom or "", idi or "", det or "", foc or "")
                nh, nd = update_history(aid, hist)
                return result, nh, nd
            return fn

        btn_sumario.click(fn=mfh(build_message_sumario,"Sumário"), inputs=ai, outputs=ao, show_progress="full")
        btn_resumo.click(fn=mfh(build_message_resumo,"Resumo"), inputs=ai, outputs=ao, show_progress="full")
        btn_pontos_chave.click(fn=mfh(build_message_pontos_chave,"Pontos-Chave"), inputs=ai, outputs=ao, show_progress="full")
        btn_resumo_intro.click(fn=mfh(build_message_resumo_introdutorio,"Resumo Introdutório"), inputs=ai, outputs=ao, show_progress="full")
        btn_academico.click(fn=mfh(build_message_resumo_academico,"Resumo Acadêmico"), inputs=ai, outputs=ao, show_progress="full")
        btn_critica.click(fn=mfh(build_message_critica_metodologica,"Crítica Metodológica"), inputs=ai, outputs=ao, show_progress="full")
        btn_estatist.click(fn=mfh(build_message_estatisticas,"Dados Estatísticos"), inputs=ai, outputs=ao, show_progress="full")
        btn_pico.click(fn=mfh(build_message_pico,"Pergunta PICO"), inputs=ai, outputs=ao, show_progress="full")
        btn_lacunas.click(fn=mfh(build_message_lacunas_pesquisa,"Lacunas de Pesquisa"), inputs=ai, outputs=ao, show_progress="full")
        btn_comparacao.click(fn=mfh(build_message_comparacao_literatura,"Comparação com Literatura"), inputs=ai, outputs=ao, show_progress="full")
        btn_implicacoes.click(fn=mfh(build_message_implicacoes_praticas,"Implicações Práticas"), inputs=ai, outputs=ao, show_progress="full")
        btn_confiab.click(fn=mfh(build_message_confiabilidade,"Confiabilidade do Artigo"), inputs=ai, outputs=ao, show_progress="full")
        btn_leigo.click(fn=mfh(build_message_resumo_paciente,"Para Leigo / Paciente"), inputs=ai, outputs=ao, show_progress="full")
        btn_estudante.click(fn=mfh(build_message_resumo_estudante,"Para Estudante"), inputs=ai, outputs=ao, show_progress="full")
        btn_questoes.click(fn=mfh(build_message_questoes_discussao,"Questões para Discussão"), inputs=ai, outputs=ao, show_progress="full")
        btn_glossario.click(fn=mfh(build_message_glossario,"Glossário de Termos"), inputs=ai, outputs=ao, show_progress="full")
        btn_impacto_br.click(fn=mfh(build_message_impacto_brasil,"Impacto no Brasil"), inputs=ai, outputs=ao, show_progress="full")
        btn_aplicab.click(fn=mfh(build_message_aplicabilidade_br,"Aplicabilidade Brasileira"), inputs=ai, outputs=ao, show_progress="full")

    return page


def make_page_medicina():
    """Cria a página Medicina como um gr.Blocks independente."""
    with gr.Blocks(
        theme=gr.themes.Base(
            primary_hue=gr.themes.colors.blue,
            neutral_hue=gr.themes.colors.slate,
            font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
            font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
        ),
        css=CUSTOM_CSS,
    ) as page:

        gr.HTML("""
        <div class="app-header">
          <h1><span class="accent">Biomedical</span> Data Digger <span style="font-size:1rem;color:#94a3b8;font-weight:400">— Medicina</span></h1>
          <p class="app-subtitle">Pronto-Socorro · Farmacologia · Segurança do Paciente · Contexto Brasileiro</p>
        </div>
        <button class="theme-toggle" id="theme-toggle-btn-med"
          onclick="(function(){
            const c=document.querySelector('.gradio-container');
            c.classList.toggle('light-theme');
            this.textContent=c.classList.contains('light-theme')?'🌙 Escuro':'☀️ Claro';
          }).call(this)">☀️ Claro</button>
        """)

        session_history = gr.State([])

        with gr.Row(equal_height=False):
          with gr.Column(scale=1, min_width=320):

            with gr.Group():
              article_id = gr.Textbox(
                  label="ID ou URL do artigo",
                  placeholder="ex: 33984217 · PMC8234567 · 10.1038/nature12373",
              )
              model_choice = gr.Dropdown(
                  choices=["GPT-OSS 20B (Groq)", "GPT-OSS 120B (Groq)", "Qwen 3.6 27B (Groq)", "Qwen 3.8 27B (Groq)", "Llama (local)"],
                  value="GPT-OSS 20B (Groq)",
                  label="Modelo de linguagem",
              )

            with gr.Accordion("Como encontrar o ID ou URL?", open=False):
              gr.Markdown("""
**Cole qualquer um destes formatos — o sistema detecta automaticamente:**

**PubMed (PMID):** `33984217` ou `https://pubmed.ncbi.nlm.nih.gov/33984217/`

**PubMed Central (PMCID):** `PMC8234567` ou `https://pmc.ncbi.nlm.nih.gov/articles/PMC8234567/`

**DOI:** `10.1038/s41586-021-03819-2` ou `https://doi.org/10.1038/s41586-021-03819-2`

💡 **Dica:** Copie a URL da barra do navegador e cole aqui diretamente.
              """)

            with gr.Accordion("Histórico da sessão", open=False):
              history_display = gr.Dataframe(
                  headers=["ID", "Título"], datatype=["str", "str"],
                  interactive=False, label=None, wrap=True,
              )

            with gr.Accordion("Personalização (opcional)", open=False):
              gr.Markdown("<small>Filtros opcionais — sem seleção, cada botão usa seu padrão.</small>")
              filtro_publico = gr.Radio(choices=["Médico / Especialista", "Residente / Interno", "Estudante de Medicina", "Enfermagem / Farmácia"], value=None, label="Público-alvo")
              filtro_tom     = gr.Radio(choices=["Formal e Técnico", "Direto e Objetivo", "Didático"], value=None, label="Tom")
              filtro_idioma  = gr.Radio(choices=["Português (BR)", "English", "Español"], value=None, label="Idioma")
              filtro_detalhe = gr.Radio(choices=["Resumido", "Completo", "Ultra-detalhado"], value=None, label="Detalhe")
              filtro_foco    = gr.Radio(choices=["Farmacologia", "Estatística", "Segurança", "Metodologia", "Clínico/Prático"], value=None, label="Foco")
              btn_limpar     = gr.Button("↺  Limpar filtros", size="sm", variant="secondary")

            with gr.Accordion("Resumos Clínicos", open=True):
              with gr.Row():
                btn_clinico    = gr.Button("Resumo Clínico",        variant="secondary")
                btn_resumo_med = gr.Button("Resumo Médico",         variant="secondary")

            with gr.Accordion("Farmacologia e Protocolos", open=False):
              with gr.Row():
                btn_medicamentos  = gr.Button("Medicamentos / Protocolos", variant="secondary")
                btn_pop_especiais = gr.Button("Populações Especiais",      variant="secondary")
              with gr.Row():
                btn_conduta = gr.Button("Conduta em Urgência", variant="secondary")

            with gr.Accordion("Segurança do Paciente", open=False):
              with gr.Row():
                btn_alertas   = gr.Button("Alertas e Contraindicações", variant="secondary")
                btn_checklist = gr.Button("Checklist Pré-Conduta",      variant="secondary")
              with gr.Row():
                btn_confiab   = gr.Button("Confiabilidade do Artigo",   variant="primary")

            with gr.Accordion("Contexto BR — Saúde", open=False):
              with gr.Row():
                btn_sus    = gr.Button("Disponib. SUS",        variant="secondary")
                btn_anvisa = gr.Button("Vigilância Sanitária", variant="secondary")
              with gr.Row():
                btn_aplicab = gr.Button("Aplicabilidade BR", variant="secondary")

          with gr.Column(scale=2, min_width=480):
            output_box = gr.Markdown(
                value="*Selecione um tipo de análise e clique em um botão para começar.*",
                elem_classes=["output-panel"],
            )

        def update_history(aid_val, history):
            aid = aid_val.strip() if aid_val else ""
            if not aid: return history, gr.update()
            cached = get_cached_article(aid)
            if cached and not any(r[0] == aid for r in history):
                title = cached[0][:60] + "..." if len(cached[0]) > 60 else cached[0]
                history = [[aid, title]] + history
                history = history[:10]
            rows = history if history else [["—", "Nenhum artigo consultado ainda"]]
            return history, gr.update(value=rows)

        btn_limpar.click(fn=lambda: (None,None,None,None,None), inputs=[],
                         outputs=[filtro_publico, filtro_tom, filtro_idioma, filtro_detalhe, filtro_foco])

        ci = [article_id, model_choice, filtro_publico, filtro_tom, filtro_idioma, filtro_detalhe, filtro_foco]
        ai = ci + [session_history]
        ao = [output_box, session_history, history_display]

        def mfh(build_fn, label):
            def fn(aid, mdl, pub, tom, idi, det, foc, hist):
                result = summariser_with_label(aid, mdl, build_fn, label, pub or "", tom or "", idi or "", det or "", foc or "")
                nh, nd = update_history(aid, hist)
                return result, nh, nd
            return fn

        btn_clinico.click(fn=mfh(build_message_resumo_clinico,"Resumo Clínico"), inputs=ai, outputs=ao, show_progress="full")
        btn_resumo_med.click(fn=mfh(build_message_resumo_academico,"Resumo Médico"), inputs=ai, outputs=ao, show_progress="full")
        btn_medicamentos.click(fn=mfh(build_message_medicamentos,"Medicamentos / Protocolos"), inputs=ai, outputs=ao, show_progress="full")
        btn_pop_especiais.click(fn=mfh(build_message_populacoes_especiais,"Populações Especiais"), inputs=ai, outputs=ao, show_progress="full")
        btn_conduta.click(fn=mfh(build_message_conduta_urgencia,"Conduta em Urgência"), inputs=ai, outputs=ao, show_progress="full")
        btn_alertas.click(fn=mfh(build_message_alertas,"Alertas e Contraindicações"), inputs=ai, outputs=ao, show_progress="full")
        btn_checklist.click(fn=mfh(build_message_checklist,"Checklist Pré-Conduta"), inputs=ai, outputs=ao, show_progress="full")
        btn_confiab.click(fn=mfh(build_message_confiabilidade,"Confiabilidade do Artigo"), inputs=ai, outputs=ao, show_progress="full")
        btn_sus.click(fn=mfh(build_message_disponibilidade_sus,"Disponibilidade no SUS"), inputs=ai, outputs=ao, show_progress="full")
        btn_anvisa.click(fn=mfh(build_message_vigilancia_sanitaria,"Vigilância Sanitária"), inputs=ai, outputs=ao, show_progress="full")
        btn_aplicab.click(fn=mfh(build_message_aplicabilidade_br,"Aplicabilidade Brasileira"), inputs=ai, outputs=ao, show_progress="full")

    return page


def gradio_ui():
    page_geral = make_page_geral()
    page_medicina = make_page_medicina()
    app = gr.TabbedInterface(
        [page_geral, page_medicina],
        tab_names=["☰  Geral", "⚕  Medicina"],
        title="Biomedical Data Digger",
    )
    return app


if __name__ == "__main__":
    app = gradio_ui()
    port = int(os.environ.get("PORT", 7860))
    app.launch(server_name="0.0.0.0", server_port=port)
