"""Fabrica de prompts e integridade das especificacoes das abas de area."""

import pytest

import contexto_brasil
import pages
import prompt_builders
import prompt_specs
from prompt_builders import build_dynamic_sys_prompt, make_builder
from workflow import wrap_source

SPECS = list(prompt_specs.ALL_SPECS)


def test_every_spec_has_a_published_builder_with_matching_name():
    for spec in SPECS:
        builder = getattr(prompt_builders, f"build_message_{spec.name}", None)
        assert builder is not None and builder.__name__ == f"build_message_{spec.name}"


def test_spec_names_are_unique():
    names = [spec.name for spec in SPECS]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.name)
def test_generated_prompt_contains_structure_note_and_source_restriction(spec):
    user = make_builder(spec)(wrap_source("T", "titulo"), wrap_source("A", "abstract"))[1]["content"]
    assert "Estruture a resposta em:" in user
    assert "1. " in user and f"{len(spec.sections)}. " in user
    assert "Restrição absoluta" in user and "Não descrito no resumo fornecido" in user
    if spec.note:
        assert spec.note in user


@pytest.mark.parametrize("spec", SPECS, ids=lambda s: s.name)
def test_specs_never_ask_for_external_knowledge(spec):
    text = " ".join((spec.role, spec.task, *spec.sections, spec.note)).lower()
    assert "conhecimento externo" not in text or "não use conhecimento externo" in text


def test_clinical_extractions_carry_a_use_warning():
    for name in ("interacoes_medicamentosas", "reacoes_adversas"):
        user = getattr(prompt_builders, f"build_message_{name}")("t", "a")[1]["content"]
        assert "AVISO DE USO CLÍNICO" in user


def test_audience_and_focus_choices_of_every_page_are_known_to_the_prompt():
    audiences = set(prompt_builders.PUBLICO_MAP)
    focuses = set(prompt_builders.FOCO_MAP)
    for page in pages.ALL_PAGES:
        assert set(page.audience_choices) <= audiences, page.key
        assert set(page.focus_choices) <= focuses, page.key


def test_every_page_filter_changes_the_system_prompt():
    for page in pages.ALL_PAGES:
        base = build_dynamic_sys_prompt("", "", "", "", "")
        for audience in page.audience_choices:
            assert build_dynamic_sys_prompt(audience, "", "", "", "") != base
        for focus in page.focus_choices:
            assert build_dynamic_sys_prompt("", "", "", "", focus) != base


def test_every_verification_source_used_by_pages_exists_in_catalog():
    for page in pages.ALL_PAGES:
        for button in page.buttons():
            for key in button.sources:
                assert key in contexto_brasil.VERIFICATION_SOURCES, f"{page.key}/{button.label}: {key}"


def test_environmental_sources_are_flagged_as_pending_review():
    for key in ("mma", "ibama", "conama", "ods"):
        assert "pendente" in contexto_brasil.VERIFICATION_SOURCES[key]["updated"]
