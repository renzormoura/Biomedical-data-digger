"""API do navegador: descoberta, biblioteca, listas, compartilhamento e exportacao."""

import pytest
from fastapi.testclient import TestClient

from account_store import AccountStore
from catalog import CatalogError
from config import Settings
from db import Database
from discovery import DiscoveryService
from library_store import LibraryStore
from ratelimit import SlidingWindowLimiter
from test_discovery import FakeCatalog, make_work
from test_web import FakeGenerator
from web import create_app
from workflow import AnalysisService, ArticleRepository

PASSWORD = "senha-forte-123"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "app.sqlite3"))
    store = AccountStore()
    store.initialize()
    library = LibraryStore(Database(database_url="", sqlite_path=str(tmp_path / "app.sqlite3")))
    library.initialize()
    catalog = FakeCatalog(works=[make_work("1"), make_work("2"), make_work("3", title="Estudo <script>alert(1)</script>")])
    discovery = DiscoveryService([catalog], SlidingWindowLimiter(100, 60), fallback=None)
    repository = ArticleRepository(lambda raw: ("T", "Resumo suficiente para o teste.", "s"))
    service = AnalysisService(repository, FakeGenerator(), SlidingWindowLimiter(50, 60))
    settings = Settings(session_secret="k" * 40, login_attempts_per_minute=100)

    def build(limit=100):
        discovery_ = DiscoveryService([catalog], SlidingWindowLimiter(limit, 60), fallback=None)
        app = create_app(service, repository, settings, account_store_factory=lambda: store, search_fn=lambda *a, **k: [],
                         discovery=discovery_, library=library)
        return TestClient(app, base_url="http://testserver")

    def login(client, email="ana@exemplo.com"):
        assert client.post("/api/auth/register", json={"email": email, "password": PASSWORD}).status_code == 200
        return client

    return type("Env", (), {"client": build(), "build": staticmethod(build), "login": staticmethod(login),
                            "catalog": catalog, "library": library, "discovery": discovery})


# ------------------------------------------------------------------ descoberta
def test_options_list_sources_languages_and_sorts(env):
    body = env.client.get("/api/discover/options").json()
    assert body["sources"][0]["id"] == "europepmc" and body["sources"][0]["default"] is True
    assert [item["id"] for item in body["languages"]] == ["", "pt", "en", "es"]
    assert [item["id"] for item in body["sorts"]] == ["relevance", "recent", "cited"]


def test_search_maps_every_filter_to_the_catalog_query(env):
    response = env.client.get("/api/discover/search", params={
        "q": "metformina", "yf": 2020, "yt": 2024, "types": "Meta-análise, Revisão", "oa": "true", "lang": "pt",
        "sort": "cited", "page": 2, "per_page": 5,
    })
    assert response.status_code == 200
    query = env.catalog.search_calls[-1]
    assert (query.q, query.year_from, query.year_to, query.open_access, query.language) == ("metformina", 2020, 2024, True, "pt")
    assert query.study_types == ("Meta-análise", "Revisão") and (query.sort, query.page, query.per_page) == ("cited", 2, 5)


def test_search_response_shape_and_snippet_truncation(env):
    env.catalog.works["1"] = make_work("1", abstract="x" * 1000)
    body = env.client.get("/api/discover/search").json()
    first = body["works"][0]
    assert body["total"] == 3 and body["page"] == 1 and body["pages"] == 1 and body["perPage"] == 10
    assert first["title"] == "Artigo 1" and first["authors"] == "Anika Weber, Hiro Suzuki" and len(first["snippet"]) == 301
    assert "abstract" not in first and "saved" not in first  # visitante: sem marcacao de salvos


@pytest.mark.parametrize("params", [{"yf": 1500}, {"yt": 9999}, {"page": 0}, {"page": 501}, {"per_page": 50}, {"q": "x" * 301}])
def test_search_rejects_out_of_range_parameters(env, params):
    assert env.client.get("/api/discover/search", params=params).status_code == 422


def test_search_marks_saved_works_for_logged_in_users_only(env):
    client = env.login(env.build())
    assert client.post("/api/library", json={"ref": "2"}).status_code == 200
    saved = {w["ref"]: w["saved"] for w in client.get("/api/discover/search").json()["works"]}
    assert saved == {"1": False, "2": True, "3": False}
    assert "saved" not in env.client.get("/api/discover/search").json()["works"][0]


def test_search_is_rate_limited_and_cached_hits_are_free(env):
    client = env.build(limit=1)
    assert client.get("/api/discover/search", params={"q": "a"}).status_code == 200
    assert client.get("/api/discover/search", params={"q": "a"}).status_code == 200  # cache
    blocked = client.get("/api/discover/search", params={"q": "b"})
    assert blocked.status_code == 429 and "Limite" in blocked.json()["error"]


def test_source_failures_are_503_with_a_safe_message(env):
    env.catalog.fail = True
    response = env.client.get("/api/discover/search", params={"q": "falha"})
    assert response.status_code == 503 and "indisponível" in response.json()["error"]
    assert CatalogError.__name__ not in response.text


def test_unknown_source_is_a_client_error(env):
    assert env.client.get("/api/discover/search", params={"source": "google"}).status_code == 400


def test_work_detail_payload(env):
    body = env.client.get("/api/discover/work", params={"ref": "1"}).json()
    assert body["work"]["title"] == "Artigo 1" and body["work"]["abstract"].startswith("Background:")
    assert [s["heading"] for s in body["sections"]] == ["Contexto", "Métodos", "Resultados", "Conclusões"]
    assert any("RR 0.89" in f["sentence"] for f in body["findings"])
    assert set(body["citations"]) == {"ABNT", "APA", "Vancouver"} and [w["ref"] for w in body["similar"]] == ["2", "3"]
    assert body["work"]["authorList"][0] == {"family": "Weber", "given": "Anika"}


def test_work_not_found_is_404_and_ref_is_validated(env):
    assert env.client.get("/api/discover/work", params={"ref": "999"}).status_code == 404
    assert env.client.get("/api/discover/work", params={"ref": ""}).status_code == 422


def test_hostile_titles_are_returned_as_inert_json_strings(env):
    response = env.client.get("/api/discover/search")
    assert response.headers["content-type"].startswith("application/json")
    assert any(w["title"] == "Estudo <script>alert(1)</script>" for w in response.json()["works"])


# ------------------------------------------------------------------ autenticacao obrigatoria
PROTECTED = [
    ("GET", "/api/library", None), ("POST", "/api/library", {"ref": "1"}), ("DELETE", "/api/library?ref=1", None),
    ("PUT", "/api/library/tags", {"ref": "1", "tags": ["a"]}), ("GET", "/api/library/export", None),
    ("GET", "/api/lists", None), ("POST", "/api/lists", {"name": "x"}), ("DELETE", "/api/lists/abc", None),
    ("POST", "/api/lists/abc/items", {"ref": "1"}), ("DELETE", "/api/lists/abc/items?ref=1", None),
    ("POST", "/api/lists/abc/share", None), ("DELETE", "/api/lists/abc/share", None),
]


@pytest.mark.parametrize("method,path,body", PROTECTED)
def test_library_and_lists_require_an_account(env, method, path, body):
    response = env.client.request(method, path, json=body) if body is not None else env.client.request(method, path)
    assert response.status_code == 401 and "Entre" in response.json()["error"]


# ------------------------------------------------------------------ biblioteca
def test_save_tag_list_and_remove(env):
    client = env.login(env.build())
    client.post("/api/library", json={"ref": "1"})
    client.post("/api/library", json={"ref": "2"})
    assert client.put("/api/library/tags", json={"ref": "1", "tags": ["TCC", "tcc", "Saúde"]}).json() == {"tags": ["TCC", "Saúde"]}
    items = {i["ref"]: i for i in client.get("/api/library").json()["items"]}
    assert set(items) == {"1", "2"} and items["1"]["tags"] == ["TCC", "Saúde"] and items["1"]["saved"] is True
    assert client.delete("/api/library", params={"ref": "1"}).json() == {"saved": False}
    assert [i["ref"] for i in client.get("/api/library").json()["items"]] == ["2"]


def test_saving_an_unknown_work_is_404_and_tags_for_unsaved_work_are_404(env):
    client = env.login(env.build())
    assert client.post("/api/library", json={"ref": "999"}).status_code == 404
    assert client.put("/api/library/tags", json={"ref": "1", "tags": ["x"]}).status_code == 404


def test_library_limit_is_409(env, monkeypatch):
    import library_store

    monkeypatch.setattr(library_store, "MAX_ITEMS", 1)
    client = env.login(env.build())
    client.post("/api/library", json={"ref": "1"})
    response = client.post("/api/library", json={"ref": "2"})
    assert response.status_code == 409 and "limite" in response.json()["error"]


def test_each_account_has_its_own_library(env):
    ana = env.login(env.build(), "ana@exemplo.com")
    bia = env.login(env.build(), "bia@exemplo.com")
    ana.post("/api/library", json={"ref": "1"})
    assert bia.get("/api/library").json()["items"] == []


def test_request_bodies_are_validated(env):
    client = env.login(env.build())
    assert client.post("/api/library", json={"ref": ""}).status_code == 422
    assert client.post("/api/library", json={"ref": "x" * 301}).status_code == 422
    assert client.put("/api/library/tags", json={"ref": "1", "tags": ["x"] * 31}).status_code == 422
    assert client.put("/api/library/tags", json={"ref": "1", "tags": ["x" * 81]}).status_code == 422


def test_cross_origin_writes_are_rejected(env):
    client = env.login(env.build())
    response = client.post("/api/library", json={"ref": "1"}, headers={"origin": "https://evil.example"})
    assert response.status_code == 403


# ------------------------------------------------------------------ listas e compartilhamento
def test_list_lifecycle(env):
    client = env.login(env.build())
    created = client.post("/api/lists", json={"name": "  Leituras da semana  "}).json()
    assert created["name"] == "Leituras da semana" and created["works"] == [] and created["shareToken"] is None
    list_id = created["id"]
    assert client.post(f"/api/lists/{list_id}/items", json={"ref": "1"}).json() == {"added": True}
    client.post(f"/api/lists/{list_id}/items", json={"ref": "2"})
    listed = client.get("/api/lists").json()["lists"][0]
    assert [w["ref"] for w in listed["works"]] == ["1", "2"]
    assert client.delete(f"/api/lists/{list_id}/items", params={"ref": "1"}).json() == {"removed": True}
    assert [w["ref"] for w in client.get("/api/lists").json()["lists"][0]["works"]] == ["2"]
    assert client.delete(f"/api/lists/{list_id}").json() == {"deleted": True}
    assert client.get("/api/lists").json()["lists"] == []


def test_lists_are_private_between_accounts(env):
    ana = env.login(env.build(), "ana@exemplo.com")
    bia = env.login(env.build(), "bia@exemplo.com")
    list_id = ana.post("/api/lists", json={"name": "Privada"}).json()["id"]
    for method, path, body in [
        ("POST", f"/api/lists/{list_id}/items", {"ref": "1"}), ("DELETE", f"/api/lists/{list_id}", None),
        ("POST", f"/api/lists/{list_id}/share", None), ("DELETE", f"/api/lists/{list_id}/items?ref=1", None),
    ]:
        response = bia.request(method, path, json=body) if body is not None else bia.request(method, path)
        assert response.status_code == 404, (method, path)
    assert bia.get("/api/lists").json()["lists"] == []


def test_share_link_is_public_readonly_and_revocable(env):
    owner = env.login(env.build(), "ana@exemplo.com")
    list_id = owner.post("/api/lists", json={"name": "Turma 3"}).json()["id"]
    owner.post(f"/api/lists/{list_id}/items", json={"ref": "1"})
    shared = owner.post(f"/api/lists/{list_id}/share").json()
    assert shared["path"] == f"/#/lista/{shared['token']}"
    public = env.build().get(f"/api/shared/{shared['token']}")  # visitante, sem cookie
    assert public.status_code == 200 and public.json()["name"] == "Turma 3"
    assert [w["ref"] for w in public.json()["works"]] == ["1"] and "ana@exemplo.com" not in public.text
    assert owner.delete(f"/api/lists/{list_id}/share").json() == {"shared": False}
    assert env.build().get(f"/api/shared/{shared['token']}").status_code == 404


@pytest.mark.parametrize("token", ["nao-existe", "x" * 200, "%27%20OR%201%3D1", "..%2F..%2Fetc"])
def test_hostile_or_unknown_share_tokens_are_404(env, token):
    assert env.client.get(f"/api/shared/{token}").status_code == 404


def test_share_endpoint_is_rate_limited_per_identity(env):
    client = env.build()
    codes = [client.get("/api/shared/inexistente").status_code for _ in range(62)]
    assert codes[:60] == [404] * 60 and 429 in codes[60:]


# ------------------------------------------------------------------ exportacao
def test_export_formats_and_headers(env):
    client = env.login(env.build())
    client.post("/api/library", json={"ref": "1"})
    for fmt, filename, marker in [("bibtex", "biblioteca.bib", "@article{"), ("ris", "biblioteca.ris", "TY  - JOUR"),
                                  ("abnt", "referencias-abnt.txt", "WEBER, A."), ("vancouver", "referencias-vancouver.txt", "Weber A")]:
        response = client.get("/api/library/export", params={"format": fmt})
        assert response.status_code == 200 and marker in response.text
        assert f'filename="{filename}"' in response.headers["content-disposition"]
        assert response.headers["cache-control"] == "no-store"


def test_export_of_a_list_and_error_cases(env):
    client = env.login(env.build(), "ana@exemplo.com")
    client.post("/api/library", json={"ref": "1"})
    list_id = client.post("/api/lists", json={"name": "L"}).json()["id"]
    client.post(f"/api/lists/{list_id}/items", json={"ref": "2"})
    text = client.get("/api/library/export", params={"format": "abnt", "list_id": list_id}).text
    assert "Artigo 2" in text and "Artigo 1" not in text
    assert client.get("/api/library/export", params={"format": "pdf"}).status_code == 400
    assert client.get("/api/library/export", params={"list_id": "nao-existe"}).status_code == 404
    other = env.login(env.build(), "bia@exemplo.com")
    assert other.get("/api/library/export", params={"list_id": list_id}).status_code == 404
