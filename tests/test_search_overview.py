"""Panorama dos resultados da busca: contagens por tipo de estudo, anos, acesso aberto e o estudo de maior nota."""

from catalog import Work
from search_overview import UNKNOWN_KEY, build, group_of
from test_browse_api import env  # noqa: F401  (fixture)


def work(ref, *, types=(), year=2020, oa=False, source="Europe PMC", abstract="Resumo do estudo.", retracted=False, doi=None):
    return Work(ref=ref, title=f"Estudo {ref}", study_types=tuple(types), year=year, open_access=oa, source=source,
                abstract=abstract, retracted=retracted, doi=doi if doi is not None else f"10.1/{ref}")


def test_group_priority_and_unknown():
    assert group_of(work("a", types=("Revisão sistemática",))) == "sistematica"
    assert group_of(work("b", types=("Ensaio clínico randomizado",))) == "ensaio"
    assert group_of(work("c", types=("Revisão", "Preprint"))) == "preprint"  # sem revisao por pares pesa primeiro
    assert group_of(work("d")) == UNKNOWN_KEY


def test_build_counts_designs_years_open_access_and_sources():
    works = [
        work("1", types=("Meta-análise",), year=2022, oa=True),
        work("2", types=("Ensaio clínico randomizado",), year=2022, source="PubMed"),
        work("3", types=("Estudo observacional",), year=2020, oa=True),
        work("4", year=2019, retracted=True),
    ]
    info = build(works, total=500)
    assert info["sample"] == 4 and info["total"] == 500
    assert {d["key"]: d["count"] for d in info["designs"]} == {"sistematica": 1, "ensaio": 1, "observacional": 1, UNKNOWN_KEY: 1}
    assert [(y["year"], y["count"]) for y in info["timeline"]] == [(2019, 1), (2020, 1), (2021, 0), (2022, 2)]
    assert info["openAccess"] == 2 and info["retracted"] == 1
    assert {s["name"]: s["count"] for s in info["sources"]} == {"Europe PMC": 3, "PubMed": 1}


def test_strongest_skips_retracted_and_reports_the_design():
    works = [work("weak", types=("Carta",)), work("strong", types=("Meta-análise",)), work("bad", types=("Meta-análise",), retracted=True)]
    strongest = build(works, total=3)["strongest"]
    assert strongest["ref"] == "strong" and strongest["design"] == "Revisões sistemáticas e meta-análises"


def test_empty_sample_has_no_charts_and_no_strongest():
    info = build([], total=0)
    assert info["designs"] == [] and info["timeline"] == [] and info["strongest"] is None


def test_panorama_route_uses_the_same_filters_and_dedupes(env):  # noqa: F811
    body = env.client.get("/api/discover/panorama", params={"q": "metformina", "oa": "true"}).json()
    assert body["sample"] >= 1 and body["total"] >= 1
    assert env.catalog.search_calls[-1].open_access is True
    assert {"designs", "timeline", "openAccess", "sources", "strongest"} <= set(body)

