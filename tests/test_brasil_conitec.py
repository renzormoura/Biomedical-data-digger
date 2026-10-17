"""CONITEC: leitor da planilha oficial, instantaneo versionado, casamento de nomes e rotas."""

import io
import json
import zipfile
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import requests
from fastapi.testclient import TestClient

from brasil import conitec, conitec_build
from catalog import Work
from config import Settings
from db import Database
from discovery import DiscoveryService
from library_store import LibraryStore
from ratelimit import SlidingWindowLimiter
from web import create_app
from workflow import AnalysisService, ArticleRepository

HEADER = ["ANO", "TECNOLOGIA AVALIADA E INDICAÇÃO", "RELATÓRIO TÉCNICO", "RELATÓRIO PARA A SOCIEDADE", "RECOMENDAÇÃO DA CONITEC FINAL",
          "DECISÃO DO MS", "PORTARIA", "DATA DA PUBLICAÇÃO", "TIPO", "INDICAÇÃO"]


def make_xlsx(rows, *, inline=False, header=HEADER):
    """XLSX minimo (so o que o leitor usa): primeira aba com cadeias compartilhadas ou em linha."""
    shared = []

    def cell(ref, value):
        if value is None or value == "":
            return f'<c r="{ref}"/>'
        if isinstance(value, (int, float)):
            return f'<c r="{ref}"><v>{value}</v></c>'
        if inline:
            return f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'
        shared.append(value)
        return f'<c r="{ref}" t="s"><v>{len(shared) - 1}</v></c>'

    cols = "ABCDEFGHIJ"
    body = "".join(
        f'<row r="{n}">' + "".join(cell(f"{cols[i]}{n}", v) for i, v in enumerate(row)) + "</row>"
        for n, row in enumerate([header, *rows], start=1)
    )
    sheet = f'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{body}</sheetData></worksheet>'
    strings = "".join(f"<si><t>{v}</t></si>" for v in shared)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
        if not inline:
            archive.writestr("xl/sharedStrings.xml", f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">{strings}</sst>')
    return buffer.getvalue()


ROWS = [
    [2026, "Ácido acetilsalicílico", "Nº 1.126", "Nº 728", "Incorporar", "Incorporar", "SCTIE/MS Nº 53/2026", 46253, "Medicamento", "Prevenção de pré-eclâmpsia"],
    [2025, "Teste molecular para hanseníase", "Nº 1.124", "", "Ampliar", "Ampliar", "SCTIE/MS nº 51/2026", 46238, "Procedimento", "Diagnóstico"],
    [2024, "Rituximabe", "Nº 900", "", "Não Incorporar", "Não incorporar", "SCTIE/MS Nº 1/2024", 45500, "Medicamento", "Lúpus"],
    [2023, "Protocolo Clínico e Diretrizes Terapêuticas", "Nº 1", "", "Aprovar", "Aprovar", "SAES Nº 2/2023", 45000, "Protocolos e Diretrizes", "Endometriose"],
]


# ------------------------------------------------------------------ leitor da planilha
@pytest.mark.parametrize("inline", [False, True])
def test_reader_maps_columns_with_shared_or_inline_strings(inline):
    rows = conitec_build.ler_xlsx(make_xlsx(ROWS, inline=inline))
    assert len(rows) == 4 and rows[0]["tecnologia"] == "Ácido acetilsalicílico" and rows[0]["tipo"] == "Medicamento"
    assert rows[0]["data_publicacao"] == "46253" and rows[1]["relatorio_sociedade"] == ""


def test_reader_rejects_missing_columns_bad_files_and_empty_sheets():
    with pytest.raises(conitec_build.ConitecError, match="faltam as colunas"):
        conitec_build.ler_xlsx(make_xlsx(ROWS, header=["ANO", "TIPO"] + [""] * 8))
    with pytest.raises(conitec_build.ConitecError, match="formato inesperado"):
        conitec_build.ler_xlsx(b"isto nao e um zip")
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData/></worksheet>')
    with pytest.raises(conitec_build.ConitecError, match="vazia"):
        conitec_build.ler_xlsx(empty.getvalue())


def test_excel_serial_dates_and_medicine_filter():
    assert conitec_build.serial_para_data("46253") == "2026-08-19" and conitec_build.serial_para_data("abc") == ""
    meds = conitec_build.registros_medicamentos(conitec_build.ler_xlsx(make_xlsx(ROWS)))
    assert [m["tecnologia"] for m in meds] == ["Ácido acetilsalicílico", "Rituximabe"]  # procedimento e protocolo ficam de fora
    assert meds[1]["recomendacao"] == "Não incorporar" and meds[0]["data_publicacao"] == "2026-08-19" and meds[0]["ano"] == 2026


def test_snapshot_refuses_suspiciously_small_reads_and_sorts_newest_first():
    lines = conitec_build.ler_xlsx(make_xlsx(ROWS))
    with pytest.raises(conitec_build.ConitecError, match="Poucos medicamentos"):
        conitec_build.montar_instantaneo(lines, arquivo_url="https://www.gov.br/x.xlsx", arquivo_data="20260101")
    many = [{**lines[0], "tecnologia": f"Substancia {i}", "data_publicacao": str(40000 + i)} for i in range(120)]
    snap = conitec_build.montar_instantaneo(many, arquivo_url="https://www.gov.br/x.xlsx", arquivo_data="20260101")
    assert snap["meta"]["linhas_medicamento"] == 120 and snap["meta"]["escopo"] == "somente medicamentos"
    assert snap["registros"][0]["tecnologia"] == "Substancia 119"


# ------------------------------------------------------------------ descoberta e download
PAGE = ('<a href="/conitec/pt-br/midias/dados-em-excel/recomendacoesdaconitec_20260101.xlsx/@@download/file">velha</a>'
        '<a href="/conitec/pt-br/midias/dados-em-excel/recomendacoesdaconitec_20260615.xlsx/@@download/file">nova</a>')


def test_discovers_the_latest_file_and_refuses_foreign_hosts():
    url, stamp = conitec_build.descobrir_arquivo(PAGE)
    assert stamp == "20260615" and url.startswith("https://www.gov.br/conitec/pt-br/midias/dados-em-excel/")
    with pytest.raises(conitec_build.ConitecError, match="fora do dominio"):
        conitec_build.descobrir_arquivo('<a href="https://evil.example/recomendacoesdaconitec_20260615.xlsx">x</a>')
    with pytest.raises(conitec_build.ConitecError, match="nao traz o link"):
        conitec_build.descobrir_arquivo("<html></html>")


def test_download_retries_intermittent_errors_and_gives_up_with_a_clear_message():
    ok = MagicMock(content=b"conteudo")
    ok.raise_for_status.return_value = None
    bad = MagicMock(content=b"")
    bad.raise_for_status.side_effect = requests.HTTPError("404")
    with patch.object(conitec_build.requests, "get", side_effect=[bad, bad, ok]) as get, patch.object(conitec_build.time, "sleep"):
        assert conitec_build._get("https://www.gov.br/x") == b"conteudo" and get.call_count == 3
    with patch.object(conitec_build.requests, "get", return_value=bad), patch.object(conitec_build.time, "sleep"), \
            pytest.raises(conitec_build.ConitecError, match="Nao foi possivel baixar"):
        conitec_build._get("https://www.gov.br/x", tentativas=2)
    big = MagicMock(content=b"x" * (conitec_build.MAX_BYTES + 1))
    big.raise_for_status.return_value = None
    with patch.object(conitec_build.requests, "get", return_value=big), pytest.raises(conitec_build.ConitecError, match="grande demais"):
        conitec_build._get("https://www.gov.br/x")


def test_update_writes_the_snapshot_end_to_end(tmp_path):
    many = [[2026, f"Substancia {i}", "Nº 1", "", "Incorporar", "Incorporar", "P", 46000 + i, "Medicamento", "I"] for i in range(120)]
    with patch.object(conitec_build, "baixar_planilha", return_value=(make_xlsx(many), "https://www.gov.br/f.xlsx", "20260615")):
        snapshot = conitec_build.atualizar(tmp_path / "out" / "conitec.json")
    saved = json.loads((tmp_path / "out" / "conitec.json").read_text(encoding="utf-8"))
    assert saved["meta"]["arquivo_data"] == "20260615" and len(saved["registros"]) == 120 == snapshot["meta"]["linhas_medicamento"]


# ------------------------------------------------------------------ o instantaneo versionado no repositorio
def test_committed_snapshot_is_complete_and_well_formed():
    snap = conitec.carregar()
    meta = snap.meta
    assert meta["escopo"] == "somente medicamentos" and str(meta["arquivo_url"]).startswith("https://www.gov.br/conitec/")
    assert len(snap.registros) >= 500 and len(snap.vocabulario) >= 300
    allowed = {"Incorporar", "Não incorporar", "Ampliar", "Excluir", "Atualizar", "Não ampliar", "Manter", "Não excluir", "Aprovar",
               "Não alterar", "Restringir uso", ""}
    for r in snap.registros:
        assert r.tecnologia and r.recomendacao in allowed, r
        assert r.data_publicacao == "" or date.fromisoformat(r.data_publicacao).year >= 2011
    assert date.fromisoformat(str(meta["extraido_em"])) <= date.today()


def test_staleness_helper():
    snap = conitec.carregar()
    extracted = date.fromisoformat(str(snap.meta["extraido_em"]))
    assert conitec.dias_desde_extracao(snap, hoje=extracted) == 0
    assert conitec.dias_desde_extracao(snap, hoje=date(extracted.year + 1, extracted.month, 1)) > conitec.STALE_AFTER_DAYS


# ------------------------------------------------------------------ casamento de nomes
def test_normalize_and_whole_word_search():
    assert conitec.normalizar("  Ácido  Acetilsalicílico! ") == "acido acetilsalicilico"
    found = conitec.buscar("acido acetilsalicilico")
    assert found and all("acetilsalicilico" in r.chave for r in found) and found[0].data_publicacao >= found[-1].data_publicacao
    assert conitec.buscar("ab") == [] and conitec.buscar("zzzinexistente") == []
    assert conitec.buscar("rituxim") == []  # palavra inteira: pedaco de palavra nao casa


def test_term_extraction_handles_salts_forms_parentheses_and_combinations():
    assert conitec._termos("Dicloridrato de pramipexol") == ["pramipexol"]  # sal removido
    assert conitec._termos("Testosterona injetável") == ["Testosterona"]
    assert "Ácido meso2" not in conitec._termos("Ácido meso2,3-dimercaptossuccínico (DMSA, succimer)")  # locantes nao quebram o nome
    assert conitec._termos("Romosozumabe e a teriparatida") == ["Romosozumabe", "teriparatida"]
    assert conitec._termos("Pertuzumabe em combinação com trastuzumabe e quimioterapia")[:2] == ["Pertuzumabe", "trastuzumabe"]
    assert conitec._termos("Nivolumabe para melanoma 3 mg") == ["Nivolumabe"]


def test_english_forms_follow_suffix_rules():
    assert {"dapagliflozin", "dapagliflozine"} <= conitec.formas_inglesas("dapagliflozina")
    assert "rituximab" in conitec.formas_inglesas("rituximabe")
    assert "acetilsalicilic acid" in conitec.formas_inglesas("acido acetilsalicilico")
    assert "nirmatrelvir ritonavir" not in conitec.formas_inglesas("ritonavir")


def pares(texto):
    return {(c.pt, c.en, c.metodo) for c in conitec.candidatos(texto)}


def test_candidates_link_english_text_to_portuguese_names_with_the_method_used():
    found = pares("Patients on aspirin and azathioprine; dapagliflozin versus placebo; rituximab for lupus.")
    assert ("Ácido acetilsalicílico", "aspirin", "sinonimo") in found
    assert ("Azatioprina", "azathioprine", "sinonimo") in found
    assert ("Dapagliflozina", "dapagliflozin", "cognato") in found
    assert ("Rituximabe", "rituximab", "sinonimo") in found


@pytest.mark.parametrize("texto", [
    "A randomized trial of surgery versus placebo in adults with hypertension and diabetes.",
    "Deep learning for image segmentation of satellite data in air pollution studies.",
    "Susceptible patients showed sustained recovery after rehabilitation.",
    "",
])
def test_candidates_stay_empty_for_texts_without_known_drugs(texto):
    assert conitec.candidatos(texto) == []


def test_candidates_are_capped_and_ordered_by_mentions():
    text = "dapagliflozin " * 3 + "rituximab " + "tofacitinib " + " ".join(f"drug{i}" for i in range(20))
    ordered = [c.en for c in conitec.candidatos(text)]
    assert ordered[0] == "dapagliflozin" and len(ordered) <= conitec.MAX_CANDIDATES


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
    works = [Work(ref="1", title="Aspirin in pregnancy", abstract="Low-dose aspirin and dapagliflozin were studied.", source="Europe PMC"),
             Work(ref="2", title="Hip surgery", abstract="Rehabilitation after hip fracture surgery.", source="Europe PMC")]
    discovery = DiscoveryService([Catalog(works)], SlidingWindowLimiter(100, 60), fallback=None)
    repository = ArticleRepository(lambda raw: ("T", "Resumo suficiente para o teste.", "s"))
    service = AnalysisService(repository, MagicMock(), SlidingWindowLimiter(50, 60))
    app = create_app(service, repository, Settings(session_secret="k" * 40), search_fn=lambda *a, **k: [], discovery=discovery, library=library)
    return TestClient(app, base_url="http://testserver")


def test_conitec_route_returns_decisions_with_source_metadata(client):
    data = client.get("/api/brasil/conitec", params={"q": "Ácido acetilsalicílico"}).json()
    assert data["registros"] and set(data["registros"][0]) >= {"year", "technology", "recommendation", "decisionMs", "ordinance", "publishedAt"}
    meta = data["meta"]
    assert meta["paginaUrl"].startswith("https://www.gov.br/conitec/") and meta["medicamentos"] >= 500 and isinstance(meta["defasado"], bool)
    assert client.get("/api/brasil/conitec", params={"q": "zzzinexistente"}).json()["registros"] == []
    assert client.get("/api/brasil/conitec", params={"q": "ab"}).status_code == 422
    assert client.get("/api/brasil/conitec").status_code == 422


def test_article_route_lists_candidates_to_confirm_or_none(client):
    data = client.get("/api/discover/brasil", params={"ref": "1"}).json()
    names = {c["pt"]: c for c in data["candidatos"]}
    assert {"Ácido acetilsalicílico", "Dapagliflozina"} <= set(names)
    assert names["Ácido acetilsalicílico"]["en"] == "aspirin" and names["Ácido acetilsalicílico"]["metodo"] == "sinonimo"
    assert all(c["conitec"] or c["anvisa"] for c in data["candidatos"])  # cada candidato tem algo nas bases
    assert client.get("/api/discover/brasil", params={"ref": "2"}).json()["candidatos"] == []
    assert client.get("/api/discover/brasil", params={"ref": "999"}).status_code == 404


def test_routes_degrade_when_the_snapshot_is_missing(client):
    with patch.object(conitec, "carregar", side_effect=FileNotFoundError("sem arquivo")):
        response = client.get("/api/brasil/conitec", params={"q": "aspirina"})
    assert response.status_code == 503 and "dados oficiais do Brasil" in response.json()["error"]
