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
        "llama3.2":    "openai/gpt-oss-20b",
        "deepseek-r1": "qwen/qwen3.6-27b",
        "gemma3":      "qwen/qwen3.8-27b",
        "mistral":     "openai/gpt-oss-120b",
        "gpt-oss":     "openai/gpt-oss-120b",
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


def build_message_resumo_simples(article_title: str, abstract_text: str, sys_prompt: str = SYS_PROMPT) -> List[Dict[str, str]]:
    """
    Constructs the payload for a Simplified Summary (Layperson / Patient / Student focus).
    """
    user_prompt = f"""Você é um divulgador científico especializado em saúde. Explique os achados deste artigo médico de forma simples, clara e acessível para leigos, pacientes ou estudantes iniciantes.

Título: {article_title}
Abstract:
{abstract_text}

Instruções de Estrutura:
- Utilize uma linguagem fácil de entender, evitando jargões médicos complexos ou explicando-os brevemente de forma didática quando forem essenciais.
- Evite fórmulas estatísticas densas.
- Estruture a resposta com os tópicos:
  1. Qual era o objetivo principal da pesquisa?
  2. Como o estudo foi feito? (Exposição didática)
  3. O que os pesquisadores descobriram?
  4. Por que essa descoberta importa?
  5. O que isso muda na prática? (em um parágrafo final amigável)"""

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

def generate_response(messages: List[Dict[str, str]], model: str) -> str:
    """
    Generates a response from the LLM based on the provided messages.
    Uses Groq API when GROQ_API_KEY is set, otherwise falls back to local Ollama.

    Args:
        messages (List[Dict[str, str]]): The message payload for the LLM.
        model (str): The model name selected in the UI.
    Returns:
        str: The content of the LLM's response.
    """
    if USE_GROQ:
        groq_model = GROQ_MODEL_MAP.get(model, "llama-3.3-70b-versatile")
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


def summariser(article_id: str, model: str, build_fn) -> str:
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

    # Geração do resumo
    try:
        messages = build_fn(article_title, abstract_text)
        summary = generate_response(messages, model)
    except Exception as e:
        raise gr.Error(f"Erro ao gerar resumo com a LLM: {str(e)}")

    return f"## 📝 Título do Artigo: {article_title}\n\n### 📌 Resumo:\n{summary}"


def summariser_with_label(article_id: str, model: str, build_fn, label: str) -> str:
    result = summariser(article_id, model, build_fn)
    return f"---\n> 🔖 Tipo de resumo gerado: **{label}**\n\n---\n{result}"

INTRO_TXT = "Este é um sumarizador simples de artigos biomédicos. Ele aceita PMCID ou PMID para buscar artigos do Europe PMC (EPMC). Atualmente utiliza apenas o abstract do artigo. Melhorias futuras incluirão integração com o texto completo."
INST_TXT = "Digite um **PMCID** (ex: `PMC1234567`) ou **PMID** numérico (ex: `33970586`) e selecione um modelo para gerar um resumo estruturado"
def gradio_ui():
  with gr.Blocks(theme=gr.themes.Soft()) as demo:
    gr.Markdown(INTRO_TXT)
    gr.Markdown(INST_TXT)

    with gr.Row():
      with gr.Column(scale=1):
        article_id = gr.Textbox(label="Digite o PMCID ou PMID do artigo", placeholder="ex: PMC1234567 ou 12345678")
        model_choice = gr.Dropdown(choices=["llama3.2", "deepseek-r1", "gemma3", "mistral", "gpt-oss"], value="llama3.2", label="Select a model")
        with gr.Row():
          btn_sumario          = gr.Button("Súmario",          variant="primary")
          btn_academico        = gr.Button("Resumo Acadêmico", variant="secondary")
        with gr.Row():
          btn_clinico          = gr.Button("Resumo Clínico",   variant="secondary")
          btn_simples          = gr.Button("Resumo Simples",   variant="secondary")
      with gr.Column(scale=1):
        output_box = gr.Markdown(value="*O resumo aparecerá aqui...*")

    btn_sumario.click(
        fn=lambda aid, mdl: summariser_with_label(aid, mdl, build_message_sumario, "Súmario"),
        inputs=[article_id, model_choice], outputs=output_box,
        show_progress="full"
    )
    btn_academico.click(
        fn=lambda aid, mdl: summariser_with_label(aid, mdl, build_message_resumo_academico, "Resumo Acadêmico"),
        inputs=[article_id, model_choice], outputs=output_box,
        show_progress="full"
    )
    btn_clinico.click(
        fn=lambda aid, mdl: summariser_with_label(aid, mdl, build_message_resumo_clinico, "Resumo Clínico"),
        inputs=[article_id, model_choice], outputs=output_box,
        show_progress="full"
    )
    btn_simples.click(
        fn=lambda aid, mdl: summariser_with_label(aid, mdl, build_message_resumo_simples, "Resumo Simples"),
        inputs=[article_id, model_choice], outputs=output_box,
        show_progress="full"
    )

  return demo


if __name__ == "__main__":
  app = gradio_ui()
  # Render injeta a porta via variável de ambiente PORT
  port = int(os.environ.get("PORT", 7860))
  app.launch(server_name="0.0.0.0", server_port=port)



