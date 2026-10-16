import pytest

from extraction import (
    CUE_KINDS,
    extract_findings,
    extract_passages,
    has_cues,
    split_sections,
    split_sentences,
    study_type_labels,
)

STRUCTURED = (
    "Background: Metformin is widely used in type 2 diabetes. "
    "Methods: We conducted a cohort study including 12,450 adults aged 60 years or older. "
    "Patients were followed for a median of 4.2 years. "
    "Results: Metformin use was associated with a lower risk (HR 0.82; 95% CI 0.74-0.91; p<0.001). "
    "Gastrointestinal adverse events were more frequent (11.3% vs 6.1%). "
    "Conclusions: Metformin was associated with fewer events. Randomized trials are needed."
)
UNSTRUCTURED = "We studied 540 adults. Treatment lowered HbA1c by 0.8% (95% CI -1.1 to -0.5). Metformin remains first-line."


# ------------------------------------------------------------------ secoes
def test_structured_abstract_is_split_verbatim():
    sections = split_sections(STRUCTURED)
    assert [s.heading for s in sections] == ["Contexto", "Métodos", "Resultados", "Conclusões"]
    assert sections[0].text == "Metformin is widely used in type 2 diabetes."
    assert "12,450 adults" in sections[1].text and "median of 4.2 years" in sections[1].text
    assert sections[3].text.endswith("Randomized trials are needed.")
    # nada e inventado nem perdido: o texto de todas as secoes esta no abstract original
    assert all(s.text in STRUCTURED for s in sections)


def test_unstructured_or_single_label_abstracts_return_no_sections():
    assert split_sections(UNSTRUCTURED) == []
    assert split_sections("Methods: only one label here, so we do not split.") == []
    assert split_sections("") == []


def test_portuguese_labels_and_preamble_are_supported():
    text = "Estudo multicêntrico. Introdução: Contexto geral. Métodos: Coorte de 200 pacientes. Resultados: Menor risco."
    sections = split_sections(text)
    assert [s.heading for s in sections] == ["Texto inicial", "Contexto", "Métodos", "Resultados"]


def test_label_words_inside_sentences_are_not_treated_as_sections():
    text = "The study design was novel: results were promising. Background: Old. Results: New."
    headings = [s.heading for s in split_sections(text)]
    assert headings == ["Texto inicial", "Contexto", "Resultados"]


def test_sentence_splitting_keeps_decimals_and_abbreviations_together():
    sentences = split_sentences("HR 0.82; p<0.001. The rate was 11.3% vs 6.1%. Next sentence here.")
    assert sentences == ["HR 0.82; p<0.001.", "The rate was 11.3% vs 6.1%.", "Next sentence here."]


# ------------------------------------------------------------------ numeros
def test_findings_return_original_sentences_with_tags():
    findings = extract_findings(STRUCTURED)
    by_sentence = {f.sentence: f.tags for f in findings}
    effect = "Results: Metformin use was associated with a lower risk (HR 0.82; 95% CI 0.74-0.91; p<0.001)."
    key = next(s for s in by_sentence if "HR 0.82" in s)
    assert {"medida de efeito", "intervalo de confiança", "valor de p"} <= set(by_sentence[key])
    assert any("12,450 adults" in s and "tamanho da amostra" in t for s, t in by_sentence.items())
    assert any("4.2 years" in s and "seguimento" in t for s, t in by_sentence.items())
    assert all(f.sentence in STRUCTURED.replace("Results: ", "") or f.sentence in STRUCTURED for f in findings)
    assert effect  # silencia linter: a frase com rotulo e a mesma que o regex enxerga


def test_findings_never_contain_text_absent_from_the_abstract():
    for finding in extract_findings(STRUCTURED + " " + UNSTRUCTURED):
        assert finding.sentence in (STRUCTURED + " " + UNSTRUCTURED)


def test_findings_ignore_sentences_without_statistics():
    assert extract_findings("Metformin is widely used. Randomized trials are needed.") == []


def test_negative_confidence_intervals_and_percentages_are_detected():
    tags = {t for f in extract_findings(UNSTRUCTURED) for t in f.tags}
    assert {"tamanho da amostra", "intervalo de confiança", "percentual"} <= tags


def test_findings_are_capped():
    many = " ".join(f"Group {i} had {i + 10}% events." for i in range(40))
    assert len(extract_findings(many)) == 15


# ------------------------------------------------------------------ trechos por tema
DRUG = (
    "Patients received metformin 500 mg twice daily for 12 weeks. "
    "Gastrointestinal adverse events occurred in 11.3% of patients. "
    "Co-administration with cimetidine increased exposure. "
    "Guidelines recommend metformin as first-line therapy. "
    "Mean eGFR was 45 mL/min in the older subgroup."
)


@pytest.mark.parametrize(
    "kind,expected,absent",
    [
        ("dose", "500 mg twice daily", "eGFR was 45 mL/min"),
        ("reacoes", "adverse events", "500 mg"),
        ("interacoes", "Co-administration with cimetidine", "500 mg"),
        ("conduta", "Guidelines recommend", "cimetidine"),
    ],
)
def test_passages_pick_only_matching_sentences_verbatim(kind, expected, absent):
    passages = extract_passages(DRUG, kind)
    assert any(expected in p for p in passages)
    assert not any(absent in p for p in passages)
    assert all(p in DRUG for p in passages)


def test_egfr_ml_per_min_is_not_mistaken_for_a_dose():
    assert extract_passages("Mean eGFR was 45 mL/min.", "dose") == []
    assert not has_cues("Mean eGFR was 45 mL/min.", "dose")


def test_abstract_without_the_topic_has_no_passages_and_no_cues():
    plain = "We studied 540 adults. Treatment lowered HbA1c."
    for kind in ("dose", "interacoes", "reacoes", "conduta"):
        assert extract_passages(plain, kind) == [] and not has_cues(plain, kind)


def test_all_kinds_are_known_and_cues_work_for_precondition_kinds():
    assert {"dose", "conduta", "interacoes", "reacoes", "populacoes", "alertas"} <= set(CUE_KINDS)
    assert has_cues("Benefits were attenuated in elderly patients and in pregnant women.", "populacoes")
    assert has_cues("Contraindicated in severe renal failure; bleeding risk was higher.", "alertas")
    assert not has_cues("A randomized trial of 200 adults.", "populacoes")


# ------------------------------------------------------------------ tipo de estudo
def test_study_type_labels_translate_official_types_and_drop_generic_ones():
    labels = study_type_labels(["Journal Article", "Randomized Controlled Trial", "Research Support, Non-U.S. Gov't",
                                "Multicenter Study", "Some New Type", "randomized controlled trial"])
    assert labels == ["Ensaio clínico randomizado", "Estudo multicêntrico", "Some New Type"]
    assert study_type_labels([]) == [] and study_type_labels(["Journal Article"]) == []


# ------------------------------------------------------------------ regressao: abstract real (PMID 33984217)
REAL_ES = (
    "Objetivo. Identificar factores demográficos y clínicos asociados con la mortalidad por dengue grave en cinco "
    "departamentos de Colombia. Material y métodos. Análisis secundario de un estudio de casos y controles basado en "
    "pacientes admitidos de 2009 a 2013. Se utilizó el procedimiento de Mantel-Haenszel para identificar los factores. "
    "Resultados. Analizando 58 casos y 121 controles, cuatro factores fueron asociados con la mortalidad: "
    "administración hospitalaria de dipirona (RMa=6.38 IC95% 2.41-16.86) y de acetaminofén (RMa=0.25 IC95% 0.10-0.61). "
    "Conclusiones. La administración de dipirona en pacientes con dengue grave se asoció con un aumento del riesgo."
)


def test_period_style_labels_in_spanish_abstracts_are_split():
    sections = split_sections(REAL_ES)
    assert [s.heading for s in sections] == ["Objetivo", "Métodos", "Resultados", "Conclusões"]
    assert sections[1].label == "Material y métodos" and sections[0].text.startswith("Identificar factores")
    assert all(s.text in REAL_ES for s in sections)


def test_dotted_labels_need_three_labels_to_avoid_false_positives():
    assert split_sections("Objetivo. Avaliar o efeito. Resultados. Houve melhora clínica significativa.") == []


def test_spanish_odds_ratio_and_ic95_are_recognised_and_ci_label_is_not_a_percentage():
    findings = extract_findings(REAL_ES)
    tags = next(f.tags for f in findings if "RMa=6.38" in f.sentence)
    assert {"tamanho da amostra", "medida de efeito", "intervalo de confiança"} <= set(tags)
    assert "percentual" not in tags  # o "95%" de "IC95%" e rotulo do intervalo


def test_real_percentages_are_still_detected_next_to_a_confidence_interval():
    tags = next(f.tags for f in extract_findings("Risk fell by 18% (95% CI 0.7-0.9).") if True)
    assert {"percentual", "intervalo de confiança"} <= set(tags)


def test_spanish_vocabulary_is_covered_for_the_main_topics():
    assert has_cues("La dipirona fue retirada del mercado por sus efectos secundarios.", "reacoes")
    assert has_cues("Se observaron reacciones adversas graves.", "reacoes")
    assert has_cues("Dosis de 500 mg por vía oral cada 12 horas.", "dose")
    assert has_cues("Se describe una interacción con la warfarina.", "interacoes")
    assert has_cues("Los ancianos y las embarazadas tuvieron mayor riesgo.", "populacoes")
    assert has_cues("Existe un riesgo de mortalidad aumentado.", "alertas")
    assert extract_passages(REAL_ES + " Se puede desaconsejar su uso en el manejo del dengue.", "conduta")


def test_hyphenation_artifacts_in_source_text_do_not_hide_the_adverse_effects_cue():
    assert has_cues("fue retirada por sus efectos secunda-rios.", "reacoes")
