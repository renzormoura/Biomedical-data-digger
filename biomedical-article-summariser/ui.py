"""Camada de apresentacao (Gradio) declarativa.

As paginas sao descritas por `PageSpec` (dados) e montadas por uma unica fabrica,
eliminando a duplicacao entre Geral e Medicina. Cada botao declara explicitamente
qual builder de prompt usa; `tests/test_ui_spec.py` garante que nenhum builder e
reutilizado por dois botoes da mesma pagina.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import wraps
from typing import Optional

import gradio as gr

import article_services
import contexto_brasil
from account_store import (
    AccountStoreError,
    InvalidCredentialsFormat,
    get_account_store,
    validate_credentials,
)
from config import Settings
from domain import DiggerError
from prompt_builders import (
    build_message_alertas,
    build_message_aplicabilidade_br,
    build_message_checklist,
    build_message_comparacao_literatura,
    build_message_conduta_urgencia,
    build_message_confiabilidade,
    build_message_critica_metodologica,
    build_message_disponibilidade_sus,
    build_message_estatisticas,
    build_message_glossario,
    build_message_impacto_brasil,
    build_message_implicacoes_praticas,
    build_message_lacunas_pesquisa,
    build_message_medicamentos,
    build_message_pico,
    build_message_pontos_chave,
    build_message_populacoes_especiais,
    build_message_questoes_discussao,
    build_message_resumo,
    build_message_resumo_academico,
    build_message_resumo_clinico,
    build_message_resumo_estudante,
    build_message_resumo_introdutorio,
    build_message_resumo_paciente,
    build_message_sumario,
    build_message_vigilancia_sanitaria,
)
from ratelimit import RateLimitExceeded, SlidingWindowLimiter, client_key
from workflow import AnalysisService, ArticleRepository, Filters

MODEL_CHOICES = ["GPT-OSS 20B (Groq)", "GPT-OSS 120B (Groq)", "Qwen 3.6 27B (Groq)", "Qwen 3.8 27B (Groq)", "Llama (local)"]
DEFAULT_MODEL = "GPT-OSS 20B (Groq)"
HISTORY_LIMIT = 10
COMPARISON_TYPES = [
    "Comparação de resultados",
    "Comparação metodológica",
    "Concordâncias e contradições",
    "Comparação de populações",
    "Eficácia",
    "Segurança",
    "Qualidade e limitações",
    "Comparação estatística",
    "Aplicabilidade prática",
    "Evolução do conhecimento",
]
TONE_CHOICES = ["Formal e Técnico", "Direto e Objetivo", "Didático"]
LANGUAGE_CHOICES = ["Português (BR)", "English", "Español"]
DETAIL_CHOICES = ["Resumido", "Completo", "Ultra-detalhado"]

_CSS_PATH = os.path.join(os.path.dirname(__file__), "styles.css")
_CSS_MARKER = "/* === MEDICAL_OVERRIDES === */"


def load_css() -> tuple[str, str]:
    """Retorna (css_base, css_medicina). Sem marcador, a pagina medica usa so o base."""
    with open(_CSS_PATH, encoding="utf-8") as css_file:
        content = css_file.read()
    base, _, overrides = content.partition(_CSS_MARKER)
    return base, base + overrides


# ---------------------------------------------------------------------------
# Especificacao declarativa
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AnalysisButton:
    label: str
    builder: Callable
    output_label: str = ""
    variant: str = "secondary"
    sources: tuple[str, ...] = ()
    check_numbers: bool = True

    @property
    def heading(self) -> str:
        return self.output_label or self.label


@dataclass(frozen=True)
class Section:
    title: str
    rows: tuple[tuple[AnalysisButton, ...], ...]
    is_open: bool = False
    audit_button: bool = False


@dataclass(frozen=True)
class PageSpec:
    key: str
    subtitle: str
    sections: tuple[Section, ...]
    audience_choices: tuple[str, ...]
    focus_choices: tuple[str, ...]
    placeholder: str
    compare_title: str
    compare_placeholder: str
    compare_type_label: str
    compare_button: str
    clinical: bool = False
    elem_id: Optional[str] = None
    title_suffix: str = ""
    help_markdown: str = ""

    def buttons(self) -> list[AnalysisButton]:
        return [button for section in self.sections for row in section.rows for button in row]


def _b(label: str, builder: Callable, output_label: str = "", **kwargs) -> AnalysisButton:
    return AnalysisButton(label, builder, output_label, **kwargs)


GENERAL_HELP = """
**Cole qualquer um destes formatos — o sistema detecta automaticamente:**

**PubMed (PMID):** `33984217` ou `https://pubmed.ncbi.nlm.nih.gov/33984217/`

**PubMed Central (PMCID):** `PMC8234567` ou `https://pmc.ncbi.nlm.nih.gov/articles/PMC8234567/`

**DOI (qualquer área):** `10.1038/s41586-021-03819-2` ou `https://doi.org/10.1038/s41586-021-03819-2`

**arXiv:** `2301.00001` ou `https://arxiv.org/abs/2301.00001`

**OpenAlex:** `W2741809807` ou `https://openalex.org/W2741809807`

**Google Acadêmico:** cole o link da busca, de um cluster ou de um resultado — o sistema encontra o artigo automaticamente

**Qualquer outro link:** páginas de editoras (Springer, Elsevier, Wiley...), repositórios e periódicos funcionam — o sistema extrai o que estiver disponível

💡 **Dica:** Copie a URL da barra do navegador e cole aqui diretamente.
"""

MEDICAL_HELP = """
**Cole qualquer um destes formatos — o sistema detecta automaticamente:**

**PubMed (PMID):** `33984217` ou `https://pubmed.ncbi.nlm.nih.gov/33984217/`

**PubMed Central (PMCID):** `PMC8234567` ou `https://pmc.ncbi.nlm.nih.gov/articles/PMC8234567/`

**DOI:** `10.1038/s41586-021-03819-2` ou `https://doi.org/10.1038/s41586-021-03819-2`

**Google Acadêmico:** cole o link da busca, de um cluster ou de um resultado — o sistema encontra o artigo automaticamente

**Qualquer outro link:** páginas de editoras (Springer, Elsevier, Wiley...), repositórios e periódicos funcionam — o sistema extrai o que estiver disponível

💡 **Dica:** Copie a URL da barra do navegador e cole aqui diretamente.
"""

GENERAL_PAGE = PageSpec(
    key="geral",
    subtitle="Análise científica universal · Europe PMC · arXiv · DOI · OpenAlex",
    sections=(
        Section("Visão Geral", (
            (_b("Sumário", build_message_sumario), _b("Resumo", build_message_resumo)),
            (_b("Pontos-Chave", build_message_pontos_chave), _b("Resumo Introdutório", build_message_resumo_introdutorio)),
        ), is_open=True),
        Section("Análise Científica", (
            (_b("Resumo Acadêmico", build_message_resumo_academico), _b("Crítica Metodológica", build_message_critica_metodologica)),
            (_b("Dados Estatísticos", build_message_estatisticas), _b("PICO", build_message_pico, "Pergunta PICO")),
            (_b("Lacunas de Pesquisa", build_message_lacunas_pesquisa), _b("Comparação Literatura", build_message_comparacao_literatura, "Comparação com Literatura")),
            (_b("Implicações Práticas", build_message_implicacoes_praticas),),
            (_b("Avaliação Crítica", build_message_confiabilidade, variant="primary"),),
        ), audit_button=True),
        Section("Educacional", (
            (_b("Explicação para Iniciantes", build_message_resumo_paciente), _b("Guia para Estudantes", build_message_resumo_estudante)),
            (_b("Questões de Discussão", build_message_questoes_discussao), _b("Glossário de Termos", build_message_glossario)),
        )),
        Section("Aplicações e Impacto", (
            (_b("Impacto na Sociedade", build_message_impacto_brasil),),
        )),
    ),
    audience_choices=("Pesquisador / Acadêmico", "Profissional da área", "Estudante", "Público geral"),
    focus_choices=("Síntese geral", "Metodologia", "Resultados e evidências", "Aplicações práticas", "Contexto brasileiro"),
    placeholder="ex: 33984217 · PMC8234567 · 10.1038/nature · arxiv.org/abs/2301.00001 · qualquer URL (Google Acadêmico, editora, etc.)",
    compare_title="Comparar dois artigos",
    compare_placeholder="PMID, PMCID, DOI, arXiv, OpenAlex ou URL",
    compare_type_label="Tipo de análise",
    compare_button="Comparar Artigos",
    help_markdown=GENERAL_HELP,
)

MEDICAL_PAGE = PageSpec(
    key="medicina",
    subtitle="Pronto-Socorro · Farmacologia · Segurança do Paciente · Contexto Brasileiro",
    sections=(
        Section("Resumos Clínicos", (
            (_b("Resumo Clínico", build_message_resumo_clinico), _b("Resumo Médico", build_message_resumo_academico)),
        ), is_open=True),
        Section("Farmacologia e Protocolos", (
            (_b("Medicamentos / Protocolos", build_message_medicamentos), _b("Populações Especiais", build_message_populacoes_especiais)),
            (_b("Conduta em Urgência", build_message_conduta_urgencia),),
        )),
        Section("Segurança do Paciente", (
            (_b("Alertas e Contraindicações", build_message_alertas), _b("Checklist Pré-Conduta", build_message_checklist)),
            (_b("Confiabilidade do Artigo", build_message_confiabilidade, variant="primary"),),
        ), audit_button=True),
        Section("Contexto BR — Saúde", (
            (
                _b("Disponib. SUS", build_message_disponibilidade_sus, "Disponibilidade no SUS", sources=("bvs", "minsaude"), check_numbers=False),
                _b("Vigilância Sanitária", build_message_vigilancia_sanitaria, sources=("anvisa", "minsaude"), check_numbers=False),
            ),
            (_b("Aplicabilidade BR", build_message_aplicabilidade_br, "Aplicabilidade Brasileira", sources=("minsaude", "anvisa", "bvs"), check_numbers=False),),
        )),
    ),
    audience_choices=("Médico / Especialista", "Residente / Interno", "Estudante de Medicina", "Enfermagem / Farmácia"),
    focus_choices=("Farmacologia", "Estatística", "Segurança", "Metodologia", "Clínico/Prático"),
    placeholder="ex: 33984217 · PMC8234567 · 10.1038/nature12373 · qualquer URL (Google Acadêmico, editora, etc.)",
    compare_title="Comparar dois artigos clínicos",
    compare_placeholder="PMID, PMCID, DOI ou URL do artigo clínico",
    compare_type_label="Tipo de análise clínica",
    compare_button="Comparar Artigos Clínicos",
    clinical=True,
    elem_id="medical-page",
    title_suffix=' <span style="font-size:1rem;color:#94a3b8;font-weight:400">— Medicina</span>',
    help_markdown=MEDICAL_HELP,
)


# ---------------------------------------------------------------------------
# Componentes puros (testaveis sem Gradio)
# ---------------------------------------------------------------------------
def update_history(article_id: str, history: list[list[str]], repository: ArticleRepository) -> list[list[str]]:
    """Insere o artigo consultado no topo do historico (sem duplicar, max HISTORY_LIMIT)."""
    key = (article_id or "").strip()
    article = repository.peek(key)
    if article is None or any(row[0] == key for row in history):
        return history
    title = article.title[:60] + "..." if len(article.title) > 60 else article.title
    return ([[key, title]] + history)[:HISTORY_LIMIT]


def history_rows(history: Sequence[Sequence[str]]) -> list[list[str]]:
    return [list(row) for row in history] or [["—", "Nenhum artigo consultado ainda"]]


def verification_annex_md(source_keys: Sequence[str]) -> str:
    """Anexo com status de alcancabilidade das fontes oficiais citadas.

    Falha de rede vira alerta explicito, nunca afirmacao silenciosa.
    """
    catalog = contexto_brasil.VERIFICATION_SOURCES
    urls = [catalog[k]["catalog_url"] for k in source_keys if k in catalog]
    by_url = {v["catalog_url"]: v for v in catalog.values()}
    results = contexto_brasil.get_verificacao().verificar_fontes(urls)
    lines = [
        "\n\n---",
        "> **Anexo de verificação externa** — status das fontes oficiais de contexto:",
    ]
    for result in results:
        source = by_url.get(result.get("url", ""), {})
        name = source.get("name", result.get("url", ""))
        revised = source.get("updated", "—")
        if result.get("status") == "ok":
            lines.append(f"> - 🟢 **{name}** — acessível · revisão {revised} · {result.get('url', '')}")
        else:
            lines.append(
                f"> - 🔴 **{name}** — **não verificável** ({result.get('motivo', 'erro')}) · {result.get('url', '')}"
            )
    lines.append(
        "> ⚠️ Afirmações contextuais sobre uma fonte 🔴 devem ser tratadas como "
        "**não verificáveis** até a fonte voltar a responder."
    )
    return "\n".join(lines)


def _gradio_errors(function):
    """Converte erros esperados do dominio em `gr.Error` com mensagem segura."""

    @wraps(function)
    def wrapper(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except DiggerError as error:
            raise gr.Error(error.user_message) from error

    return wrapper


def _client_id(request: Optional[gr.Request], settings: Settings) -> str:
    if request is None:
        return "local"
    peer = request.client.host if request.client else None
    return client_key(dict(request.headers), peer, settings.trusted_proxy_hops)


def _theme() -> gr.themes.Base:
    return gr.themes.Base(
        primary_hue=gr.themes.colors.blue,
        neutral_hue=gr.themes.colors.slate,
        font=[gr.themes.GoogleFont("Inter"), "system-ui", "sans-serif"],
        font_mono=[gr.themes.GoogleFont("JetBrains Mono"), "monospace"],
    )


def _header(subtitle: str, title_suffix: str = "", toggle_id: str = "") -> str:
    toggle = ""
    if toggle_id:
        toggle = f"""
        <button class="theme-toggle" id="{toggle_id}"
          onclick="(function(){{
            const c=this.closest('.gradio-container');
            c.classList.toggle('light-theme');
            this.textContent=c.classList.contains('light-theme')?'🌙 Escuro':'☀️ Claro';
          }}).call(this)">☀️ Claro</button>"""
    return f"""
        <div class="app-header">
          <h1><span class="accent">Biomedical</span> Data Digger{title_suffix}</h1>
          <p class="app-subtitle">{subtitle}</p>
        </div>{toggle}
        """


# ---------------------------------------------------------------------------
# Fabrica de paginas
# ---------------------------------------------------------------------------
def build_analysis_page(spec: PageSpec, service: AnalysisService, repository: ArticleRepository,
                        settings: Settings, css: str) -> gr.Blocks:
    kwargs = {"elem_id": spec.elem_id} if spec.elem_id else {}
    with gr.Blocks(theme=_theme(), css=css, **kwargs) as page:
        gr.HTML(_header(spec.subtitle, spec.title_suffix, f"theme-toggle-btn-{spec.key}"))
        session_history = gr.State([])
        last_response = gr.State("")

        with gr.Row(equal_height=False):
            with gr.Column(scale=1, min_width=320):
                with gr.Group():
                    article_id = gr.Textbox(label="ID ou URL do artigo", placeholder=spec.placeholder)
                    model_choice = gr.Dropdown(choices=MODEL_CHOICES, value=DEFAULT_MODEL, label="Modelo de linguagem")

                with gr.Accordion(spec.compare_title, open=False):
                    compare_a = gr.Textbox(label="Artigo A — ID ou URL", placeholder=spec.compare_placeholder)
                    compare_b = gr.Textbox(label="Artigo B — ID ou URL", placeholder=spec.compare_placeholder)
                    compare_type = gr.Dropdown(choices=COMPARISON_TYPES, value=COMPARISON_TYPES[0], label=spec.compare_type_label)
                    compare_button = gr.Button(spec.compare_button, variant="primary")

                with gr.Accordion("Como encontrar o ID ou URL?", open=False):
                    gr.Markdown(spec.help_markdown)

                with gr.Accordion("Histórico da sessão", open=False):
                    history_display = gr.Dataframe(
                        headers=["ID", "Título"], datatype=["str", "str"], interactive=False, label=None, wrap=True
                    )

                with gr.Accordion("Personalização (opcional)", open=False):
                    gr.Markdown("<small>Filtros opcionais — sem seleção, cada botão usa seu padrão.</small>")
                    f_publico = gr.Radio(choices=list(spec.audience_choices), value=None, label="Público-alvo")
                    f_tom = gr.Radio(choices=TONE_CHOICES, value=None, label="Tom")
                    f_idioma = gr.Radio(choices=LANGUAGE_CHOICES, value=None, label="Idioma")
                    f_detalhe = gr.Radio(choices=DETAIL_CHOICES, value=None, label="Detalhe")
                    f_foco = gr.Radio(choices=list(spec.focus_choices), value=None, label="Foco")
                    clear_button = gr.Button("↺  Limpar filtros", size="sm", variant="secondary")

                analysis_buttons: list[tuple[AnalysisButton, gr.Button]] = []
                audit_button: Optional[gr.Button] = None
                for section in spec.sections:
                    with gr.Accordion(section.title, open=section.is_open):
                        for row in section.rows:
                            with gr.Row():
                                for button in row:
                                    analysis_buttons.append((button, gr.Button(button.label, variant=button.variant)))
                        if section.audit_button:
                            audit_button = gr.Button("Auditoria da Resposta", variant="primary")

            with gr.Column(scale=2, min_width=480):
                output_box = gr.Markdown(
                    value="*Selecione um tipo de análise e clique em um botão para começar.*",
                    elem_classes=["output-panel"],
                )

        filter_inputs = [f_publico, f_tom, f_idioma, f_detalhe, f_foco]
        analysis_inputs = [article_id, model_choice, *filter_inputs, session_history]
        analysis_outputs = [output_box, session_history, history_display, last_response]

        clear_button.click(fn=lambda: (None,) * 5, inputs=[], outputs=filter_inputs)

        def make_handler(button: AnalysisButton):
            @_gradio_errors
            def handler(aid, model, publico, tom, idioma, detalhe, foco, history, request: gr.Request):
                client = _client_id(request, settings)
                filters = Filters(publico or "", tom or "", idioma or "", detalhe or "", foco or "")
                result = service.analyze(
                    aid, model, button.builder, button.heading, filters,
                    client_id=client, clinical=spec.clinical, check_numbers=button.check_numbers,
                )
                if button.sources:
                    try:
                        result += verification_annex_md(button.sources)
                    except Exception:
                        result += (
                            "\n\n---\n> ⚠️ **Verificação externa indisponível no momento.** "
                            "Trate qualquer afirmação contextual como **não verificável**."
                        )
                new_history = update_history(aid, history, repository)
                return result, new_history, gr.update(value=history_rows(new_history)), result

            return handler

        for button, component in analysis_buttons:
            component.click(fn=make_handler(button), inputs=analysis_inputs, outputs=analysis_outputs, show_progress="full")

        if audit_button is not None:
            @_gradio_errors
            def audit_handler(aid, model, previous, request: gr.Request):
                return service.audit(aid, model, previous, client_id=_client_id(request, settings))

            audit_button.click(
                fn=audit_handler, inputs=[article_id, model_choice, last_response],
                outputs=output_box, show_progress="full",
            )

        @_gradio_errors
        def compare_handler(a, b, analysis, model, request: gr.Request):
            return service.compare(
                a, b, analysis, model, medical_context=spec.clinical, client_id=_client_id(request, settings)
            )

        compare_button.click(
            fn=compare_handler, inputs=[compare_a, compare_b, compare_type, model_choice],
            outputs=output_box, show_progress="full",
        )
    return page


def build_search_page(css: str) -> gr.Blocks:
    areas = list(article_services.AREA_KEYWORDS)
    with gr.Blocks(theme=_theme(), css=css) as page:
        gr.HTML(_header("Busca por palavra-chave · artigos prioritários e confiáveis"))
        with gr.Row(equal_height=False):
            with gr.Column(scale=1, min_width=320):
                keyword = gr.Textbox(
                    label="Palavra-chave ou tema de pesquisa",
                    placeholder="ex: diabetes mellitus, machine learning, sepsis, immunotherapy",
                )
                area = gr.Dropdown(choices=areas, value="Todas", label="Área de foco")
                limit = gr.Dropdown(choices=["3", "5", "8"], value="5", label="Quantidade de recomendações")
                search_button = gr.Button("Buscar artigos relevantes", variant="primary")
                gr.Markdown(
                    "<small>A busca combina impacto bibliográfico, atualidade, completude dos metadados "
                    "e cobertura das fontes consultadas.</small>"
                )
            with gr.Column(scale=2, min_width=480):
                results_table = gr.Dataframe(
                    headers=["Título", "Revista", "Ano", "PMID", "Fonte", "Relevância bibliográfica"],
                    datatype=["str"] * 6, interactive=False, wrap=True, label="Artigos recomendados",
                )
                summary_box = gr.Markdown(value="*Aguardando pesquisa.*")

        def run_search(query: str, selected_area: str, page_size: str):
            if not query or not query.strip():
                raise gr.Error("Informe uma palavra-chave ou tema para buscar artigos relevantes.")
            try:
                results = article_services.search_reliable_articles(
                    query, limit=int(page_size or 5), area=selected_area or "Todas"
                )
            except RuntimeError as error:
                raise gr.Error(str(error)) from error
            if not results:
                raise gr.Error(
                    "Nenhum artigo foi encontrado para esta busca com o filtro selecionado. "
                    "Tente outra palavra-chave ou área."
                )
            return format_search_rows(results), format_search_summary(results)

        search_button.click(fn=run_search, inputs=[keyword, area, limit], outputs=[results_table, summary_box], show_progress="full")
    return page


def _score_icon(score: float) -> str:
    return "🟢" if score >= 0.90 else "🟡" if score >= 0.75 else "🟠"


def format_search_rows(results: Sequence[dict]) -> list[list[str]]:
    return [
        [
            item["title"], item["journal"], str(item["year"]), item["pmid"], item["source"],
            f"{item['reliability']} · score {item['reliability_score']:.2f}",
        ]
        for item in results
    ]


def format_search_summary(results: Sequence[dict]) -> str:
    return "\n\n".join(
        f"### {_score_icon(item['reliability_score'])} {idx}. [{item['title']}]({item['url']})\n"
        f"- Revista: {item['journal']} ({item['year']})\n"
        f"- PMID: [{item['pmid']}]({item['url']})\n"
        f"- Relevância bibliográfica: {item['reliability']} (score {item['reliability_score']:.2f})"
        for idx, item in enumerate(results, start=1)
    )


def build_accounts_page(css: str, settings: Settings) -> gr.Blocks:
    auth_limiter = SlidingWindowLimiter(settings.login_attempts_per_minute, window=60.0)

    def throttle(request: Optional[gr.Request]) -> None:
        try:
            auth_limiter.check(_client_id(request, settings))
        except RateLimitExceeded as error:
            raise gr.Error(str(error)) from error

    with gr.Blocks(theme=_theme(), css=css) as page:
        gr.HTML(_header("Contas e acesso do usuário"))
        logged_user = gr.State("")
        status_box = gr.Markdown(value="*Nenhum usuário logado.*")
        with gr.Row(equal_height=False):
            with gr.Column(scale=1, min_width=320):
                email = gr.Textbox(label="E-mail", placeholder="seuemail@exemplo.com")
                password = gr.Textbox(label="Senha", placeholder="Digite sua senha", type="password")
                with gr.Row():
                    create_button = gr.Button("Criar conta", variant="primary")
                    login_button = gr.Button("Entrar", variant="secondary")
                guest_button = gr.Button("Entrar como visitante", variant="secondary")
                logout_button = gr.Button("Sair da conta", variant="stop")
            with gr.Column(scale=2, min_width=480):
                account_info = gr.Markdown(value="## Conta\nCadastre-se para guardar sua sessão local do app.")

        def create_account(address: str, secret: str, request: gr.Request):
            throttle(request)
            try:
                normalized, secret = validate_credentials(address, secret)
                created = get_account_store().create_user(normalized, secret)
            except (InvalidCredentialsFormat, AccountStoreError) as error:
                raise gr.Error(str(error)) from error
            if not created:
                raise gr.Error("Este e-mail já está cadastrado.")
            return f"Conta criada com sucesso para {normalized}.", "*Nenhum usuário logado.*"

        def login(address: str, secret: str, request: gr.Request):
            throttle(request)
            try:
                normalized, secret = validate_credentials(address, secret)
                ok = get_account_store().authenticate(normalized, secret)
            except InvalidCredentialsFormat as error:
                raise gr.Error("E-mail ou senha inválidos.") from error
            except AccountStoreError as error:
                raise gr.Error(str(error)) from error
            if not ok:
                raise gr.Error("E-mail ou senha inválidos.")
            return f"Usuário logado: {normalized}", normalized

        create_button.click(fn=create_account, inputs=[email, password], outputs=[account_info, status_box], show_progress="full")
        login_button.click(fn=login, inputs=[email, password], outputs=[account_info, logged_user], show_progress="full")
        guest_button.click(fn=lambda: ("Acesso como visitante ativo. Nenhuma conta foi criada.", "visitor"), inputs=[], outputs=[account_info, logged_user])
        logout_button.click(fn=lambda: ("*Nenhum usuário logado.*", ""), inputs=[], outputs=[account_info, logged_user], show_progress="full")
        gr.Markdown(
            "<small>O cadastro usa armazenamento persistente quando o banco de produção está configurado. "
            "O acesso como visitante não cria conta.</small>"
        )
    return page


def build_app(service: AnalysisService, repository: ArticleRepository, settings: Settings) -> gr.TabbedInterface:
    base_css, medical_css = load_css()
    pages = [
        build_analysis_page(GENERAL_PAGE, service, repository, settings, base_css),
        build_analysis_page(MEDICAL_PAGE, service, repository, settings, medical_css),
        build_search_page(base_css),
        build_accounts_page(base_css, settings),
    ]
    return gr.TabbedInterface(
        pages,
        tab_names=["☰  Geral", "⚕  Medicina", "🔎  Pesquisa por palavra-chave", "👤  Contas"],
        title="Biomedical Data Digger",
    )
