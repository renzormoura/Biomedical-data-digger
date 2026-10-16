"""Pontuacao de confiabilidade de um artigo, transparente e sem IA.

O que a nota mede: sinais verificaveis no registro da fonte e no resumo (abstract) do artigo, como
tipo de estudo, retratacao, revisao por pares, tamanho da amostra e medidas de precisao informadas.
O que a nota NAO mede: a qualidade da execucao do estudo, o risco de vies nem a validade clinica.
Isso exige o texto completo e julgamento de especialistas, entao o resultado sempre traz esse aviso.

Regras de projeto:
- cada criterio tem peso fixo, estado (atendido, parcial, nao atendido, nao se aplica, desconhecido)
  e a evidencia usada, para o usuario poder conferir;
- "desconhecido" e "nao se aplica" saem do denominador: faltar dado na fonte nao pune o artigo,
  mas reduz a "cobertura" (quanto da nota foi realmente avaliado);
- artigo retratado vale 0, qualquer que seja o resto.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from catalog import Work
from extraction import AbstractSection, Finding

MET, PARTIAL, UNMET, NA, UNKNOWN = "met", "partial", "unmet", "na", "unknown"
LOW_COVERAGE = 0.5
BANDS = ((75, "Alta"), (50, "Moderada"))
DISCLAIMER = (
    "Esta nota resume sinais verificáveis no registro e no resumo do artigo. Ela não avalia a qualidade da "
    "execução do estudo, o risco de viés nem a validade clínica, e não substitui a leitura crítica do texto completo."
)

# Nivel de evidencia pelo desenho (rotulo oficial) -> fracao do peso. Segue a ideia geral das hierarquias
# de evidencia (revisao sistematica > ensaio randomizado > coorte/caso-controle > relato de caso).
_DESIGN_SCORES: dict[str, float] = {
    "Revisão sistemática": 1.0, "Meta-análise": 1.0,
    "Ensaio clínico randomizado": 0.9,
    "Diretriz de prática clínica": 0.75, "Diretriz": 0.75,
    "Ensaio clínico controlado": 0.75, "Ensaio clínico": 0.7,
    "Estudo multicêntrico": 0.55, "Estudo observacional": 0.55, "Estudo comparativo": 0.55,
    "Revisão": 0.5,
    "Relato de caso": 0.25,
    "Carta": 0.1, "Editorial": 0.1, "Comentário": 0.1,
}

_REGISTRY = re.compile(
    r"\b(?:NCT\s?\d{8}|ISRCTN\s?\d{5,8}|ChiCTR[-\w]*\d+|RBR-\w{6,}|ACTRN\s?\d{10,}|EUCTR[\d-]+|"
    r"CTRI/\d{4}/\d+|DRKS\d{8}|UMIN\d{9}|PACTR\d+)\b", re.IGNORECASE)
_TRIAL_WORDS = re.compile(r"\b(?:randomi[sz]ed|randomizado|aleatori[sz]ado|clinical trial|ensaio cl[ií]nico)\b", re.IGNORECASE)
_STUDIES_INCLUDED = re.compile(
    r"\b\d{1,4}\s+(?:randomi[sz]ed\s+)?(?:studies|trials|articles|papers|estudos|ensaios|artigos|trabalhos)\b", re.IGNORECASE)
_REVIEW_TYPES = frozenset({"Revisão sistemática", "Meta-análise", "Revisão"})
_NO_EMPIRICAL = frozenset({"Carta", "Editorial", "Comentário", "Diretriz de prática clínica", "Diretriz"})


@dataclass(frozen=True)
class Criterion:
    key: str
    name: str
    weight: int
    status: str
    points: float
    detail: str  # o que foi encontrado ou por que nao foi possivel avaliar
    evidence: str = ""  # trecho/rotulo copiado da fonte, quando houver
    how: str = ""  # como o criterio e avaliado (texto fixo)


@dataclass(frozen=True)
class Reliability:
    score: int | None  # None quando nao ha base minima para avaliar
    band: str  # "Alta", "Moderada", "Baixa", "Indeterminada" ou "Retratado"
    coverage: int  # % do peso total realmente avaliado
    criteria: tuple[Criterion, ...]
    summary: str
    warnings: tuple[str, ...]
    disclaimer: str = DISCLAIMER


def _best_design(study_types: tuple[str, ...]) -> str:
    known = [t for t in study_types if t in _DESIGN_SCORES]
    return max(known, key=lambda t: _DESIGN_SCORES[t]) if known else ""


def _first(findings: tuple[Finding, ...], tag: str) -> Finding | None:
    return next((f for f in findings if tag in f.tags), None)


def _snippet(text: str, limit: int = 220) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _integrity(work: Work) -> Criterion:
    how = "Consulta a marca de retratação no registro da fonte (Europe PMC ou OpenAlex)."
    if work.retracted:
        return Criterion("integridade", "Integridade (retratação)", 20, UNMET, 0,
                         "O registro marca este artigo como RETRATADO. Não use como evidência.", work.source, how)
    return Criterion("integridade", "Integridade (retratação)", 20, MET, 20,
                     f"Sem marca de retratação no registro de {work.source or 'a fonte'}. "
                     "A checagem cobre só essa fonte; retratações recentes podem ainda não constar.", "", how)


def _design(work: Work) -> Criterion:
    how = ("Usa o tipo de estudo do registro oficial. Revisão sistemática e meta-análise pontuam mais; "
           "ensaio randomizado vem a seguir; estudos observacionais, revisões narrativas e relatos de caso pontuam menos.")
    best = _best_design(work.study_types)
    if not best:
        return Criterion("desenho", "Desenho do estudo", 25, UNKNOWN, 0,
                         "A fonte não informa o tipo de estudo. O critério não entra no cálculo.", "", how)
    fraction = _DESIGN_SCORES[best]
    status = MET if fraction >= 0.9 else PARTIAL
    return Criterion("desenho", "Desenho do estudo", 25, status, round(25 * fraction, 1),
                     f"Tipo de estudo registrado: {best}. Pontua {round(fraction * 100)}% do peso.", best, how)


def _peer_review(work: Work) -> Criterion:
    how = "Preprint não passou por revisão por pares; artigo em periódico indexado é considerado revisado."
    if "Preprint" in work.study_types:
        return Criterion("revisao_pares", "Revisão por pares", 10, UNMET, 0,
                         "Publicado como preprint, sem revisão por pares até o registro.", "Preprint", how)
    if work.journal:
        return Criterion("revisao_pares", "Revisão por pares", 10, MET, 10,
                         "Publicado em periódico. O registro não informa o rigor da revisão de cada periódico.",
                         work.journal, how)
    return Criterion("revisao_pares", "Revisão por pares", 10, UNKNOWN, 0,
                     "A fonte não informa o periódico nem se é preprint.", "", how)


def _sample(work: Work, findings: tuple[Finding, ...]) -> Criterion:
    how = "Procura no resumo o tamanho da amostra (n = ..., N participantes) ou o número de estudos incluídos."
    if not work.abstract:
        return Criterion("amostra", "Tamanho da amostra informado", 10, UNKNOWN, 0, "Sem resumo para avaliar.", "", how)
    found = _first(findings, "tamanho da amostra")
    if found:
        return Criterion("amostra", "Tamanho da amostra informado", 10, MET, 10,
                         "O resumo informa o tamanho da amostra.", _snippet(found.sentence), how)
    match = _STUDIES_INCLUDED.search(work.abstract)
    if match and _best_design(work.study_types) in _REVIEW_TYPES:
        return Criterion("amostra", "Tamanho da amostra informado", 10, MET, 10,
                         "O resumo informa quantos estudos a revisão incluiu.", match.group(0), how)
    if set(work.study_types) & _NO_EMPIRICAL:
        return Criterion("amostra", "Tamanho da amostra informado", 10, NA, 0,
                         "Este tipo de publicação não tem amostra própria.", "", how)
    return Criterion("amostra", "Tamanho da amostra informado", 10, UNMET, 0,
                     "O resumo não informa o tamanho da amostra (pode constar no texto completo).", "", how)


def _results(work: Work, findings: tuple[Finding, ...]) -> Criterion:
    how = "Procura no resumo uma medida de efeito (HR, OR, RR, diferença de médias) com valor numérico."
    if not work.abstract:
        return Criterion("resultados", "Resultado principal quantificado", 10, UNKNOWN, 0, "Sem resumo para avaliar.", "", how)
    effect = _first(findings, "medida de efeito")
    if effect:
        return Criterion("resultados", "Resultado principal quantificado", 10, MET, 10,
                         "O resumo traz uma medida de efeito numérica.", _snippet(effect.sentence), how)
    pct = _first(findings, "percentual")
    if pct:
        return Criterion("resultados", "Resultado principal quantificado", 10, PARTIAL, 5,
                         "O resumo traz números ou percentuais, mas sem uma medida de efeito identificável.",
                         _snippet(pct.sentence), how)
    if set(work.study_types) & _NO_EMPIRICAL:
        return Criterion("resultados", "Resultado principal quantificado", 10, NA, 0,
                         "Este tipo de publicação não tem resultado empírico próprio.", "", how)
    return Criterion("resultados", "Resultado principal quantificado", 10, UNMET, 0,
                     "O resumo não traz resultados quantificados.", "", how)


def _precision(work: Work, findings: tuple[Finding, ...]) -> Criterion:
    how = "Procura no resumo um intervalo de confiança (melhor) ou valor de p (parcial)."
    if not work.abstract:
        return Criterion("precisao", "Precisão estatística (IC ou p)", 10, UNKNOWN, 0, "Sem resumo para avaliar.", "", how)
    ci = _first(findings, "intervalo de confiança")
    if ci:
        return Criterion("precisao", "Precisão estatística (IC ou p)", 10, MET, 10,
                         "O resumo informa intervalo de confiança.", _snippet(ci.sentence), how)
    p_value = _first(findings, "valor de p")
    if p_value:
        return Criterion("precisao", "Precisão estatística (IC ou p)", 10, PARTIAL, 5,
                         "O resumo informa valor de p, mas não intervalo de confiança.", _snippet(p_value.sentence), how)
    if set(work.study_types) & (_NO_EMPIRICAL | {"Relato de caso"}):
        return Criterion("precisao", "Precisão estatística (IC ou p)", 10, NA, 0,
                         "Este tipo de publicação normalmente não traz estatística inferencial.", "", how)
    return Criterion("precisao", "Precisão estatística (IC ou p)", 10, UNMET, 0,
                     "O resumo não informa intervalo de confiança nem valor de p.", "", how)


def _methods(work: Work, sections: tuple[AbstractSection, ...]) -> Criterion:
    how = "Verifica se o resumo é estruturado e traz a seção de métodos (desenho, participantes, intervenção)."
    if not work.abstract:
        return Criterion("metodos", "Método descrito no resumo", 10, UNKNOWN, 0, "Sem resumo para avaliar.", "", how)
    method = next((s for s in sections if s.heading == "Métodos"), None)
    if method:
        return Criterion("metodos", "Método descrito no resumo", 10, MET, 10,
                         "O resumo traz uma seção de métodos.", _snippet(method.text), how)
    if len(work.abstract) >= 600:
        return Criterion("metodos", "Método descrito no resumo", 10, PARTIAL, 5,
                         "O resumo é longo, mas não separa os métodos por seção.", "", how)
    return Criterion("metodos", "Método descrito no resumo", 10, UNMET, 0,
                     "O resumo é curto e não descreve o método.", "", how)


def _registry(work: Work) -> Criterion:
    how = "Para ensaios clínicos: procura número de registro prévio (ClinicalTrials.gov, ReBEC, ISRCTN e outros) no resumo."
    is_trial = bool(
        set(work.study_types) & {"Ensaio clínico randomizado", "Ensaio clínico", "Ensaio clínico controlado"}
        or _TRIAL_WORDS.search(work.abstract or "")
    )
    if not is_trial:
        return Criterion("registro", "Registro prévio do ensaio", 5, NA, 0,
                         "Não se aplica: o artigo não é identificado como ensaio clínico.", "", how)
    match = _REGISTRY.search(work.abstract or "")
    if match:
        return Criterion("registro", "Registro prévio do ensaio", 5, MET, 5,
                         "O resumo cita o registro do ensaio.", match.group(0), how)
    return Criterion("registro", "Registro prévio do ensaio", 5, UNMET, 0,
                     "Ensaio sem número de registro no resumo (pode constar no texto completo).", "", how)


def _band(score: int) -> str:
    return next((name for floor, name in BANDS if score >= floor), "Baixa")


def assess(work: Work, sections: tuple[AbstractSection, ...] = (), findings: tuple[Finding, ...] = ()) -> Reliability:
    """Calcula a nota (0 a 100) e o detalhe por criterio."""
    criteria = (
        _integrity(work), _design(work), _peer_review(work), _sample(work, findings),
        _results(work, findings), _precision(work, findings), _methods(work, sections), _registry(work),
    )
    total = sum(c.weight for c in criteria)
    assessed = [c for c in criteria if c.status not in (NA, UNKNOWN)]
    weight = sum(c.weight for c in assessed)
    coverage = round(100 * weight / total)
    warnings: list[str] = []
    if work.retracted:
        return Reliability(
            score=0, band="Retratado", coverage=coverage, criteria=criteria,
            summary="Artigo retratado: a nota é 0, independentemente dos demais critérios.",
            warnings=("A fonte marca este artigo como retratado.",),
        )
    if not work.abstract:
        warnings.append("Sem resumo disponível: só os dados do registro foram avaliados.")
    if weight / total < LOW_COVERAGE:
        return Reliability(
            score=None, band="Indeterminada", coverage=coverage, criteria=criteria,
            summary="Não há dados suficientes na fonte para calcular uma nota confiável.",
            warnings=tuple(warnings),
        )
    score = round(100 * sum(c.points for c in assessed) / weight)
    if coverage < 80:
        warnings.append(f"Nota calculada com {coverage}% dos critérios avaliáveis; o restante não pôde ser verificado.")
    band = _band(score)
    return Reliability(
        score=score, band=band, coverage=coverage, criteria=criteria,
        summary=f"{score}/100 ({band}), com {coverage}% dos critérios avaliados.",
        warnings=tuple(warnings),
    )
