"""Pontuacao de confiabilidade: regras, cobertura e casos limite."""

from __future__ import annotations

import pytest

import reliability
from catalog import Work
from extraction import extract_findings, split_sections

RCT_ABSTRACT = (
    "Background: Sepsis is common. Methods: We randomized 420 patients to drug or placebo. "
    "Trial registration: NCT01234567. Results: Mortality fell (HR 0.72, 95% CI 0.58-0.90; p = 0.003). "
    "Conclusions: The drug reduced mortality."
)


def assess(work: Work) -> reliability.Reliability:
    return reliability.assess(work, tuple(split_sections(work.abstract)), tuple(extract_findings(work.abstract)))


def by_key(result: reliability.Reliability, key: str) -> reliability.Criterion:
    return next(c for c in result.criteria if c.key == key)


def make(**kw: object) -> Work:
    base: dict[str, object] = {"ref": "1", "title": "T", "journal": "Lancet", "source": "Europe PMC"}
    base.update(kw)
    return Work(**base)  # type: ignore[arg-type]


def test_pesos_somam_cem() -> None:
    assert sum(c.weight for c in assess(make()).criteria) == 100


def test_ensaio_bem_relatado_tem_nota_alta_com_evidencias() -> None:
    result = assess(make(study_types=("Ensaio clínico randomizado",), abstract=RCT_ABSTRACT))
    assert result.band == "Alta"
    assert result.score is not None and result.score >= 90
    assert by_key(result, "registro").status == reliability.MET
    assert "NCT01234567" in by_key(result, "registro").evidence
    assert "95% CI" in by_key(result, "precisao").evidence
    assert result.coverage == 100


def test_retratado_vale_zero_independente_do_resto() -> None:
    result = assess(make(study_types=("Ensaio clínico randomizado",), abstract=RCT_ABSTRACT, retracted=True))
    assert result.score == 0 and result.band == "Retratado"
    assert by_key(result, "integridade").status == reliability.UNMET


def test_preprint_perde_revisao_por_pares() -> None:
    result = assess(make(study_types=("Preprint",), journal="", abstract=RCT_ABSTRACT))
    assert by_key(result, "revisao_pares").status == reliability.UNMET


def test_sem_dados_suficientes_e_indeterminada_e_nao_pune() -> None:
    result = assess(make(journal="", abstract="", study_types=()))
    assert result.score is None and result.band == "Indeterminada"
    assert by_key(result, "desenho").status == reliability.UNKNOWN


def test_desconhecido_sai_do_denominador() -> None:
    with_type = assess(make(study_types=("Estudo observacional",), abstract=RCT_ABSTRACT))
    without_type = assess(make(study_types=(), abstract=RCT_ABSTRACT))
    assert without_type.coverage < with_type.coverage
    assert without_type.score is not None and without_type.score > with_type.score  # nao foi punido


def test_registro_so_se_aplica_a_ensaios() -> None:
    assert by_key(assess(make(study_types=("Revisão",), abstract=RCT_ABSTRACT.replace("randomized", "reviewed"))), "registro").status == reliability.NA
    assert by_key(assess(make(study_types=("Ensaio clínico randomizado",), abstract="Methods: x. Results: y.")), "registro").status == reliability.UNMET


def test_editorial_nao_e_punido_por_nao_ter_amostra() -> None:
    result = assess(make(study_types=("Editorial",), abstract="Opinião curta sobre o tema."))
    assert by_key(result, "amostra").status == reliability.NA
    assert by_key(result, "precisao").status == reliability.NA


def test_revisao_com_estudos_incluidos_conta_como_amostra() -> None:
    result = assess(make(study_types=("Meta-análise",), abstract="Methods: x. Results: We included 34 randomized trials. Conclusions: y."))
    assert by_key(result, "amostra").status == reliability.MET


@pytest.mark.parametrize(("types", "expected"), [
    (("Revisão sistemática",), 25.0),
    (("Ensaio clínico randomizado",), 22.5),
    (("Relato de caso",), 6.2),
    (("Relato de caso", "Meta-análise"), 25.0),
])
def test_desenho_usa_o_melhor_tipo(types: tuple[str, ...], expected: float) -> None:
    assert by_key(assess(make(study_types=types)), "desenho").points == pytest.approx(expected, abs=0.1)


def test_faixas_e_aviso_sempre_presente() -> None:
    result = assess(make(study_types=("Relato de caso",), abstract="Um paciente relatou melhora após o tratamento."))
    assert result.band in {"Moderada", "Baixa"}
    assert "não avalia a qualidade da execução" in result.disclaimer
    assert all(c.how for c in result.criteria)


def test_evidencia_longa_e_truncada() -> None:
    long_sentence = "We enrolled n = 100 patients " + "x" * 400 + "."
    evidence = by_key(assess(make(abstract=f"Methods: a. Results: {long_sentence}")), "amostra").evidence
    assert len(evidence) <= 220
