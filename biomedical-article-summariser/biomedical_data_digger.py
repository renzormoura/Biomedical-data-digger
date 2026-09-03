import os
from typing import List, Dict

import gradio as gr

import article_services
import llm_service
from prompt_builders import (
    build_dynamic_sys_prompt,
    build_message_alertas,
    build_message_aplicabilidade_br,
    build_message_comparacao_literatura,
    build_message_checklist,
    build_message_confiabilidade,
    build_message_conduta_urgencia,
    build_message_critica_metodologica,
    build_message_disponibilidade_sus,
    build_message_estatisticas,
    build_message_resumo_estudante,
    build_message_glossario,
    build_message_impacto_brasil,
    build_message_implicacoes_praticas,
    build_message_lacunas_pesquisa,
    build_message_medicamentos,
    build_message_pico,
    build_message_populacoes_especiais,
    build_message_pontos_chave,
    build_message_questoes_discussao,
    build_message_resumo,
    build_message_resumo_academico,
    build_message_resumo_clinico,
    build_message_resumo_introdutorio,
    build_message_resumo_paciente,
    build_message_sumario,
    build_message_vigilancia_sanitaria,
)
from llm_service import USE_GROQ

CSS_PATH = os.path.join(os.path.dirname(__file__), "styles.css")
with open(CSS_PATH, encoding="utf-8") as css_file:
  CUSTOM_CSS, MEDICAL_OVERRIDES = css_file.read().split(
    "/* === MEDICAL_OVERRIDES === */", maxsplit=1
  )
MEDICAL_CSS = CUSTOM_CSS + MEDICAL_OVERRIDES

get_cached_article = article_services.get_cached_article
set_cached_article = article_services.set_cached_article





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
            article_title, abstract_text, fonte = article_services.resolve_article(article_id)
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
        summary = llm_service.generate_response(messages, model)
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

# INTERFACE GRADIO
# ===========================================================================

# ===========================================================================
# TEMA VISUAL CUSTOMIZADO
# ===========================================================================

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
              filtro_publico = gr.Radio(choices=["Pesquisador / Acadêmico", "Profissional da área", "Estudante", "Público geral"], value=None, label="Público-alvo")
              filtro_tom     = gr.Radio(choices=["Formal e Técnico", "Direto e Objetivo", "Didático"], value=None, label="Tom")
              filtro_idioma  = gr.Radio(choices=["Português (BR)", "English", "Español"], value=None, label="Idioma")
              filtro_detalhe = gr.Radio(choices=["Resumido", "Completo", "Ultra-detalhado"], value=None, label="Detalhe")
              filtro_foco    = gr.Radio(choices=["Síntese geral", "Metodologia", "Resultados e evidências", "Aplicações práticas", "Contexto brasileiro"], value=None, label="Foco")
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
        css=MEDICAL_CSS,
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
