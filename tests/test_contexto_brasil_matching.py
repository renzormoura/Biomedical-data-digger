"""Contexto do Brasil: casamento por palavra inteira, rotulos honestos e anexo que so diz que o site respondeu."""

from unittest.mock import MagicMock, patch

import pytest

import contexto_brasil as cb
import presentation


def itens(texto):
    return [i.item for i in cb.selecionar_contexto(texto)]


@pytest.mark.parametrize("texto", [
    "A randomized trial of drug X versus placebo in adults with hypertension.",  # "versus" continha "sus "
    "Bacterial isolates were susceptible to the antibiotic in vitro.",
    "Sustained release formulation and suspected adverse events.",
    "Deep learning for image segmentation of satellite data.",
])
def test_sus_nao_e_injetado_em_artigos_sem_relacao(texto):
    assert "SUS" not in itens(texto)


def test_renal_nao_casa_com_adrenal_mas_casa_com_a_palavra_inteira():
    assert itens("Adrenal insufficiency in critically ill patients.") == []
    assert "Populacoes Especiais" in itens("Dosing in patients with renal impairment.")


@pytest.mark.parametrize("texto", [
    "Avaliamos a disponibilidade do medicamento no SUS em municípios do Nordeste.",
    "Estudo sobre o Sistema Único de Saúde.",
    "Impacto na saúde pública brasileira.",
    "Unified health system coverage in Brazil.",
])
def test_conceito_do_sus_continua_casando_com_acentos_e_sinonimos(texto):
    assert "SUS" in itens(texto)


def test_sinonimos_em_ingles_dos_outros_conceitos():
    assert "Vigilancia Sanitaria" in itens("Surveillance of an outbreak of measles.")
    assert "Medicamento Generico" in itens("Bioequivalence of a generic drug.")
    assert "Populacoes Especiais" in itens("Safety in pregnant and elderly patients.")


def test_catalogo_e_registro_nao_afirmam_revisao_por_especialista():
    for source in cb.VERIFICATION_SOURCES.values():
        assert "pendente de revisão" in source["updated"]
    for item in cb.CONTEXTO_REGISTRY.values():
        assert "pendente de revisão" in item.atualizado
    assert "mantidos por especialistas" not in (cb.__doc__ or "")


def test_conass_descrito_corretamente_e_sem_erro_de_grafia():
    conass = cb.VERIFICATION_SOURCES["conass"]
    assert "Secretários de Saúde" in conass["name"] and "Secretarios" in conass["note"]
    assert "radiao" not in cb.CONTEXTO_REGISTRY["VIGILANCIA_SANITARIA"].contexto


def test_anexo_diz_que_so_o_site_respondeu_e_nao_confirma_a_afirmacao():
    fake = MagicMock()
    fake.verificar_fontes.return_value = [
        {"status": "ok", "url": "https://www.gov.br/anvisa/pt-br"},
        {"status": "nao_verificavel", "motivo": "timeout", "url": "https://www.gov.br/saude/pt-br"},
    ]
    with patch.object(cb, "get_verificacao", return_value=fake):
        anexo = presentation.verification_annex_md(["anvisa", "minsaude"])
    assert "site respondeu" in anexo and "sem resposta" in anexo and "timeout" in anexo
    assert "não confirma" in anexo and "confira diretamente" in anexo
    assert "revisão" not in anexo and "acessível" not in anexo  # nada que sugira checagem do conteudo
