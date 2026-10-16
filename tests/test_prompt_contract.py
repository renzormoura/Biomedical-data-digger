"""Contrato comum a todos os builders de prompt."""

import inspect

import pytest

import prompt_builders
from workflow import wrap_source

TITLE = wrap_source("SOURCE_TITLE", "Metformin and outcomes")
ABSTRACT = wrap_source("SOURCE_ABSTRACT", "A randomized trial of 120 patients.")

BUILDERS = sorted(
    (name, fn)
    for name, fn in vars(prompt_builders).items()
    if name.startswith("build_message_")
    and name not in {"build_message_auditoria_resposta", "build_message_comparacao_artigos"}
)


@pytest.mark.parametrize("name,builder", BUILDERS, ids=[n for n, _ in BUILDERS])
def test_builder_returns_system_then_user_with_source_embedded(name, builder):
    messages = builder(TITLE, ABSTRACT)
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "<<<SOURCE_TITLE_START>>>" in messages[1]["content"]
    assert "<<<SOURCE_ABSTRACT_START>>>" in messages[1]["content"]


@pytest.mark.parametrize("name,builder", BUILDERS, ids=[n for n, _ in BUILDERS])
def test_builder_uses_the_system_prompt_it_is_given(name, builder):
    assert builder(TITLE, ABSTRACT, sys_prompt="CUSTOM")[0]["content"] == "CUSTOM"


@pytest.mark.parametrize("name,builder", BUILDERS, ids=[n for n, _ in BUILDERS])
def test_builder_states_source_only_constraint(name, builder):
    content = builder(TITLE, ABSTRACT)[1]["content"].lower()
    assert any(marker in content for marker in ("restrição absoluta", "somente", "exclusivamente", "apenas")), (
        f"{name} deveria restringir a resposta à fonte"
    )


@pytest.mark.parametrize("name,builder", BUILDERS, ids=[n for n, _ in BUILDERS])
def test_builder_signature_is_uniform(name, builder):
    parameters = list(inspect.signature(builder).parameters)
    assert parameters[:2] == ["article_title", "abstract_text"] and "sys_prompt" in parameters


def test_system_prompt_defends_against_injected_instructions():
    text = prompt_builders.SYS_PROMPT
    assert "untrusted" in text and "Não descrito no resumo fornecido" in text


def test_dynamic_prompt_ignores_empty_filters_and_applies_selected_ones():
    base = prompt_builders.build_dynamic_sys_prompt("", "", "", "", "")
    custom = prompt_builders.build_dynamic_sys_prompt("Estudante", "Didático", "", "", "")
    assert base.strip() == prompt_builders.SYS_PROMPT.strip()
    assert len(custom) > len(base)
