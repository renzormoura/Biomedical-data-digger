from grounding import check_numeric_grounding

SOURCE = "Em 1200 pacientes, a mortalidade caiu de 12,5% para 8.1% (p=0.03) com 40 mg/dia."


def test_numbers_present_in_source_are_grounded():
    report = check_numeric_grounding("Mortalidade caiu de 12,5% para 8,1% com 40 mg.", SOURCE)
    assert report.ok
    assert report.to_markdown() == ""


def test_invented_dose_is_flagged():
    report = check_numeric_grounding("Administrar 80 mg a cada 8 h.", SOURCE)
    assert not report.ok
    assert any("80" in item for item in report.ungrounded)
    assert "não foram encontrados" in report.to_markdown()


def test_invented_percentage_and_decimal_are_flagged():
    report = check_numeric_grounding("Redução de 35% e HR 0.72.", SOURCE)
    assert len(report.ungrounded) == 2


def test_list_markers_and_plain_small_integers_are_ignored():
    report = check_numeric_grounding("1. Objetivo\n2. Métodos\n3. Resultados", SOURCE)
    assert report.ok


def test_comma_and_dot_decimals_are_equivalent():
    assert check_numeric_grounding("p=0,03", SOURCE).ok


def test_duplicates_reported_once():
    report = check_numeric_grounding("99% e novamente 99%", SOURCE)
    assert report.ungrounded == ["99%"]
