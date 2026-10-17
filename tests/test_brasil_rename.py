"""RENAME 2024: extracao do texto do PDF, instantaneo versionado, consulta e rotas."""

import json
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi.testclient import TestClient

from brasil import consulta, rename, rename_build
from catalog import Work
from config import Settings
from db import Database
from discovery import DiscoveryService
from library_store import LibraryStore
from ratelimit import SlidingWindowLimiter
from web import create_app
from workflow import AnalysisService, ArticleRepository

CABECALHO = (
    "| 25RELAÇÃO NACIONAL DE MEDICAMENTOS ESSENCIAIS | RENAME 2024\nA: Aparelho digestivo e metabolismo\n"
    "Denominação Comum \nBrasileira (DCB)\nConcentração/\nComposição Forma Farmacêutica \nComponente de \nFinanciamento \n"
    "da Assistência \nFarmacêutica\nCódigo ATC\n"
)
PAGINA = CABECALHO + (
    "cloridrato de \nmetoclopramida\n10 mg comprimido Básico A03FA01\n5 mg/mL solução injetável Básico A03FA01\n"
    "succinato sódico de \nmetilprednisolona 500 mg pó para solução injetável\nEspecializado e \nProcedimento \nHospitalar(1)\nH02AB04\n"
    "amoxicilina\n500 mg cápsula Básico J01CA04 Acesso\nalfa-agalsidase 1 mg/mL solução injetável Especializado A16AB03\n"
    "seringas para insulina - unidade Insumos (Básico) NC\ncontinua\n"
)


def textos(*paginas):
    vazio = [""] * rename_build.PRIMEIRA_PAGINA
    return vazio + list(paginas)


def test_extrair_reads_names_presentations_components_and_atc():
    itens = rename_build.extrair(textos(PAGINA))
    por_nome = {}
    for item in itens:
        por_nome.setdefault(item["nome"], []).append(item)
    assert [i["apresentacao"] for i in por_nome["cloridrato de metoclopramida"]] == ["10 mg comprimido", "5 mg/mL solução injetável"]
    assert por_nome["cloridrato de metoclopramida"][1]["atc"] == "A03FA01" and por_nome["cloridrato de metoclopramida"][0]["pagina"] == 26
    metilpred = por_nome["succinato sódico de metilprednisolona"][0]
    assert metilpred["componente"] == "Especializado e Procedimento Hospitalar" and metilpred["atc"] == "H02AB04"
    assert por_nome["amoxicilina"][0]["atc"] == "J01CA04"  # a coluna AWaRe ("Acesso") nao vira nome do proximo item
    assert "alfa-agalsidase" in por_nome
    assert all(not i["nome"].lower().startswith("seringas") for i in itens)  # insumos nao sao medicamentos


@pytest.mark.parametrize("nome,chave", [
    ("cloridrato de metformina", "metformina"),
    ("succinato sódico de metilprednisolona", "metilprednisolona"),
    ("alcachofra (Cynara scolymus L.)", "alcachofra"),
    ("vacina influenza trivalente (fragmentada", "vacina influenza trivalente"),
    ("ácido acetilsalicílico", "acido acetilsalicilico"),
])
def test_chave_do_nome_strips_salts_and_scientific_names(nome, chave):
    assert rename_build.chave_do_nome(nome) == chave


def test_montar_instantaneo_records_meta_and_refuses_empty_extraction():
    itens = rename_build.extrair(textos(PAGINA))
    snap = rename_build.montar_instantaneo(itens, paginas_pdf=267, agora=datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert snap["meta"]["extraido_em"] == "2026-10-01" and snap["meta"]["paginas_pdf"] == 267 and "CC BY-NC-SA" in snap["meta"]["licenca"]
    assert snap["meta"]["itens"] == len(snap["itens"]) and snap["meta"]["substancias"] == 4
    with pytest.raises(rename_build.RenameError):
        rename_build.montar_instantaneo([], paginas_pdf=1)


def test_salvar_and_carregar_roundtrip(tmp_path):
    snap = rename_build.montar_instantaneo(rename_build.extrair(textos(PAGINA)), paginas_pdf=3)
    caminho = rename_build.salvar(snap, tmp_path / "sub" / "rename.json")
    data = rename.carregar(str(caminho))
    metoclopramida = rename.buscar("metoclopramida", instantaneo=data)[0]
    assert metoclopramida.componentes == ("Básico",) and len(metoclopramida.apresentacoes) == 2
    assert rename.buscar("ab", instantaneo=data) == [] and rename.buscar("inexistente", instantaneo=data) == []
    assert "metoclopramida" in data.vocabulario  # chaves curtas ficam fora do vocabulario de busca no texto
    assert rename.dias_desde_extracao(data, date(2999, 1, 1)) > 1000
    data.meta["extraido_em"] = "x"
    assert rename.dias_desde_extracao(data) is None


def test_baixar_refuses_other_hosts_and_reports_failures():
    with pytest.raises(rename_build.RenameError):
        rename_build.baixar("https://exemplo.com/rename.pdf")
    with patch("brasil.rename_build.requests.get", side_effect=requests.ConnectionError("x")), patch("brasil.rename_build.time.sleep"):
        with pytest.raises(rename_build.RenameError):
            rename_build.baixar(tentativas=2)
    grande = MagicMock(content=b"x" * (rename_build.MAX_BYTES + 1))
    with patch("brasil.rename_build.requests.get", return_value=grande):
        with pytest.raises(rename_build.RenameError, match="maior"):
            rename_build.baixar()
    ok = MagicMock(content=b"%PDF")
    with patch("brasil.rename_build.requests.get", return_value=ok):
        assert rename_build.baixar() == b"%PDF"


def test_paginas_rejects_unreadable_pdf():
    with pytest.raises(rename_build.RenameError):
        rename_build.paginas(b"isto nao e um pdf")


def test_atualizar_writes_snapshot(tmp_path):
    with patch("brasil.rename_build.baixar", return_value=b""), patch("brasil.rename_build.paginas", return_value=textos(PAGINA)):
        snap = rename_build.atualizar(tmp_path / "r.json")
    assert snap["meta"]["itens"] >= 5 and (tmp_path / "r.json").exists()


def test_committed_snapshot_is_consistent_and_covers_known_drugs():
    data = rename.carregar()
    assert data.meta["itens"] > 900 and data.meta["substancias"] > 450 and data.meta["paginas_pdf"] == 267
    assert rename.buscar("metformina")[0].componentes == ("Básico",)
    assert rename.buscar("ácido acetilsalicílico")[0].apresentacoes
    assert any("Especializado" in r.componentes for r in rename.buscar("adalimumabe"))
    assert all(r.apresentacoes and r.atc for r in data.registros.values())
    assert rename.candidatos("Patients received metformin and amoxicillin daily.")[0].pt


def test_situacao_includes_rename_when_given(tmp_path):
    from brasil import anvisa, conitec

    a, c, r = anvisa.carregar(), conitec.carregar(), rename.carregar()
    com = consulta.situacao("metformina", a, c, rename_data=r)
    sem = consulta.situacao("metformina", a, c)
    assert com.rename and sem.rename == ()
    assert "metformina" in consulta.vocabulario(a, c, r)
    achados = consulta.situacoes_do_texto("Metformin was compared with placebo.", a, c, r)
    assert achados and achados[0].rename


class Catalog:
    id, name = "europepmc", "Europe PMC (x)"

    def __init__(self, works):
        self._works = {w.ref: w for w in works}

    def study_types(self):
        return ()

    def search(self, query):
        raise AssertionError("nao deve buscar")

    def get(self, ref):
        return self._works.get(ref)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "a.sqlite3"))
    library = LibraryStore(Database(database_url="", sqlite_path=str(tmp_path / "a.sqlite3")))
    library.initialize()
    works = [Work(ref="1", title="Metformin in diabetes", abstract="Metformin and amoxicillin were compared.", source="Europe PMC")]
    discovery = DiscoveryService([Catalog(works)], SlidingWindowLimiter(100, 60), fallback=None)
    repository = ArticleRepository(lambda raw: ("T", "Resumo suficiente para o teste.", "s"))
    service = AnalysisService(repository, MagicMock(), SlidingWindowLimiter(50, 60))
    app = create_app(service, repository, Settings(session_secret="k" * 40), search_fn=lambda *a, **k: [], discovery=discovery, library=library)
    return TestClient(app, base_url="http://testserver")


def test_routes_expose_rename_with_meta_and_presentations(client):
    manual = client.get("/api/brasil/medicamento", params={"q": "Metformina"}).json()
    item = manual["rename"][0]
    assert item["components"] == ["Básico"] and item["presentations"][0]["page"] >= 26 and item["totalPresentations"] >= 2
    assert manual["meta"]["rename"]["licenca"].startswith("CC BY-NC-SA") and manual["meta"]["rename"]["defasado"] in (True, False)
    artigo = client.get("/api/discover/brasil", params={"ref": "1"}).json()
    assert any(c["rename"] for c in artigo["candidatos"])
    assert client.get("/api/brasil/medicamento", params={"q": "zzzinexistente"}).json()["rename"] == []


def test_routes_degrade_when_the_rename_snapshot_is_missing(client):
    with patch.object(rename, "carregar", side_effect=FileNotFoundError("sem arquivo")):
        assert client.get("/api/brasil/medicamento", params={"q": "aspirina"}).status_code == 503
    assert json.dumps(rename.carregar().meta)
