"""Invariantes da especificacao declarativa das abas (pages.py)."""

from collections import Counter

import pytest

import pages
import prompt_builders
from config import Settings

PAGES = list(pages.ALL_PAGES)


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.key)
def test_no_two_buttons_share_a_prompt_builder(page):
    """Regressao dos 'botoes falsos': cada botao deve ter prompt proprio."""
    counts = Counter(button.builder for button in page.buttons())
    duplicated = [b.__name__ for b, n in counts.items() if n > 1]
    assert not duplicated, f"builders reutilizados em {page.key}: {duplicated}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.key)
def test_button_labels_and_ids_are_unique(page):
    everything = [*page.buttons(), *page.citation_buttons()]
    assert len({b.label for b in everything}) == len(everything)
    ids = [b.id for b in everything]
    assert len(ids) == len(set(ids)) and all(i and i == i.lower() and " " not in i for i in ids)


def test_slugify_strips_accents_and_symbols():
    assert pages.slugify("Questões de Discussão") == "questoes-de-discussao"
    assert pages.slugify("Medicamentos / Protocolos") == "medicamentos-protocolos"


def test_every_prompt_builder_is_reachable_from_some_page():
    used = {b.builder for page in PAGES for b in page.buttons()}
    internal = {
        prompt_builders.build_message_auditoria_resposta,
        prompt_builders.build_message_comparacao_artigos,
    }
    all_builders = {
        fn for name, fn in vars(prompt_builders).items() if name.startswith("build_message_") and callable(fn)
    }
    assert all_builders - used - internal == set(), "builder morto: nenhum botao o utiliza"


def test_medical_page_is_clinical_and_general_is_not():
    assert pages.MEDICAL_PAGE.clinical and not pages.GENERAL_PAGE.clinical


def test_brazil_context_buttons_declare_verification_sources():
    sources = {b.label: b.sources for b in pages.MEDICAL_PAGE.buttons() if b.sources}
    assert len(sources) == 3


def test_page_keys_and_tab_names_are_unique():
    assert len({p.key for p in PAGES}) == len(PAGES)
    assert len({p.tab_name for p in PAGES}) == len(PAGES)


def test_page_title_drops_leading_symbol():
    assert pages.ACADEMIC_PAGE.title == "Acadêmico"
    assert pages.MEDICAL_PAGE.title == "Medicina"
    assert all(p.title and p.title[0].isalpha() for p in PAGES)


def test_expected_tabs_are_present():
    assert {p.key for p in PAGES} == {
        "geral", "academico", "medicina", "ambiental", "saude_publica", "tecnologia", "engenharias",
    }


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.key)
def test_every_page_has_exactly_one_audit_button(page):
    assert sum(section.audit_button for section in page.sections) == 1


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.key)
def test_health_pages_are_flagged_clinical(page):
    assert page.clinical == (page.key in {"medicina", "saude_publica"})


def test_general_page_no_longer_has_educational_section():
    assert "Educacional" not in [s.title for s in pages.GENERAL_PAGE.sections]


def test_academic_page_owns_educational_and_citation_buttons():
    labels = {b.label for b in pages.ACADEMIC_PAGE.buttons()}
    assert {"Explicação para Iniciantes", "Guia para Estudantes", "Glossário de Termos", "Questões de Discussão"} <= labels
    assert [c.style for c in pages.ACADEMIC_PAGE.citation_buttons()] == ["ABNT", "APA", "Vancouver"]
    assert all(not p.citation_buttons() for p in PAGES if p.key != "academico")


def test_default_model_is_a_known_choice():
    assert pages.DEFAULT_MODEL in pages.MODEL_CHOICES


def test_settings_validation(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "abc")
    with pytest.raises(ValueError):
        Settings.from_env()
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
    with pytest.raises(ValueError):
        Settings.from_env()
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "20")
    assert Settings.from_env().llm_calls_per_minute == 20


def test_production_requires_a_strong_session_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    with pytest.raises(ValueError, match="SESSION_SECRET"):
        Settings.from_env()
    monkeypatch.setenv("SESSION_SECRET", "x" * 32)
    settings = Settings.from_env()
    assert settings.production and "xxxx" not in repr(settings)
