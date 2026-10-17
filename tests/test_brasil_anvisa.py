"""ANVISA: leitor do CSV aberto, agregacao por substancia, instantaneo versionado, nomes e rotas."""

import csv
import io
import json
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi.testclient import TestClient

from brasil import anvisa, anvisa_build, conitec, consulta
from brasil.nomes import AMBIGUOS, dobrar, encontrar, limpar_substancia, normalizar
from catalog import Work
from config import Settings
from db import Database
from discovery import DiscoveryService
from library_store import LibraryStore
from ratelimit import SlidingWindowLimiter
from web import create_app
from workflow import AnalysisService, ArticleRepository

COLUMNS = ["TIPO_PRODUTO", "NOME_PRODUTO", "DATA_FINALIZACAO_PROCESSO", "CATEGORIA_REGULATORIA", "NUMERO_REGISTRO_PRODUTO",
           "DATA_VENCIMENTO_REGISTRO", "NUMERO_PROCESSO", "CLASSE_TERAPEUTICA", "EMPRESA_DETENTORA_REGISTRO", "SITUACAO_REGISTRO",
           "PRINCIPIO_ATIVO"]


def make_csv(rows, columns=COLUMNS):
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";", quotechar='"', quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(row)
    return out.getvalue().encode("cp1252")


def row(nome, ativo, situacao="Ativo", categoria="Genérico", venc="092030", empresa="1 - EMPRESA A", classe="ANTIDIABETICOS"):
    return ["MEDICAMENTO", nome, "01/01/2020", categoria, "1", venc, "2", classe, empresa, situacao, ativo]


ROWS = [
    row("GLIFAGE", "cloridrato de metformina"),
    row("GLUCOFORMIN", "cloridrato de metformina", categoria="Similar", venc="122035", empresa="2 - EMPRESA B"),
    row("VELHO", "cloridrato de metformina", situacao="Inativo", venc="012010"),
    row("JANUMET", "fosfato de sitagliptina, cloridrato de metformina", categoria="Novo", empresa="3 - EMPRESA C"),
    row("SORO", "cloreto de sódio", categoria="Específico", classe="REPOSICAO"),
    row("ATORVA", "atorvastatina cálcica", classe="ANTILIPEMICOS"),
    row("SEM", ""),  # registro sem principio ativo
    ["PRODUTO", "NAO MEDICAMENTO", "", "", "", "", "", "", "", "Ativo", "algo"],
    row("ASSOC", "cynara scolymus + associações", categoria="Fitoterápico"),
]


# ------------------------------------------------------------------ leitura e agregacao
def test_reader_decodes_cp1252_and_rejects_changed_formats():
    lines = anvisa_build.ler_csv(make_csv(ROWS))
    assert len(lines) == len(ROWS) and lines[4]["PRINCIPIO_ATIVO"] == "cloreto de sódio"
    with pytest.raises(anvisa_build.AnvisaError, match="mudou de formato"):
        anvisa_build.ler_csv(make_csv([], columns=["A", "B"]))


def test_components_strip_salts_forms_and_ignore_associations():
    assert anvisa_build.componentes("cloridrato de metformina") == ["metformina"]
    assert anvisa_build.componentes("fosfato de sitagliptina, cloridrato de metformina") == ["sitagliptina", "metformina"]
    assert anvisa_build.componentes("atorvastatina cálcica") == ["atorvastatina"]
    assert anvisa_build.componentes("cloreto de sódio") == ["cloreto de sódio"]  # sal de elemento preserva o nome inteiro
    assert anvisa_build.componentes("cynara scolymus + associações") == ["cynara scolymus"]
    assert anvisa_build.componentes("") == [] and anvisa_build.componentes("oxalato de escitalopram") == ["escitalopram"]


def test_aggregation_counts_active_inactive_categories_validity_and_companies():
    items, stats = anvisa_build.agregar(anvisa_build.ler_csv(make_csv(ROWS)))
    by_key = {i["chave"]: i for i in items}
    met = by_key["metformina"]
    assert (met["ativos"], met["inativos"], met["ativos_isolado"]) == (3, 1, 2)  # JANUMET e associacao, nao conta como isolado
    assert met["categorias"] == {"Genérico": 1, "Similar": 1, "Novo": 1} and met["empresas"] == 3
    assert met["validade_max"] == "2035-12" and met["classes"] == ["Antidiabeticos"]
    assert by_key["sitagliptina"]["ativos_isolado"] == 0 and by_key["cloreto de sodio"]["categorias"] == {"Específico": 1}
    assert stats == {"linhas": 9, "sem_principio_ativo": 1, "ativos": 6}  # o produto que nao e medicamento nao entra
    assert "associacoes" not in by_key and by_key["cynara scolymus"]["categorias"] == {"Fitoterápico": 1}


def test_validity_and_category_helpers():
    assert anvisa_build._validade("092030") == "2030-09" and anvisa_build._validade("") == "" and anvisa_build._validade("132030") == ""
    assert anvisa_build._categoria("FITOTER?PICO") == "Fitoterápico" and anvisa_build._categoria("") == "Sem categoria"
    assert anvisa_build._categoria("baixo risco") == "Baixo risco" and anvisa_build._categoria("Biológico") == "Biológico"


def test_snapshot_refuses_suspiciously_small_reads():
    with pytest.raises(anvisa_build.AnvisaError, match="Leitura suspeita"):
        anvisa_build.montar_instantaneo(anvisa_build.ler_csv(make_csv(ROWS)), arquivo_modificado="2026-10-13")


# ------------------------------------------------------------------ download
def test_download_checks_host_retries_and_parses_last_modified():
    with pytest.raises(anvisa_build.AnvisaError, match="fora do dominio"):
        anvisa_build.baixar("https://evil.example/x.csv")
    with pytest.raises(anvisa_build.AnvisaError, match="fora do dominio"):
        anvisa_build.baixar("http://dados.anvisa.gov.br/dados/x.csv")
    ok = MagicMock(content=b"dados", headers={"Last-Modified": "Tue, 13 Oct 2026 19:10:26 GMT"})
    ok.raise_for_status.return_value = None
    bad = MagicMock(content=b"")
    bad.raise_for_status.side_effect = requests.HTTPError("500")
    with patch.object(anvisa_build.requests, "get", side_effect=[bad, ok]) as get, patch.object(anvisa_build.time, "sleep"):
        assert anvisa_build.baixar() == (b"dados", "2026-10-13") and get.call_count == 2
    with patch.object(anvisa_build.requests, "get", return_value=bad), patch.object(anvisa_build.time, "sleep"), \
            pytest.raises(anvisa_build.AnvisaError, match="Nao foi possivel baixar"):
        anvisa_build.baixar(tentativas=2)


# ------------------------------------------------------------------ instantaneo versionado
def test_committed_snapshot_is_complete_and_consistent():
    snap = anvisa.carregar()
    meta = snap.meta
    assert str(meta["arquivo_url"]).startswith("https://dados.anvisa.gov.br/") and meta["substancias"] == len(snap.substancias) >= 3000
    assert meta["registros_ativos"] >= 50000 and date.fromisoformat(str(meta["extraido_em"])) <= date.today()
    for chave in ("metformina", "paracetamol", "atorvastatina", "dapagliflozina", "insulina humana"):
        item = snap.substancias[chave]
        assert item.ativos > 0 and item.empresas > 0 and item.validade_max[:2] == "20", chave
    assert snap.substancias["metformina"].ativos_isolado <= snap.substancias["metformina"].ativos


def test_search_exact_first_then_whole_word_matches():
    found = anvisa.buscar("Insulina")
    assert found and all("insulina" in s.chave.split() for s in found)
    exact = anvisa.buscar("metformina")
    assert exact[0].chave == "metformina" and all(" " in s.chave or s.chave == "metformina" for s in exact[1:3])
    assert anvisa.buscar("ab") == [] and anvisa.buscar("zzzinexistente") == [] and anvisa.buscar("metformin") == []  # palavra inteira


def test_staleness_helper():
    snap = anvisa.carregar()
    extracted = date.fromisoformat(str(snap.meta["extraido_em"]))
    assert anvisa.dias_desde_extracao(snap, hoje=extracted) == 0
    assert anvisa.dias_desde_extracao(snap, hoje=date(extracted.year + 1, extracted.month, 1)) > anvisa.STALE_AFTER_DAYS


# ------------------------------------------------------------------ nomes
def test_folding_and_salt_cleaning_helpers():
    assert dobrar("ampicillin") == "ampicilin" and dobrar("morphine") == "morfine" and dobrar("thyroxine") == "tiroxine"
    assert limpar_substancia("Dicloridrato de pramipexol") == "pramipexol" and limpar_substancia("cloreto de sódio") == "cloreto de sódio"
    assert limpar_substancia("Testosterona injetável") == "Testosterona" and normalizar("Ácido Fólico!") == "acido folico"


def pares(texto):
    return {(c.pt, c.en, c.metodo) for c in consulta.situacoes_do_texto(texto, anvisa.carregar(), conitec.carregar()) and
            encontrar(texto, consulta.vocabulario(anvisa.carregar(), conitec.carregar()), limite=8)}


def test_english_spellings_reach_portuguese_names_without_a_synonym_table():
    found = {(en, pt) for pt, en, _ in pares("Ampicillin, piperacillin and morphine; buprenorphine versus methadone; ketamine.")}
    assert {("ampicillin", "Ampicilina"), ("piperacillin", "Piperacilina"), ("morphine", "Morfina"), ("buprenorphine", "Buprenorfina"),
            ("methadone", "Metadona"), ("ketamine", "Cetamina")} <= found


def test_similar_but_different_drugs_are_not_confused():
    assert not any(en == "valganciclovir" and pt.lower().startswith("valaciclovir") for pt, en, _ in pares("Valganciclovir prophylaxis."))
    assert "valaciclovir" not in {en for _, en, _ in pares("Valganciclovir prophylaxis.")}


@pytest.mark.parametrize("texto", [
    "Serum glucose, sodium, potassium and creatinine were measured; phosphorus and sulfur levels rose.",
    "Dimethyl groups and sulphate ions in water and oxygen were analysed.",
    "Haemolyticus strains were isolated.",
])
def test_labs_elements_and_common_chemistry_words_never_become_drug_candidates(texto):
    assert pares(texto) == set()
    assert {"glicose", "sodio", "phosphorus", "sulphur"} <= AMBIGUOS


# ------------------------------------------------------------------ rotas
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
    works = [Work(ref="1", title="Metformin in diabetes", abstract="Metformin and dapagliflozin and aspirin were compared.", source="Europe PMC"),
             Work(ref="2", title="Hip surgery", abstract="Rehabilitation after hip fracture surgery.", source="Europe PMC")]
    discovery = DiscoveryService([Catalog(works)], SlidingWindowLimiter(100, 60), fallback=None)
    repository = ArticleRepository(lambda raw: ("T", "Resumo suficiente para o teste.", "s"))
    service = AnalysisService(repository, MagicMock(), SlidingWindowLimiter(50, 60))
    app = create_app(service, repository, Settings(session_secret="k" * 40), search_fn=lambda *a, **k: [], discovery=discovery, library=library)
    return TestClient(app, base_url="http://testserver")


def test_article_route_combines_anvisa_and_conitec_per_candidate(client):
    data = client.get("/api/discover/brasil", params={"ref": "1"}).json()
    by_pt = {c["pt"].lower(): c for c in data["candidatos"]}
    assert {"metformina", "dapagliflozina", "ácido acetilsalicílico"} <= set(by_pt)
    met = by_pt["metformina"]
    assert met["en"] == "metformin" and met["metodo"] == "cognato" and met["anvisa"][0]["key"] == "metformina"
    assert met["anvisa"][0]["active"] > 100 and set(met["anvisa"][0]) >= {"inactive", "activeAlone", "categories", "classes", "companies", "validUntil"}
    assert by_pt["dapagliflozina"]["conitec"] and by_pt["ácido acetilsalicílico"]["anvisa"]
    assert set(data["meta"]) == {"anvisa", "conitec"} and data["meta"]["anvisa"]["arquivoUrl"].startswith("https://dados.anvisa.gov.br/")
    assert client.get("/api/discover/brasil", params={"ref": "2"}).json()["candidatos"] == []


def test_manual_lookup_route_accepts_accents_and_unknown_names(client):
    data = client.get("/api/brasil/medicamento", params={"q": "Ácido Acetilsalicílico"}).json()
    assert data["anvisa"] and data["conitec"] and data["meta"]["conitec"]["medicamentos"] >= 500
    unknown = client.get("/api/brasil/medicamento", params={"q": "zzzinexistente"}).json()
    assert unknown["anvisa"] == [] and unknown["conitec"] == []
    assert client.get("/api/brasil/medicamento", params={"q": "ab"}).status_code == 422
    assert json.dumps(unknown)  # serializavel


def test_routes_degrade_when_the_anvisa_snapshot_is_missing(client):
    with patch.object(anvisa, "carregar", side_effect=FileNotFoundError("sem arquivo")):
        assert client.get("/api/brasil/medicamento", params={"q": "aspirina"}).status_code == 503
        assert client.get("/api/discover/brasil", params={"ref": "1"}).status_code == 503
