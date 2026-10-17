"""Especificacao declarativa das abas de analise (dados puros, sem Gradio).

Cada botao declara o builder de prompt que usa. `tests/test_ui_spec.py` garante que
nenhum builder se repete dentro da mesma aba e que nenhum builder fica sem uso.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from typing import Union

import prompt_builders as pb

GROUP_ORDER = ("Geral", "Saúde", "Exatas e Tecnologia", "Sociedade e Ambiente")
MODEL_CHOICES = ("GPT-OSS 20B (Groq)", "GPT-OSS 120B (Groq)", "Qwen 3.6 27B (Groq)", "Qwen 3.8 27B (Groq)", "Llama (local)")
DEFAULT_MODEL = "GPT-OSS 20B (Groq)"
COMPARISON_TYPES = (
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
)
TONE_CHOICES = ("Formal e Técnico", "Direto e Objetivo", "Didático")
LANGUAGE_CHOICES = ("Português (BR)", "English", "Español")
DETAIL_CHOICES = ("Resumido", "Completo", "Ultra-detalhado")


# Botoes de baixo risco (reformulam o texto sem julgar nem extrair dados clinicos): raciocinio
# reduzido corta ~50% dos tokens de saida. Medicao real: scripts/measure_tokens.py.
LOW_REASONING: dict[Callable, str] = {
    pb.build_message_sumario: "low",
    pb.build_message_pontos_chave: "low",
    pb.build_message_resumo: "low",
    pb.build_message_resumo_introdutorio: "low",
    pb.build_message_resumo_paciente: "low",
    pb.build_message_resumo_estudante: "low",
    pb.build_message_glossario: "low",
    pb.build_message_questoes_discussao: "low",
    pb.build_message_flashcards: "low",
    pb.build_message_mapa_conceitos: "low",
    pb.build_message_roteiro_seminario: "low",
    pb.build_message_pergunta_pesquisa: "low",
    pb.build_message_estrategia_busca: "low",
}


def slugify(text: str) -> str:
    """Identificador estavel e ASCII para uso em URLs e atributos HTML."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


@dataclass(frozen=True)
class AnalysisButton:
    label: str
    builder: Callable
    output_label: str = ""
    variant: str = "secondary"
    sources: tuple[str, ...] = ()
    check_numbers: bool = True
    # Esforco de raciocinio do modelo (low/medium/high). None = padrao do provedor. So e
    # reduzido em botoes que apenas reformulam o texto; nunca em abas clinicas (ver web.py).
    reasoning_effort: str | None = None
    # Tema (extraction.CUE_KINDS) que o abstract precisa trazer. Sem ele a analise e bloqueada
    # sem chamar o modelo, em vez de a IA preencher a lacuna.
    requires: str | None = None

    @property
    def heading(self) -> str:
        return self.output_label or self.label

    @property
    def id(self) -> str:
        return slugify(self.label)


@dataclass(frozen=True)
class CitationButton:
    """Botao que gera referencia bibliografica sem LLM (ABNT, APA ou Vancouver)."""

    style: str

    @property
    def label(self) -> str:
        return self.style

    @property
    def id(self) -> str:
        return slugify(self.style)


@dataclass(frozen=True)
class ExtractButton:
    """Botao SEM IA: copia trechos do abstract (`overview`, `dose`, `conduta`, `interacoes`, `reacoes`)."""

    label: str
    kind: str = "overview"
    variant: str = "secondary"

    @property
    def id(self) -> str:
        return slugify(self.label)


AnyButton = Union[AnalysisButton, CitationButton, ExtractButton]


@dataclass(frozen=True)
class Section:
    title: str
    rows: tuple[tuple[AnyButton, ...], ...]
    is_open: bool = False
    audit_button: bool = False


@dataclass(frozen=True)
class PageSpec:
    key: str
    tab_name: str
    subtitle: str
    sections: tuple[Section, ...]
    audience_choices: tuple[str, ...]
    focus_choices: tuple[str, ...]
    placeholder: str
    help_markdown: str
    compare_title: str = "Comparar dois artigos"
    compare_placeholder: str = "PMID, PMCID, DOI, arXiv, OpenAlex ou URL"
    compare_type_label: str = "Tipo de análise"
    compare_button: str = "Comparar Artigos"
    clinical: bool = False
    elem_id: str | None = None
    title_suffix: str = ""
    group: str = ""

    @property
    def title(self) -> str:
        """Nome da aba sem o emoji/simbolo inicial."""
        return re.sub(r"^[^\w]+", "", self.tab_name).strip()

    def buttons(self) -> list[AnalysisButton]:
        return [
            button
            for section in self.sections
            for row in section.rows
            for button in row
            if isinstance(button, AnalysisButton)
        ]

    def extract_buttons(self) -> list[ExtractButton]:
        return [
            button
            for section in self.sections
            for row in section.rows
            for button in row
            if isinstance(button, ExtractButton)
        ]

    def citation_buttons(self) -> list[CitationButton]:
        return [
            button
            for section in self.sections
            for row in section.rows
            for button in row
            if isinstance(button, CitationButton)
        ]


def _b(label: str, builder: Callable, output_label: str = "", **kwargs) -> AnalysisButton:
    kwargs.setdefault("reasoning_effort", LOW_REASONING.get(builder))
    return AnalysisButton(label, builder, output_label, **kwargs)


def _suffix(text: str) -> str:
    return f' <span style="font-size:1rem;color:#94a3b8;font-weight:400">— {text}</span>'


GENERAL_HELP = """
**Cole qualquer um destes formatos — o sistema detecta automaticamente:**

**PubMed (PMID):** `33984217` ou `https://pubmed.ncbi.nlm.nih.gov/33984217/`

**PubMed Central (PMCID):** `PMC8234567` ou `https://pmc.ncbi.nlm.nih.gov/articles/PMC8234567/`

**DOI (qualquer área):** `10.1038/s41586-021-03819-2` ou `https://doi.org/10.1038/s41586-021-03819-2`

**arXiv:** `2301.00001` ou `https://arxiv.org/abs/2301.00001`

**OpenAlex:** `W2741809807` ou `https://openalex.org/W2741809807`

**Google Acadêmico:** cole o link da busca, de um cluster ou de um resultado — o sistema encontra o artigo automaticamente

**Qualquer outro link:** páginas de editoras (Springer, Elsevier, Wiley...), repositórios e periódicos funcionam — o sistema extrai o que estiver disponível

**Dica:** Copie a URL da barra do navegador e cole aqui diretamente.
"""

MEDICAL_HELP = """
**Cole qualquer um destes formatos — o sistema detecta automaticamente:**

**PubMed (PMID):** `33984217` ou `https://pubmed.ncbi.nlm.nih.gov/33984217/`

**PubMed Central (PMCID):** `PMC8234567` ou `https://pmc.ncbi.nlm.nih.gov/articles/PMC8234567/`

**DOI:** `10.1038/s41586-021-03819-2` ou `https://doi.org/10.1038/s41586-021-03819-2`

**Google Acadêmico:** cole o link da busca, de um cluster ou de um resultado — o sistema encontra o artigo automaticamente

**Qualquer outro link:** páginas de editoras (Springer, Elsevier, Wiley...), repositórios e periódicos funcionam — o sistema extrai o que estiver disponível

**Dica:** Copie a URL da barra do navegador e cole aqui diretamente.
"""

ACADEMIC_HELP = (
    GENERAL_HELP
    + """
**Referências (ABNT, APA, Vancouver):** use um **DOI, PMID ou PMCID**. A referência vem do registro oficial
(Crossref ou Europe PMC) e é formatada por código, **sem IA**, então não há risco de autor ou ano inventado.

**Uso responsável:** esta aba ajuda a entender, fichar e citar. Ela não substitui a leitura do artigo
completo nem a sua autoria no trabalho.
"""
)

def _no_ai_section() -> Section:
    return Section(
        "Direto do artigo (sem IA)",
        ((ExtractButton("Extrair do artigo", "overview", variant="primary"),),),
        is_open=True,
    )


_GENERIC_PLACEHOLDER = "ex: 33984217 · PMC8234567 · 10.1038/nature · arxiv.org/abs/2301.00001 · qualquer URL"

GENERAL_PAGE = PageSpec(
    key="geral",
    group="Geral",
    tab_name="Geral",
    subtitle="Análise científica universal · Europe PMC · arXiv · DOI · OpenAlex",
    sections=(
        _no_ai_section(),
        Section("Visão Geral", (
            (_b("Sumário", pb.build_message_sumario), _b("Resumo", pb.build_message_resumo)),
            (_b("Pontos-Chave", pb.build_message_pontos_chave), _b("Resumo Introdutório", pb.build_message_resumo_introdutorio)),
        ), is_open=True),
        Section("Análise Científica", (
            (_b("Resumo Acadêmico", pb.build_message_resumo_academico), _b("Crítica Metodológica", pb.build_message_critica_metodologica)),
            (_b("Dados Estatísticos", pb.build_message_estatisticas), _b("PICO", pb.build_message_pico, "Pergunta PICO")),
            (_b("Lacunas de Pesquisa", pb.build_message_lacunas_pesquisa), _b("Comparação Literatura", pb.build_message_comparacao_literatura, "Comparação com Literatura")),
            (_b("Implicações Práticas", pb.build_message_implicacoes_praticas),),
            (_b("Avaliação Crítica", pb.build_message_confiabilidade, variant="primary"),),
        ), audit_button=True),
        Section("Aplicações e Impacto", (
            (_b("Impacto na Sociedade", pb.build_message_impacto_brasil),),
        )),
    ),
    audience_choices=("Pesquisador / Acadêmico", "Profissional da área", "Estudante", "Público geral"),
    focus_choices=("Síntese geral", "Metodologia", "Resultados e evidências", "Aplicações práticas", "Contexto brasileiro"),
    placeholder=_GENERIC_PLACEHOLDER + " (Google Acadêmico, editora, etc.)",
    help_markdown=GENERAL_HELP,
)

ACADEMIC_PAGE = PageSpec(
    key="academico",
    group="Geral",
    tab_name="Acadêmico",
    subtitle="Estudar · Escrever · Referenciar · Apresentar — para estudantes de qualquer curso",
    sections=(
        _no_ai_section(),
        Section("Entender o artigo", (
            (_b("Sumário", pb.build_message_sumario), _b("Pontos-Chave", pb.build_message_pontos_chave)),
            (_b("Explicação para Iniciantes", pb.build_message_resumo_paciente), _b("Guia para Estudantes", pb.build_message_resumo_estudante)),
        ), is_open=True),
        Section("Estudar", (
            (_b("Questões de Discussão", pb.build_message_questoes_discussao), _b("Glossário de Termos", pb.build_message_glossario)),
            (_b("Flashcards", pb.build_message_flashcards), _b("Múltipla Escolha", pb.build_message_questoes_multipla_escolha, "Questões de Múltipla Escolha")),
            (_b("Mapa de Conceitos", pb.build_message_mapa_conceitos),),
        )),
        Section("Escrever (TCC, seminário)", (
            (_b("Fichamento", pb.build_message_fichamento), _b("Roteiro de Resenha", pb.build_message_resenha_critica, "Roteiro de Resenha Crítica")),
            (_b("Como Citar no Texto", pb.build_message_como_citar), _b("Justificativa de Pesquisa", pb.build_message_justificativa_pesquisa)),
        )),
        Section("Referências (sem IA)", (
            (CitationButton("ABNT"), CitationButton("APA"), CitationButton("Vancouver")),
        )),
        Section("Pesquisar", (
            (_b("Pergunta e Descritores", pb.build_message_pergunta_pesquisa), _b("Estratégia de Busca", pb.build_message_estrategia_busca)),
        )),
        Section("Apresentar", (
            (_b("Roteiro de Seminário", pb.build_message_roteiro_seminario),),
        ), audit_button=True),
    ),
    audience_choices=("Graduação (iniciante)", "Graduação (avançado)", "Pós-graduação"),
    focus_choices=("Estudo e revisão", "Escrita acadêmica", "Metodologia", "Síntese geral"),
    placeholder=_GENERIC_PLACEHOLDER,
    help_markdown=ACADEMIC_HELP,
    title_suffix=_suffix("Acadêmico"),
)

def _medical_page(generative_clinical: bool) -> PageSpec:
    """Aba Medicina. Por padrao, dose, conduta, interacoes e reacoes adversas sao EXTRATIVAS (trechos
    copiados do resumo, sem IA). `generative_clinical=True` restaura as versoes geradas por IA, cada
    uma bloqueada quando o resumo nao traz o tema; so deve ser ligado apos validacao por especialista."""
    if generative_clinical:
        pharmacology = Section("Farmacologia e Protocolos", (
            (_b("Medicamentos / Protocolos", pb.build_message_medicamentos, requires="dose"),
             _b("Populações Especiais", pb.build_message_populacoes_especiais, requires="populacoes")),
            (_b("Conduta em Urgência", pb.build_message_conduta_urgencia, requires="conduta"),),
            (_b("Interações Medicamentosas", pb.build_message_interacoes_medicamentosas, requires="interacoes"),
             _b("Reações Adversas", pb.build_message_reacoes_adversas, requires="reacoes")),
        ))
    else:
        pharmacology = Section("Farmacologia e Protocolos", (
            (ExtractButton("Doses e protocolos (trechos)", "dose"),
             _b("Populações Especiais", pb.build_message_populacoes_especiais, requires="populacoes")),
            (ExtractButton("Condutas e recomendações (trechos)", "conduta"),),
            (ExtractButton("Interações medicamentosas (trechos)", "interacoes"),
             ExtractButton("Reações adversas (trechos)", "reacoes")),
        ))
    return PageSpec(
        key="medicina",
        group="Saúde",
        tab_name="Medicina",
        subtitle="Pronto-Socorro · Farmacologia · Segurança do Paciente · Contexto Brasileiro",
        sections=(
            _no_ai_section(),
            Section("Resumos Clínicos", (
                (_b("Resumo Clínico", pb.build_message_resumo_clinico), _b("Resumo Médico", pb.build_message_resumo_academico)),
                (_b("PICO", pb.build_message_pico, "Pergunta PICO"),),
            ), is_open=True),
            pharmacology,
            Section("Evidência e Segurança", (
                (_b("Crítica Metodológica", pb.build_message_critica_metodologica), _b("Dados Estatísticos", pb.build_message_estatisticas)),
                (_b("Alertas e Contraindicações", pb.build_message_alertas, requires="alertas"), _b("Checklist Pré-Conduta", pb.build_message_checklist)),
                (_b("Confiabilidade do Artigo", pb.build_message_confiabilidade, variant="primary"),),
            ), audit_button=True),
            Section("Contexto BR — Saúde", (
                (
                    _b("Disponib. SUS", pb.build_message_disponibilidade_sus, "Disponibilidade no SUS", sources=("bvs", "minsaude"), check_numbers=False),
                    _b("Vigilância Sanitária", pb.build_message_vigilancia_sanitaria, sources=("anvisa", "minsaude"), check_numbers=False),
                ),
                (_b("Aplicabilidade BR", pb.build_message_aplicabilidade_br, "Aplicabilidade Brasileira", sources=("minsaude", "anvisa", "bvs"), check_numbers=False),),
            )),
        ),
        audience_choices=("Médico / Especialista", "Residente / Interno", "Estudante de Medicina", "Enfermagem / Farmácia"),
        focus_choices=("Farmacologia", "Estatística", "Segurança", "Metodologia", "Clínico/Prático"),
        placeholder="ex: 33984217 · PMC8234567 · 10.1038/nature12373 · qualquer URL (Google Acadêmico, editora, etc.)",
        help_markdown=MEDICAL_HELP,
        compare_title="Comparar dois artigos clínicos",
        compare_placeholder="PMID, PMCID, DOI ou URL do artigo clínico",
        compare_type_label="Tipo de análise clínica",
        compare_button="Comparar Artigos Clínicos",
        clinical=True,
        elem_id="medical-page",
        title_suffix=_suffix("Medicina"),
    )


MEDICAL_PAGE = _medical_page(generative_clinical=False)
MEDICAL_PAGE_GENERATIVE = _medical_page(generative_clinical=True)

ENVIRONMENTAL_PAGE = PageSpec(
    key="ambiental",
    group="Sociedade e Ambiente",
    tab_name="Ambiental",
    subtitle="Impacto ambiental · Poluentes · Mitigação · Contexto regulatório brasileiro",
    sections=(
        _no_ai_section(),
        Section("Visão Geral", (
            (_b("Sumário", pb.build_message_sumario), _b("Pontos-Chave", pb.build_message_pontos_chave)),
        ), is_open=True),
        Section("Impacto", (
            (_b("Impacto Ambiental", pb.build_message_impacto_ambiental), _b("Poluentes e Exposição", pb.build_message_poluentes_exposicao)),
            (_b("Ecossistemas e Populações", pb.build_message_ecossistemas_populacoes),),
        )),
        Section("Mitigação e Política", (
            (_b("Medidas de Mitigação", pb.build_message_medidas_mitigacao), _b("Indicadores e ODS", pb.build_message_indicadores_ods, sources=("ods",))),
            (_b("Contexto Regulatório", pb.build_message_contexto_regulatorio_ambiental, "Contexto Regulatório Ambiental", sources=("conama", "ibama", "mma")),),
        )),
        Section("Evidência", (
            (_b("Crítica Metodológica", pb.build_message_critica_metodologica), _b("Dados Estatísticos", pb.build_message_estatisticas)),
            (_b("Lacunas de Pesquisa", pb.build_message_lacunas_pesquisa),),
        ), audit_button=True),
    ),
    audience_choices=("Pesquisador / Acadêmico", "Gestor / Técnico ambiental", "Estudante", "Público geral"),
    focus_choices=("Impacto ambiental", "Mitigação e gestão", "Metodologia", "Contexto brasileiro"),
    placeholder=_GENERIC_PLACEHOLDER,
    help_markdown=GENERAL_HELP,
    title_suffix=_suffix("Ambiental"),
)

PUBLIC_HEALTH_PAGE = PageSpec(
    key="saude_publica",
    group="Saúde",
    tab_name="Saúde Pública",
    subtitle="Epidemiologia · Vigilância · SUS · Políticas de saúde",
    sections=(
        _no_ai_section(),
        Section("Visão Geral", (
            (_b("Sumário", pb.build_message_sumario), _b("Pontos-Chave", pb.build_message_pontos_chave)),
        ), is_open=True),
        Section("Epidemiologia", (
            (_b("Desenho Epidemiológico", pb.build_message_desenho_epidemiologico), _b("Medidas de Associação", pb.build_message_medidas_associacao)),
            (_b("Vieses e Confusão", pb.build_message_vieses_confusao),),
        )),
        Section("SUS e Vigilância", (
            (
                _b("Disponib. SUS", pb.build_message_disponibilidade_sus, "Disponibilidade no SUS", sources=("bvs", "minsaude"), check_numbers=False),
                _b("Vigilância Sanitária", pb.build_message_vigilancia_sanitaria, sources=("anvisa", "minsaude"), check_numbers=False),
            ),
            (
                _b("Aplicabilidade BR", pb.build_message_aplicabilidade_br, "Aplicabilidade Brasileira", sources=("minsaude", "anvisa", "bvs"), check_numbers=False),
                _b("Implicações para Políticas", pb.build_message_implicacoes_praticas),
            ),
        )),
        Section("Evidência", (
            (_b("Crítica Metodológica", pb.build_message_critica_metodologica), _b("Dados Estatísticos", pb.build_message_estatisticas)),
        ), audit_button=True),
    ),
    audience_choices=("Profissional de saúde pública", "Pesquisador / Acadêmico", "Estudante", "Público geral"),
    focus_choices=("Epidemiologia", "Vigilância e políticas", "Metodologia", "Contexto brasileiro"),
    placeholder=_GENERIC_PLACEHOLDER,
    help_markdown=MEDICAL_HELP,
    compare_title="Comparar dois estudos",
    compare_button="Comparar Estudos",
    clinical=True,
    title_suffix=_suffix("Saúde Pública"),
)

TECHNOLOGY_PAGE = PageSpec(
    key="tecnologia",
    group="Exatas e Tecnologia",
    tab_name="Tecnologia e IA",
    subtitle="Computação · Inteligência Artificial · Dados · Reprodutibilidade",
    sections=(
        _no_ai_section(),
        Section("Visão Geral", (
            (_b("Sumário", pb.build_message_sumario), _b("Pontos-Chave", pb.build_message_pontos_chave)),
        ), is_open=True),
        Section("Método", (
            (_b("Problema e Abordagem", pb.build_message_problema_abordagem), _b("Dados e Datasets", pb.build_message_dados_datasets)),
            (_b("Métricas e Resultados", pb.build_message_metricas_resultados),),
        )),
        Section("Qualidade", (
            (_b("Reprodutibilidade", pb.build_message_reprodutibilidade), _b("Ameaças à Validade", pb.build_message_ameacas_validade)),
            (_b("Estado da Arte", pb.build_message_comparacao_literatura, "Comparação com o Estado da Arte"), _b("Riscos e Ética", pb.build_message_riscos_eticos)),
        )),
        Section("Aplicação", (
            (_b("Implicações Práticas", pb.build_message_implicacoes_praticas),),
        ), audit_button=True),
    ),
    audience_choices=("Desenvolvedor / Cientista de dados", "Pesquisador / Acadêmico", "Estudante", "Público geral"),
    focus_choices=("Método e dados", "Desempenho e métricas", "Metodologia", "Aplicações práticas"),
    placeholder=_GENERIC_PLACEHOLDER,
    help_markdown=GENERAL_HELP,
    title_suffix=_suffix("Tecnologia e IA"),
)

ENGINEERING_PAGE = PageSpec(
    key="engenharias",
    group="Exatas e Tecnologia",
    tab_name="Engenharias",
    subtitle="Civil · Elétrica · Química · Projeto, desempenho e normas",
    sections=(
        _no_ai_section(),
        Section("Visão Geral", (
            (_b("Sumário", pb.build_message_sumario), _b("Pontos-Chave", pb.build_message_pontos_chave)),
        ), is_open=True),
        Section("Projeto e Método", (
            (_b("Metodologia Experimental", pb.build_message_metodologia_experimental), _b("Parâmetros e Especificações", pb.build_message_parametros_especificacoes)),
            (_b("Resultados e Desempenho", pb.build_message_resultados_desempenho),),
        )),
        Section("Qualidade", (
            (_b("Limitações e Incertezas", pb.build_message_limitacoes_incertezas), _b("Crítica Metodológica", pb.build_message_critica_metodologica)),
            (_b("Estado da Arte", pb.build_message_comparacao_literatura, "Comparação com o Estado da Arte"),),
        )),
        Section("Aplicação", (
            (_b("Aplicação e Normas", pb.build_message_aplicacao_normas), _b("Viabilidade e Custos", pb.build_message_viabilidade_custos)),
            (_b("Implicações Práticas", pb.build_message_implicacoes_praticas),),
        ), audit_button=True),
    ),
    audience_choices=("Engenheiro / Técnico", "Pesquisador / Acadêmico", "Estudante", "Público geral"),
    focus_choices=("Projeto e parâmetros", "Desempenho e métricas", "Normas e aplicação", "Metodologia"),
    placeholder=_GENERIC_PLACEHOLDER,
    help_markdown=GENERAL_HELP,
    title_suffix=_suffix("Engenharias"),
)

# ---------------------------------------------------------------------------
# Abas adicionais (saude aplicada, humanas, aplicadas e para o publico leigo)
# ---------------------------------------------------------------------------
def _overview_section() -> Section:
    return Section("Visão Geral", (
        (_b("Sumário", pb.build_message_sumario), _b("Pontos-Chave", pb.build_message_pontos_chave)),
    ), is_open=True)


NURSING_PAGE = PageSpec(
    key="enfermagem",
    group="Saúde",
    tab_name="Enfermagem",
    subtitle="Cuidados descritos · Escalas e instrumentos · Prática baseada em evidências",
    sections=(
        _no_ai_section(),
        _overview_section(),
        Section("Cuidado e Prática", (
            (_b("Cuidados Descritos", pb.build_message_cuidados_descritos), _b("Escalas e Instrumentos", pb.build_message_escalas_instrumentos)),
            (_b("Implicações para a Prática", pb.build_message_implicacoes_enfermagem),
             _b("Populações Especiais", pb.build_message_populacoes_especiais, requires="populacoes")),
        )),
        Section("Linguagem Simples", (
            (_b("Explicação para o Paciente", pb.build_message_resumo_paciente), _b("Glossário de Termos", pb.build_message_glossario)),
        )),
        Section("Evidência", (
            (_b("Crítica Metodológica", pb.build_message_critica_metodologica), _b("Dados Estatísticos", pb.build_message_estatisticas)),
            (_b("Alertas e Contraindicações", pb.build_message_alertas, requires="alertas"),),
        ), audit_button=True),
    ),
    audience_choices=("Enfermeiro(a)", "Técnico(a) de enfermagem", "Estudante de enfermagem", "Público geral"),
    focus_choices=("Cuidado e assistência", "Instrumentos e escalas", "Metodologia", "Prática baseada em evidências"),
    placeholder=_GENERIC_PLACEHOLDER,
    help_markdown=MEDICAL_HELP,
    compare_title="Comparar dois estudos",
    compare_button="Comparar Estudos",
    clinical=True,
    title_suffix=_suffix("Enfermagem"),
)

PHARMACY_PAGE = PageSpec(
    key="farmacia",
    group="Saúde",
    tab_name="Farmácia",
    subtitle="Fármaco e mecanismo · Eficácia e segurança · Trechos de doses e interações (sem IA)",
    sections=(
        _no_ai_section(),
        _overview_section(),
        Section("Fármaco", (
            (_b("Fármaco, Classe e Mecanismo", pb.build_message_farmaco_classe_mecanismo),
             _b("Eficácia e Segurança", pb.build_message_eficacia_seguranca_farmaco)),
        )),
        Section("Doses, Interações e Reações (trechos, sem IA)", (
            (ExtractButton("Doses e esquemas (trechos)", "dose"), ExtractButton("Interações medicamentosas (trechos)", "interacoes")),
            (ExtractButton("Reações adversas (trechos)", "reacoes"),
             _b("Populações Especiais", pb.build_message_populacoes_especiais, requires="populacoes")),
        )),
        Section("Evidência e Segurança", (
            (_b("Crítica Metodológica", pb.build_message_critica_metodologica), _b("Dados Estatísticos", pb.build_message_estatisticas)),
            (_b("Alertas e Contraindicações", pb.build_message_alertas, requires="alertas"),),
        ), audit_button=True),
        Section("Contexto BR — Regulação", (
            (_b("Vigilância Sanitária", pb.build_message_vigilancia_sanitaria, sources=("anvisa", "minsaude"), check_numbers=False),
             _b("Disponib. SUS", pb.build_message_disponibilidade_sus, "Disponibilidade no SUS", sources=("bvs", "minsaude"), check_numbers=False)),
        )),
    ),
    audience_choices=("Farmacêutico(a)", "Estudante de farmácia", "Pesquisador / Acadêmico", "Público geral"),
    focus_choices=("Farmacologia", "Eficácia e segurança", "Metodologia", "Contexto brasileiro"),
    placeholder=_GENERIC_PLACEHOLDER,
    help_markdown=MEDICAL_HELP,
    compare_title="Comparar dois estudos de fármacos",
    compare_button="Comparar Estudos",
    clinical=True,
    title_suffix=_suffix("Farmácia"),
)

NUTRITION_PAGE = PageSpec(
    key="nutricao",
    group="Saúde",
    tab_name="Nutrição",
    subtitle="Intervenção alimentar · Desfechos · Limites para aplicar o resultado",
    sections=(
        _no_ai_section(),
        _overview_section(),
        Section("Estudo de Nutrição", (
            (_b("Intervenção e População", pb.build_message_intervencao_nutricional),
             _b("Desfechos e Resultados", pb.build_message_desfechos_nutricionais)),
            (_b("PICO", pb.build_message_pico, "Pergunta PICO"),),
        )),
        Section("Linguagem Simples", (
            (_b("Explicação para o Paciente", pb.build_message_resumo_paciente), _b("Glossário de Termos", pb.build_message_glossario)),
        )),
        Section("Evidência", (
            (_b("Crítica Metodológica", pb.build_message_critica_metodologica), _b("Dados Estatísticos", pb.build_message_estatisticas)),
            (_b("Implicações Práticas", pb.build_message_implicacoes_praticas),),
        ), audit_button=True),
    ),
    audience_choices=("Nutricionista", "Estudante de nutrição", "Pesquisador / Acadêmico", "Público geral"),
    focus_choices=("Intervenção alimentar", "Desfechos e resultados", "Metodologia", "Aplicação prática"),
    placeholder=_GENERIC_PLACEHOLDER,
    help_markdown=MEDICAL_HELP,
    compare_title="Comparar dois estudos",
    compare_button="Comparar Estudos",
    clinical=True,
    title_suffix=_suffix("Nutrição"),
)

PSYCHOLOGY_PAGE = PageSpec(
    key="psicologia",
    group="Saúde",
    tab_name="Psicologia",
    subtitle="Instrumentos e escalas · Amostra e tamanho de efeito · Generalização",
    sections=(
        _no_ai_section(),
        _overview_section(),
        Section("Medidas e Amostra", (
            (_b("Instrumentos e Escalas", pb.build_message_instrumentos_psicometricos),
             _b("Amostra e Tamanho de Efeito", pb.build_message_amostra_efeito)),
            (_b("Generalização e Limites", pb.build_message_generalizacao_limites),),
        )),
        Section("Evidência", (
            (_b("Crítica Metodológica", pb.build_message_critica_metodologica), _b("Dados Estatísticos", pb.build_message_estatisticas)),
            (_b("Lacunas de Pesquisa", pb.build_message_lacunas_pesquisa), _b("Implicações Práticas", pb.build_message_implicacoes_praticas)),
        ), audit_button=True),
    ),
    audience_choices=("Psicólogo(a)", "Estudante de psicologia", "Pesquisador / Acadêmico", "Público geral"),
    focus_choices=("Instrumentos e medidas", "Amostra e efeitos", "Metodologia", "Aplicação prática"),
    placeholder=_GENERIC_PLACEHOLDER,
    help_markdown=GENERAL_HELP,
    compare_title="Comparar dois estudos",
    compare_button="Comparar Estudos",
    clinical=True,
    title_suffix=_suffix("Psicologia"),
)

LAW_PAGE = PageSpec(
    key="direito",
    group="Sociedade e Ambiente",
    tab_name="Direito e Políticas",
    subtitle="Política avaliada · Implicações regulatórias · Impacto social (sem parecer jurídico)",
    sections=(
        _no_ai_section(),
        _overview_section(),
        Section("Política e Regulação", (
            (_b("Política ou Norma Avaliada", pb.build_message_politica_avaliada),
             _b("Implicações Regulatórias", pb.build_message_implicacoes_regulatorias)),
            (_b("Impacto Social e Grupos", pb.build_message_impacto_social_grupos),
             _b("Impacto na Sociedade", pb.build_message_impacto_brasil)),
        )),
        Section("Evidência", (
            (_b("Crítica Metodológica", pb.build_message_critica_metodologica), _b("Dados Estatísticos", pb.build_message_estatisticas)),
            (_b("Lacunas de Pesquisa", pb.build_message_lacunas_pesquisa), _b("Implicações para Políticas", pb.build_message_implicacoes_praticas)),
        ), audit_button=True),
    ),
    audience_choices=("Gestor / Analista de políticas", "Estudante de direito", "Pesquisador / Acadêmico", "Público geral"),
    focus_choices=("Política avaliada", "Regulação", "Impacto social", "Contexto brasileiro"),
    placeholder=_GENERIC_PLACEHOLDER,
    help_markdown=GENERAL_HELP,
    title_suffix=_suffix("Direito e Políticas"),
)

EDUCATION_PAGE = PageSpec(
    key="educacao",
    group="Sociedade e Ambiente",
    tab_name="Educação",
    subtitle="Metodologia de ensino · Resultados de aprendizagem · Aplicação em sala de aula",
    sections=(
        _no_ai_section(),
        _overview_section(),
        Section("Ensino e Aprendizagem", (
            (_b("Metodologia de Ensino", pb.build_message_metodologia_ensino),
             _b("Resultados de Aprendizagem", pb.build_message_resultados_aprendizagem)),
            (_b("Aplicação em Sala de Aula", pb.build_message_aplicabilidade_sala),),
        )),
        Section("Para a Turma", (
            (_b("Questões de Discussão", pb.build_message_questoes_discussao), _b("Glossário de Termos", pb.build_message_glossario)),
        )),
        Section("Evidência", (
            (_b("Crítica Metodológica", pb.build_message_critica_metodologica), _b("Dados Estatísticos", pb.build_message_estatisticas)),
        ), audit_button=True),
    ),
    audience_choices=("Professor(a)", "Coordenador(a) pedagógico(a)", "Estudante de licenciatura", "Pesquisador / Acadêmico"),
    focus_choices=("Metodologia de ensino", "Resultados de aprendizagem", "Aplicação em sala", "Metodologia"),
    placeholder=_GENERIC_PLACEHOLDER,
    help_markdown=GENERAL_HELP,
    title_suffix=_suffix("Educação"),
)

AGRO_PAGE = PageSpec(
    key="agro",
    group="Sociedade e Ambiente",
    tab_name="Agro e Veterinária",
    subtitle="Cultura e espécie · Manejo e intervenção · Viabilidade e normas",
    sections=(
        _no_ai_section(),
        _overview_section(),
        Section("Sistema e Manejo", (
            (_b("Espécie e Sistema", pb.build_message_sistema_especie), _b("Manejo e Intervenção", pb.build_message_intervencao_manejo)),
            (_b("Resultados e Desempenho", pb.build_message_resultados_desempenho),),
        )),
        Section("Aplicação", (
            (_b("Aplicação e Normas", pb.build_message_aplicacao_normas), _b("Viabilidade e Custos", pb.build_message_viabilidade_custos)),
        )),
        Section("Evidência", (
            (_b("Limitações e Incertezas", pb.build_message_limitacoes_incertezas), _b("Crítica Metodológica", pb.build_message_critica_metodologica)),
        ), audit_button=True),
    ),
    audience_choices=("Agrônomo / Veterinário", "Técnico / Produtor", "Estudante", "Pesquisador / Acadêmico"),
    focus_choices=("Manejo e intervenção", "Produtividade e sanidade", "Viabilidade", "Metodologia"),
    placeholder=_GENERIC_PLACEHOLDER,
    help_markdown=GENERAL_HELP,
    title_suffix=_suffix("Agro e Veterinária"),
)

BIOTECH_PAGE = PageSpec(
    key="biotecnologia",
    group="Exatas e Tecnologia",
    tab_name="Biotecnologia",
    subtitle="Organismo e método molecular · Dados e acesso · Reprodutibilidade e ética",
    sections=(
        _no_ai_section(),
        _overview_section(),
        Section("Método Molecular", (
            (_b("Organismo e Método Molecular", pb.build_message_organismo_modelo_metodo),
             _b("Dados e Acesso", pb.build_message_dados_sequencias_acesso)),
        )),
        Section("Qualidade", (
            (_b("Reprodutibilidade", pb.build_message_reprodutibilidade), _b("Riscos e Ética", pb.build_message_riscos_eticos)),
            (_b("Estado da Arte", pb.build_message_comparacao_literatura, "Comparação com o Estado da Arte"),),
        )),
        Section("Evidência", (
            (_b("Crítica Metodológica", pb.build_message_critica_metodologica), _b("Dados Estatísticos", pb.build_message_estatisticas)),
            (_b("Lacunas de Pesquisa", pb.build_message_lacunas_pesquisa),),
        ), audit_button=True),
    ),
    audience_choices=("Biólogo / Biotecnólogo", "Pesquisador / Acadêmico", "Estudante", "Público geral"),
    focus_choices=("Método molecular", "Dados e reprodutibilidade", "Ética e riscos", "Metodologia"),
    placeholder=_GENERIC_PLACEHOLDER,
    help_markdown=GENERAL_HELP,
    title_suffix=_suffix("Biotecnologia"),
)

PATIENT_HELP = (
    MEDICAL_HELP
    + """
**Aviso importante:** esta aba explica o que um estudo encontrou, em linguagem simples. Ela **não é orientação
médica**, não diz se um tratamento serve para você e não deve ser usada para iniciar, parar ou mudar tratamento.
Converse com um profissional de saúde.
"""
)

PATIENT_PAGE = PageSpec(
    key="paciente",
    group="Saúde",
    tab_name="Para o Paciente",
    subtitle="Linguagem simples · O que o estudo mostra e não mostra · Perguntas para levar ao profissional",
    sections=(
        _no_ai_section(),
        Section("Em linguagem simples", (
            (_b("O que o Estudo Mostra", pb.build_message_estudo_mostra), _b("O que Ele Não Prova", pb.build_message_estudo_nao_prova)),
            (_b("Perguntas para o Profissional", pb.build_message_perguntas_profissional),),
        ), is_open=True),
        Section("Entender melhor", (
            (_b("Explicação Simples", pb.build_message_resumo_paciente), _b("Termos Explicados", pb.build_message_glossario)),
        ), audit_button=True),
    ),
    audience_choices=("Paciente", "Familiar / Cuidador", "Público geral"),
    focus_choices=("O que o estudo encontrou", "Limites do estudo", "Perguntas para a consulta"),
    placeholder=_GENERIC_PLACEHOLDER,
    help_markdown=PATIENT_HELP,
    compare_title="Comparar dois artigos",
    compare_button="Comparar Artigos",
    clinical=True,
    title_suffix=_suffix("Para o Paciente"),
)


def pages_for(generative_clinical: bool = False) -> tuple[PageSpec, ...]:
    """Abas na ordem da interface. `generative_clinical` liga os botoes de dose/conduta gerados por IA."""
    return (
        GENERAL_PAGE,
        ACADEMIC_PAGE,
        MEDICAL_PAGE_GENERATIVE if generative_clinical else MEDICAL_PAGE,
        ENVIRONMENTAL_PAGE,
        PUBLIC_HEALTH_PAGE,
        TECHNOLOGY_PAGE,
        ENGINEERING_PAGE,
        NURSING_PAGE,
        PHARMACY_PAGE,
        NUTRITION_PAGE,
        PSYCHOLOGY_PAGE,
        LAW_PAGE,
        EDUCATION_PAGE,
        AGRO_PAGE,
        BIOTECH_PAGE,
        PATIENT_PAGE,
    )


def grouped(page_list: tuple[PageSpec, ...]) -> list[tuple[str, list[PageSpec]]]:
    """Agrupa as abas na ordem de `GROUP_ORDER` (menu lateral), mantendo a ordem dentro de cada grupo."""
    return [(name, [p for p in page_list if p.group == name]) for name in GROUP_ORDER if any(p.group == name for p in page_list)]


ALL_PAGES: tuple[PageSpec, ...] = pages_for(False)
