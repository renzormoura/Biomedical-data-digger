"""Extracao sem IA: copia trechos do abstract em vez de gerar texto.

Tudo aqui e deterministico e custa zero token. Como so seleciona e reordena frases que ja
existem no abstract (ou rotulos de registros oficiais), nao consegue inventar conteudo.
A selecao e por palavras-chave, entao pode perder frases relevantes (falso negativo) ou
trazer frases pouco relevantes; por isso a interface sempre mostra o texto original e avisa
que nada foi gerado nem interpretado.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Frases
# ---------------------------------------------------------------------------
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9(\[])|\n+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text or "") if s and s.strip()]


# ---------------------------------------------------------------------------
# Abstract estruturado (secoes com rotulo)
# ---------------------------------------------------------------------------
_SECTION_LABELS: dict[str, tuple[str, ...]] = {
    "Contexto": ("background", "introduction", "context", "rationale", "introdução", "introducao", "introducción",
                 "contexto", "antecedentes", "justificativa"),
    "Objetivo": ("objectives", "objective", "aims", "aim", "purpose", "goal", "objetivos", "objetivo", "propósito"),
    "Métodos": ("materials and methods", "material y métodos", "materiales y métodos", "main outcome measures", "outcome measures", "study design", "methodology",
                "methods", "method", "design", "setting", "participants", "patients", "subjects", "interventions",
                "intervention", "métodos", "metodos", "método", "metodologia", "desenho", "participantes", "pacientes"),
    "Resultados": ("results", "result", "findings", "resultados", "resultado", "achados"),
    "Conclusões": ("conclusions", "conclusion", "interpretation", "implications", "conclusões", "conclusoes",
                   "conclusão", "interpretação", "conclusiones", "conclusión"),
    "Limitações": ("limitations", "limitação", "limitações", "limitacoes"),
    "Registro e financiamento": ("trial registration", "registration", "funding", "registro", "financiamento"),
}
_LABEL_TO_SECTION = {label: section for section, labels in _SECTION_LABELS.items() for label in labels}
_LABEL_ALTERNATION = "|".join(sorted((re.escape(label) for label in _LABEL_TO_SECTION), key=len, reverse=True))
_SECTION_RE = re.compile(rf"(?:^|(?<=[.!?])\s+|(?<=\n))\s*({_LABEL_ALTERNATION})\s*:\s*", re.IGNORECASE)
# Alguns periodicos usam "Objetivo. Texto" em vez de "Objetivo: Texto". O ponto e ambiguo, entao so vale
# com rotulo capitalizado, seguido de frase iniciada em maiuscula, e com 3 ou mais rotulos no resumo.
_SECTION_DOT_RE = re.compile(
    rf"(?:^|(?<=[.!?])\s+|(?<=\n))\s*((?:{_LABEL_ALTERNATION}))\.\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])", re.IGNORECASE
)
_MIN_DOT_LABELS = 3


@dataclass(frozen=True)
class AbstractSection:
    heading: str  # nome padronizado (ex.: "Métodos")
    label: str  # rotulo como apareceu no abstract (ex.: "Patients")
    text: str  # texto copiado literalmente


def split_sections(abstract: str) -> list[AbstractSection]:
    """Divide o abstract pelos rotulos (Background, Methods, Results...). Menos de 2 rotulos = [].

    Abstracts sem estrutura sao frequentes: nesse caso a interface mostra o texto inteiro.
    """
    text = (abstract or "").strip()
    matches = list(_SECTION_RE.finditer(text))
    if len(matches) < 2:
        dotted = [m for m in _SECTION_DOT_RE.finditer(text) if m.group(1)[:1].isupper()]
        if len(dotted) < _MIN_DOT_LABELS:
            return []
        matches = dotted
    sections: list[AbstractSection] = []
    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.append(AbstractSection("Texto inicial", "", preamble))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end(): end].strip()
        if body:
            label = match.group(1).strip()
            sections.append(AbstractSection(_LABEL_TO_SECTION[label.lower()], label, body))
    return sections


# ---------------------------------------------------------------------------
# Numeros com a frase de origem
# ---------------------------------------------------------------------------
_NUM = r"-?\d+(?:[.,]\d+)?"
_FINDING_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("tamanho da amostra", re.compile(
        r"\b[nN]\s*=\s*\d[\d.,]*|\b\d[\d.,]*\s+(?:adult|patient|participant|subject|individual|women|men|children|"
        r"infant|neonate|case|person|people|pacient|particip|adulto|criança|mulher|homem|indivíduo|caso)",
        re.IGNORECASE)),
    ("medida de efeito", re.compile(
        rf"\b(?:a?HR|a?OR|a?RR|IRR|SMD|WMD|RRR|ARR|NNT|NNH|RMa?|RPa?|RRa|hazard ratio|odds ratio|risk ratio|"
        rf"relative risk|raz[aã]o de (?:chances|risco|momios))\b\s*(?:[=:]|of|de)?\s*{_NUM}")),
    ("intervalo de confiança", re.compile(
        rf"\b(?:(?:90|95|99)\s*%\s*(?:CI|IC|confidence interval|intervalo de confian[cç]a)|"
        rf"(?:CI|IC)\s*(?:90|95|99)\s*%?)[^0-9\-]{{0,12}}{_NUM}\s*(?:-|–|—|to|a|,)\s*{_NUM}", re.IGNORECASE)),
    ("valor de p", re.compile(r"\bp\s*(?:value\s*)?[<>=≤≥]\s*0?[.,]?\d+", re.IGNORECASE)),
    ("seguimento", re.compile(
        rf"(?:followed|follow-up|seguimento|acompanhad\w*)[^.;]{{0,60}}?{_NUM}\s*"
        r"(?:years?|months?|weeks?|days?|anos?|meses|semanas|dias)", re.IGNORECASE)),
    ("percentual", re.compile(rf"{_NUM}\s*%")),
)
_CI_LABEL = re.compile(r"\b(?:CI|IC)\s*(?:90|95|99)\s*%|\b(?:90|95|99)\s*%\s*(?:CI|IC)\b", re.IGNORECASE)
MAX_FINDINGS = 15


def _without_ci_label(sentence: str, tag: str) -> str:
    """O "95%" do rotulo do intervalo nao e um percentual de resultado."""
    return _CI_LABEL.sub(" ", sentence) if tag == "percentual" else sentence


@dataclass(frozen=True)
class Finding:
    sentence: str  # frase copiada do abstract
    tags: tuple[str, ...]


def extract_findings(abstract: str) -> list[Finding]:
    """Frases do abstract que contem dados estatisticos, com o tipo de dado encontrado."""
    findings: list[Finding] = []
    for sentence in split_sentences(abstract):
        tags = tuple(tag for tag, pattern in _FINDING_PATTERNS if pattern.search(_without_ci_label(sentence, tag)))
        if tags:
            findings.append(Finding(sentence, tags))
    return findings[:MAX_FINDINGS]


# ---------------------------------------------------------------------------
# Trechos por tema (para botoes de alto risco: dose, conduta, interacoes, reacoes)
# ---------------------------------------------------------------------------
_DOSE_UNITS = r"(?:mg|mcg|µg|ug|g|kg|ml|mL|UI|IU|units?|mmol|mEq)"
_CUES: dict[str, re.Pattern[str]] = {
    "dose": re.compile(
        rf"\b\d+(?:[.,]\d+)?\s*{_DOSE_UNITS}(?:/(?:kg|day|d|h|dia|m2|m²|dose))?\b(?!/min)|"
        r"\b(?:dose[sd]?|dosage|dosing|posology|posologia|dosagem|twice daily|once daily|daily|bid|tid|qid|"
        r"intravenous\w*|orally|subcutaneous\w*|intramuscular\w*|infusion|bolus|titrat\w*|loading dose|"
        r"dosis|dosificaci\w*|v[ií]a (?:oral|intravenosa)|diari[ao]s?)\b",
        re.IGNORECASE),
    "conduta": re.compile(
        r"\b(?:recommend\w*|should|guideline\w*|management|protocol\w*|first-line|second-line|algorithm|"
        r"standard of care|treatment strategy|manejo|conduta|diretriz\w*|recomend\w*|primeira linha|"
        r"gu[ií]as?|pautas?|desaconsej\w*|aconsej\w*)\b",
        re.IGNORECASE),
    "interacoes": re.compile(
        r"\b(?:interact\w*|co-?administ\w*|concomitant\w*|concurrent\w*|drug[- ]drug|inhibitor\w*|inducer\w*|"
        r"CYP\w*|P-gp|potentiat\w*|synerg\w*|antagonis\w*|interaç\w*|interacci\w*|coadministra\w*)\b",
        re.IGNORECASE),
    "reacoes": re.compile(
        r"\b(?:adverse|side effects?|toxicit\w*|safety|tolerab\w*|discontinu\w*|withdrawal|hypoglyc\w*|nausea|"
        r"vomit\w*|diarrh\w*|bleeding|hemorrhag\w*|reaç\w*|adverso\w*|efeitos? colaterais|segurança|toxicidade|"
        r"tolerabilidade|efectos? (?:secundari\w*|adversos?|colaterales)|secunda-?rios|reacciones? adversas?|"
        r"seguridad)\b", re.IGNORECASE),
    # Usados como pre-condicao: o botao so chama o modelo se o abstract trouxer o tema.
    "populacoes": re.compile(
        r"\b(?:elderly|older adults?|older patients?|aged\s+\d+|geriatric|pediatric|paediatric|children|infant\w*|"
        r"neonat\w*|adolescent\w*|pregnan\w*|lactat\w*|breastfe\w*|renal|kidney|hepatic|liver|dialysis|eGFR|"
        r"idos\w*|criança\w*|gestan\w*|hepátic\w*|anciano\w*|ni[ñn]os?|embaraz\w*|hep[aá]tic\w*)\b",
        re.IGNORECASE),
    "alertas": re.compile(
        r"\b(?:contraindicat\w*|warning\w*|caution|adverse|harm\w*|risk\w*|toxic\w*|mortality|bleeding|"
        r"hypoglyc\w*|safety|risco\w*|alert\w*|cuidado|segurança|mortalidade|advertencia\w*|riesgo\w*|"
        r"seguridad|mortalidad)\b", re.IGNORECASE),
}
CUE_KINDS = tuple(_CUES)
MAX_PASSAGES = 8


def extract_passages(abstract: str, kind: str, limit: int = MAX_PASSAGES) -> list[str]:
    """Frases do abstract que mencionam o tema `kind`, copiadas sem alteracao."""
    pattern = _CUES[kind]
    return [s for s in split_sentences(abstract) if pattern.search(s)][:limit]


def has_cues(abstract: str, kind: str) -> bool:
    return bool(_CUES[kind].search(abstract or ""))


# ---------------------------------------------------------------------------
# Tipo de estudo (rotulos oficiais do registro, nao opiniao)
# ---------------------------------------------------------------------------
STUDY_TYPE_LABELS: dict[str, str] = {
    "randomized controlled trial": "Ensaio clínico randomizado",
    "clinical trial": "Ensaio clínico",
    "controlled clinical trial": "Ensaio clínico controlado",
    "meta-analysis": "Meta-análise",
    "systematic review": "Revisão sistemática",
    "review": "Revisão",
    "review-article": "Revisão",
    "case reports": "Relato de caso",
    "observational study": "Estudo observacional",
    "comparative study": "Estudo comparativo",
    "multicenter study": "Estudo multicêntrico",
    "practice guideline": "Diretriz de prática clínica",
    "guideline": "Diretriz",
    "preprint": "Preprint",
    "letter": "Carta",
    "editorial": "Editorial",
    "comment": "Comentário",
}
_GENERIC_TYPES = {
    "journal article", "research support, non-u.s. gov't", "research-article", "article", "english abstract", "other",
}


def study_type_labels(pub_types: list[str]) -> list[str]:
    """Traduz os tipos de publicacao do registro; tipos genericos sao omitidos; desconhecidos ficam como estao."""
    labels: list[str] = []
    for pub_type in pub_types:
        key = pub_type.strip().lower()
        if not key or key in _GENERIC_TYPES or key.startswith("research support"):
            continue
        label = STUDY_TYPE_LABELS.get(key, pub_type.strip())
        if label not in labels:
            labels.append(label)
    return labels
