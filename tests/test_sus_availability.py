"""Disponibilidade no SUS: Tabela SIGTAP (instantaneo, busca, cognatos), veredito por item e rotas."""

import io
import json
import zipfile
from datetime import date, datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from brasil import anvisa, conitec, disponibilidade, rename, sigtap, sigtap_build
from catalog import Work
from config import Settings
from db import Database
from discovery import DiscoveryService
from library_store import LibraryStore
from ratelimit import SlidingWindowLimiter
from web import create_app
from workflow import AnalysisService, ArticleRepository


# ---------------------------------------------------------------------------- construcao do instantaneo
def linha(*campos):
    return "".join(valor.ljust(tamanho)[:tamanho] for valor, tamanho in campos)


def zip_do_sigtap(procedimentos, *, sem=()):
    layout_proc = "Coluna,Tamanho,Inicio,Fim,Tipo\nCO_PROCEDIMENTO,10,1,10,V\nNO_PROCEDIMENTO,50,11,60,V\nTP_COMPLEXIDADE,1,61,61,V\n"
    layout_grupo = "Coluna,Tamanho,Inicio,Fim,Tipo\nCO_GRUPO,2,1,2,V\nNO_GRUPO,50,3,52,V\n"
    layout_sub = "Coluna,Tamanho,Inicio,Fim,Tipo\nCO_GRUPO,2,1,2,V\nCO_SUB_GRUPO,2,3,4,V\nNO_SUB_GRUPO,50,5,54,V\n"
    arquivos = {
        "tb_procedimento_layout.txt": layout_proc,
        "tb_procedimento.txt": "\n".join(linha((c, 10), (n, 50), (x, 1)) for c, n, x in procedimentos) + "\n",
        "tb_grupo_layout.txt": layout_grupo,
        "tb_grupo.txt": linha(("04", 2), ("Procedimentos cirúrgicos", 50)) + "\n" + linha(("06", 2), ("Medicamentos", 50)) + "\n",
        "tb_sub_grupo_layout.txt": layout_sub,
        "tb_sub_grupo.txt": linha(("04", 2), ("07", 2), ("Cirurgia do aparelho digestivo", 50)) + "\n",
        "versao": "1.1",
    }
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as arquivo:
        for nome, texto in arquivos.items():
            if nome not in sem:
                arquivo.writestr(nome, texto.encode("latin-1"))
    return saida.getvalue()


PROCEDIMENTOS = [
    ("0407030026", "COLECISTECTOMIA", "2"), ("0407030034", "COLECISTECTOMIA VIDEOLAPAROSCÓPICA", "2"),
    ("0407010017", "MASTOIDECTOMIA", "3"), ("0604130074", "RIVASTIGMINA 2,0 MG/ML SOLUÇÃO ORAL", "3"),
    ("0415020034", "OPERAÇÃO CESARIANA", "2"),
]


@pytest.fixture
def pequena(monkeypatch):
    monkeypatch.setattr(sigtap_build, "MIN_PROCEDIMENTOS", 2)


def test_build_reads_fixed_width_files_with_groups_and_accents(pequena):
    snapshot = sigtap_build.montar_instantaneo(zip_do_sigtap(PROCEDIMENTOS), arquivo_url="ftp://ftp2.datasus.gov.br/x.zip", competencia="202605",
                                               agora=datetime(2026, 10, 21, tzinfo=timezone.utc))
    assert snapshot["meta"]["procedimentos"] == 5 and snapshot["meta"]["competencia"] == "202605" and snapshot["meta"]["extraido_em"] == "2026-10-21"
    assert snapshot["grupos"] == {"04": "Procedimentos cirúrgicos", "06": "Medicamentos"} and snapshot["subgrupos"] == {"0407": "Cirurgia do aparelho digestivo"}
    assert ["0407030034", "COLECISTECTOMIA VIDEOLAPAROSCÓPICA", "2"] in snapshot["procedimentos"]


def test_build_refuses_a_broken_table(pequena):
    with pytest.raises(sigtap_build.SigtapError, match="ZIP"):
        sigtap_build.montar_instantaneo(b"nao e zip", arquivo_url="u", competencia="202605")
    with pytest.raises(sigtap_build.SigtapError, match="falta o arquivo"):
        sigtap_build.montar_instantaneo(zip_do_sigtap(PROCEDIMENTOS, sem=("tb_grupo.txt",)), arquivo_url="u", competencia="202605")
    with pytest.raises(sigtap_build.SigtapError, match="Poucos procedimentos"):
        sigtap_build.montar_instantaneo(zip_do_sigtap(PROCEDIMENTOS[:1]), arquivo_url="u", competencia="202605")


def test_build_picks_the_latest_table_and_refuses_pages_without_the_official_link():
    pagina = (
        '<a href="ftp://ftp2.datasus.gov.br/pub/sistemas/tup/downloads/TabelaUnificada_202604_v2605181544.zip">a</a>'
        '<a href="ftp://ftp2.datasus.gov.br/pub/sistemas/tup/downloads/TabelaUnificada_202605_v2605210940.zip">b</a>'
        '<a href="ftp://ftp2.datasus.gov.br/pub/sistemas/tup/downloads/Mapeamento_TUSS_SIGTAP.zip">c</a>'
    )
    url, competencia = sigtap_build.descobrir_arquivo(pagina)
    assert competencia == "202605" and url.endswith("TabelaUnificada_202605_v2605210940.zip")
    for ruim in ("<html></html>", '<a href="ftp://servidor-falso.com/pub/sistemas/tup/downloads/TabelaUnificada_202605_v1.zip">x</a>'):
        with pytest.raises(sigtap_build.SigtapError):
            sigtap_build.descobrir_arquivo(ruim)


def test_build_saves_and_the_snapshot_loads_back(pequena, tmp_path):
    snapshot = sigtap_build.montar_instantaneo(zip_do_sigtap(PROCEDIMENTOS), arquivo_url="u", competencia="202605")
    caminho = sigtap_build.salvar(snapshot, tmp_path / "sub" / "sigtap.json")
    carregado = sigtap.carregar(str(caminho))
    colecistectomia = next(p for p in carregado.procedimentos if p.codigo == "0407030026")
    assert len(carregado.procedimentos) == 5 and colecistectomia.grupo == "Procedimentos cirúrgicos"
    assert colecistectomia.subgrupo == "Cirurgia do aparelho digestivo" and colecistectomia.complexidade_texto == "média complexidade"


# ---------------------------------------------------------------------------- busca e cognatos
@pytest.fixture
def pequeno(pequena, tmp_path):
    snapshot = sigtap_build.montar_instantaneo(zip_do_sigtap(PROCEDIMENTOS), arquivo_url="u", competencia="202605")
    return sigtap.carregar(str(sigtap_build.salvar(snapshot, tmp_path / "s.json")))


def test_search_matches_whole_words_without_accents_and_ranks_the_exact_name_first(pequeno):
    achados = sigtap.buscar("colecistectomia", instantaneo=pequeno)
    assert achados.total == 2 and [p.nome for p in achados.itens] == ["COLECISTECTOMIA", "COLECISTECTOMIA VIDEOLAPAROSCÓPICA"]
    assert sigtap.buscar("operacao cesariana", instantaneo=pequeno).total == 1
    assert sigtap.buscar("operações cesarianas", instantaneo=pequeno).total == 1  # plural
    assert sigtap.buscar("cesariana de urgencia", instantaneo=pequeno).total == 0  # todas as palavras precisam casar
    assert sigtap.buscar("de", instantaneo=pequeno).total == 0 and sigtap.buscar("ab", instantaneo=pequeno).total == 0


def test_cognates_link_english_techniques_but_not_a_different_root(pequeno):
    achados = {c.termo: c for c in sigtap.candidatos("She had a cholecystectomy; mastoidectomy was not needed. Mastectomy rates fell.", instantaneo=pequeno)}
    assert "colecistectomia" in achados and achados["colecistectomia"].metodo == "cognato" and achados["colecistectomia"].verificavel is False
    assert "mastoidectomia" in achados
    assert "mastectomia" not in achados and len(achados) == 2  # "mast-" nao liga a "mastoid-" (nem o contrario)


def test_curated_synonyms_come_first_and_are_verifiable(pequeno):
    achados = sigtap.candidatos("Caesarean section and cholecystectomy outcomes.", instantaneo=pequeno)
    assert [c.metodo for c in achados] == ["sinonimo", "cognato"] and achados[0].termo == "operacao cesariana" and achados[0].verificavel is True
    assert sigtap.candidatos("short", instantaneo=pequeno) == []


# ---------------------------------------------------------------------------- instantaneo real
def test_the_versioned_snapshot_is_sane_and_every_alias_resolves():
    tabela = sigtap.carregar()
    assert len(tabela.procedimentos) >= 4000 and len(tabela.meta["competencia"]) == 6
    colecistectomia = sigtap.buscar("colecistectomia", instantaneo=tabela).itens[0]
    assert colecistectomia.codigo == "0407030026" and colecistectomia.grupo.startswith("Procedimentos cir")
    assert not any("�" in p.nome for p in tabela.procedimentos)  # latin-1 lido certo
    sem_acerto = [pt for pt in sigtap._sinonimos().values() if not sigtap.buscar(pt, instantaneo=tabela).total]  # noqa: SLF001
    assert sem_acerto == []
    assert sigtap.dias_desde_extracao(tabela, date(2026, 10, 22)) == 1 or sigtap.dias_desde_extracao(tabela) is not None


# ---------------------------------------------------------------------------- vereditos
@pytest.fixture(scope="module")
def bases():
    return anvisa.carregar(), conitec.carregar(), rename.carregar(), sigtap.carregar()


def veredito(itens, nome):
    return next(i for i in itens if i.nome.lower() == nome.lower()).veredito


def test_medicine_on_the_rename_is_available_and_cites_the_sources(bases):
    (item,) = disponibilidade.avaliar_termo("metformina", *bases)
    assert item.tipo == "medicamento" and item.veredito == "disponivel" and "Rename" in item.fontes
    assert any("Rename 2024" in d for d in item.detalhes) and any("ANVISA" in d for d in item.detalhes)


def test_medicine_in_the_sigtap_specialized_group_is_available(bases):
    (item,) = disponibilidade.avaliar_termo("rivastigmina", *bases)
    assert item.veredito == "disponivel" and "SIGTAP" in item.fontes


def test_procedure_is_found_in_the_sigtap_and_unknown_terms_are_not_found(bases):
    (item,) = disponibilidade.avaliar_termo("transplante de rim", *bases)
    assert item.tipo == "procedimento" and item.veredito == "disponivel" and item.total_procedimentos >= 1 and item.procedimentos[0].codigo
    (nada,) = disponibilidade.avaliar_termo("zzzinexistente", *bases)
    assert nada.veredito == "nao_encontrado" and disponibilidade.VEREDITOS["nao_encontrado"][1] == "none"


def test_a_medicine_hit_hides_the_lab_exams_that_share_its_name(bases):
    itens = disponibilidade.avaliar_termo("insulina", *bases)
    assert [i.tipo for i in itens] == ["medicamento"]


def test_conitec_decisions_decide_when_there_is_no_rename_or_sigtap_entry(bases):
    def registro(decisao, data):
        return conitec.Registro(2026, "xyzmab", "", decisao, decisao, "Portaria 1", data, "", "", "xyzmab")

    def veredito_de(*registros, ativos=0):
        situacao = consulta_situacao(registros, ativos)
        return disponibilidade._medicamento(situacao, bases[3], "", "manual").veredito  # noqa: SLF001

    assert veredito_de(registro("Incorporar", "2026-01-01")) == "incorporado"
    assert veredito_de(registro("Não incorporar", "2026-01-01")) == "nao_incorporado"
    assert veredito_de(registro("Excluir", "2026-01-01")) == "excluido"
    assert veredito_de(registro("Não incorporar", "2025-01-01"), registro("Incorporar", "2026-01-01")) == "incorporado"  # vale a mais recente
    assert veredito_de(ativos=3) == "registrado" and veredito_de() == "nao_encontrado"


def consulta_situacao(registros, ativos):
    from brasil import consulta  # noqa: PLC0415 - so este teste monta uma situacao sob medida
    substancias = (anvisa.Substancia("Xyzmab", "xyzmab", ativos, 0, 0, {}, (), 1, ""),) if ativos else ()
    return consulta.Situacao(None, "xyzmab", substancias, tuple(registros), ())


def test_article_text_lists_medicines_and_procedures_with_the_trecho_that_matched(bases):
    texto = "Metformin and bariatric surgery were compared with laparoscopic cholecystectomy and hemodialysis in adults."
    itens = disponibilidade.avaliar_texto(texto, *bases)
    assert {i.tipo for i in itens} == {"medicamento", "procedimento"}
    assert veredito(itens, "Metformina") == "disponivel" and veredito(itens, "Colecistectomia") == "disponivel"
    assert next(i for i in itens if i.nome == "Gastroplastia").origem == "bariatric surgery"
    contexto = disponibilidade.como_contexto(itens)
    assert contexto.startswith("--- DISPONIBILIDADE NO SUS") and "Colecistectomia" in contexto and disponibilidade.como_contexto([]) == ""


def test_a_cognate_that_cannot_be_checked_is_never_reported_as_missing(bases):
    # "-ectomy" so vira candidato quando a tabela tem a palavra; um sinonimo sem acerto, sim, aparece como "nao encontrado"
    itens = disponibilidade.avaliar_texto("A lobotomy was described.", *bases)
    assert all(i.veredito != "nao_encontrado" for i in itens)


# ---------------------------------------------------------------------------- rotas
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
    works = [Work(ref="1", title="Metformin or surgery", abstract="Metformin and laparoscopic cholecystectomy in obesity.", source="Europe PMC")]
    discovery = DiscoveryService([Catalog(works)], SlidingWindowLimiter(100, 60), fallback=None)
    repository = ArticleRepository(lambda raw: ("T", "Resumo suficiente para o teste.", "s"))
    service = AnalysisService(repository, MagicMock(), SlidingWindowLimiter(50, 60))
    app = create_app(service, repository, Settings(session_secret="k" * 40), search_fn=lambda *a, **k: [], discovery=discovery, library=library)
    return TestClient(app, base_url="http://testserver")


def test_manual_route_returns_items_notice_and_the_four_sources(client):
    data = client.get("/api/brasil/sus", params={"q": "colecistectomia"}).json()
    item = data["items"][0]
    assert item["kind"] == "procedimento" and item["verdict"] == "disponivel" and item["tone"] == "ok" and item["totalProcedures"] >= 1
    assert item["procedures"][0]["code"] == "0407030026" and item["procedures"][0]["group"]
    assert "não garante" in data["notice"] and set(data["meta"]) == {"anvisa", "conitec", "rename", "sigtap"}
    assert data["meta"]["sigtap"]["competencia"] and data["meta"]["sigtap"]["defasado"] in (True, False)
    assert client.get("/api/brasil/sus", params={"q": "zzzinexistente"}).json()["items"][0]["verdict"] == "nao_encontrado"
    assert client.get("/api/brasil/sus", params={"q": "ab"}).status_code == 422


def test_article_route_finds_the_interventions_in_the_abstract(client):
    items = client.get("/api/discover/sus", params={"ref": "1"}).json()["items"]
    assert {(i["kind"], i["name"]) for i in items} >= {("medicamento", "Metformina"), ("procedimento", "Colecistectomia")}
    assert next(i for i in items if i["name"] == "Colecistectomia")["source"] == "cholecystectomy"
    assert client.get("/api/discover/sus", params={"ref": "999"}).status_code == 404


def test_routes_degrade_when_the_sigtap_snapshot_is_missing(client):
    with patch.object(sigtap, "carregar", side_effect=FileNotFoundError("sem arquivo")):
        assert client.get("/api/brasil/sus", params={"q": "colecistectomia"}).status_code == 503
        assert client.get("/api/discover/sus", params={"ref": "1"}).status_code == 503
    assert json.dumps(sigtap.carregar().meta)
