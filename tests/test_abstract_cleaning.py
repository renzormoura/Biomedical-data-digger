import pytest

from workflow import ArticleRepository, strip_boilerplate

BODY = (
    "Background: Metformin is widely used in type 2 diabetes. Methods: We studied 12,450 adults. "
    "Results: Risk was lower (HR 0.82; 95% CI 0.74-0.91). Conclusions: Metformin was associated with fewer events."
)


@pytest.mark.parametrize(
    "notice",
    [
        "© 2023 The Authors. Published by Elsevier Ltd.",
        "Copyright © 2021 Wiley Periodicals LLC. All rights reserved.",
        "(C) 2019 Oxford University Press.",
        "All rights reserved.",
        "Published by Elsevier Ltd.",
        "This is an open access article under the CC BY license.",
        "Copyright 2020 John Wiley & Sons.",
    ],
)
def test_trailing_notices_are_removed_and_content_is_preserved(notice):
    cleaned = strip_boilerplate(f"{BODY} {notice}")
    assert cleaned == BODY
    assert "©" not in cleaned and "rights" not in cleaned.lower()


def test_numbers_and_statistics_survive_cleaning():
    cleaned = strip_boilerplate(f"{BODY} © 2023 The Authors.")
    assert "HR 0.82; 95% CI 0.74-0.91" in cleaned and "12,450" in cleaned


def test_notice_in_the_first_part_is_never_cut():
    text = "© 2023 note at the start. " + BODY  # aviso no inicio: preserva o conteudo
    assert strip_boilerplate(text) == text


def test_text_mentioning_licensee_early_keeps_everything():
    text = "The licensee study design was novel. " + BODY
    assert strip_boilerplate(text) == text


def test_leading_abstract_label_is_dropped():
    assert strip_boilerplate("Abstract: " + BODY) == BODY
    assert strip_boilerplate("ABSTRACT\n" + BODY) == BODY


def test_clean_text_without_notice_is_unchanged():
    assert strip_boilerplate(BODY) == BODY
    assert strip_boilerplate("") == ""


def test_repository_stores_the_cleaned_abstract_and_rejects_notice_only_abstracts():
    repo = ArticleRepository(lambda raw: ("T", BODY + " © 2023 The Authors. All rights reserved.", "src"))
    assert repo.get("33984217").abstract == BODY
    only_notice = ArticleRepository(lambda raw: ("T", "© 2023 The Authors.", "src"))
    with pytest.raises(Exception, match="Nenhum abstract"):
        only_notice.get("33984217")
