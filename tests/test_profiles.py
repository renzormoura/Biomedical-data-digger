"""Perfil de uso: o que a pessoa faz e se o pacote Saude no Brasil fica visivel."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import profiles
from account_store import AccountStore
from config import Settings
from db import Database
from discovery import DiscoveryService
from library_store import LibraryStore
from profiles import DEFAULT, ProfileError, ProfileStore
from ratelimit import SlidingWindowLimiter
from web import create_app
from workflow import AnalysisService, ArticleRepository

EMAIL = "ana@exemplo.com"


@pytest.fixture
def store(tmp_path):
    result = ProfileStore(Database(database_url="", sqlite_path=str(tmp_path / "p.sqlite3")))
    result.initialize()
    return result


def test_options_list_every_profile_with_the_health_default():
    options = {o["key"]: o for o in profiles.options()}
    assert set(options) == {"estudante", "pesquisador", "saude", "consultoria", "outro"}
    assert options["saude"]["healthPack"] is True and options["estudante"]["healthPack"] is False
    assert all(o["label"] and o["description"] for o in options.values())


def test_unset_profile_shows_the_health_pack_and_is_not_configured(store):
    assert store.get(EMAIL) == DEFAULT and DEFAULT.health_pack and not DEFAULT.configured
    assert store.get(None) == DEFAULT and store.get("") == DEFAULT


def test_set_uses_the_profile_default_unless_overridden(store):
    assert store.set(EMAIL, "estudante") == profiles.Profile("estudante", False)
    assert store.get(EMAIL).configured and not store.get(EMAIL).health_pack
    assert store.set(EMAIL, "saude").health_pack is True
    assert store.set(EMAIL, "estudante", True).health_pack is True  # o usuario manda
    assert store.set(EMAIL, "saude", False).health_pack is False
    assert store.get(EMAIL) == profiles.Profile("saude", False)


def test_unknown_profile_is_rejected_and_accounts_are_isolated(store):
    with pytest.raises(ProfileError):
        store.set(EMAIL, "astronauta")
    store.set(EMAIL, "saude")
    assert store.get("outra@exemplo.com") == DEFAULT
    store._db.execute("UPDATE user_profiles SET profile = 'extinto'")  # noqa: SLF001
    assert store.get(EMAIL) == DEFAULT  # perfil que deixou de existir volta ao padrao


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "app.sqlite3"))
    AccountStore().initialize()
    database = Database(database_url="", sqlite_path=str(tmp_path / "app.sqlite3"))
    library = LibraryStore(database)
    library.initialize()
    profile_store = ProfileStore(database)
    profile_store.initialize()

    class Catalog:
        id, name = "fake", "Fake"

        def study_types(self):
            return ()

        def search(self, query):
            raise AssertionError("nao deve buscar")

        def get(self, ref):
            return None

    discovery = DiscoveryService([Catalog()], SlidingWindowLimiter(100, 60), fallback=None)
    repository = ArticleRepository(lambda raw: ("T", "Resumo suficiente para o teste.", "s"))
    service = AnalysisService(repository, MagicMock(), SlidingWindowLimiter(50, 60))
    settings = Settings(session_secret="k" * 40, login_attempts_per_minute=100)

    def client(email=EMAIL):
        app = create_app(service, repository, settings, account_store_factory=lambda: AccountStore(), search_fn=lambda *a, **k: [],
                         discovery=discovery, library=library, profiles=profile_store)
        test_client = TestClient(app, base_url="http://testserver")
        if email:
            assert test_client.post("/api/auth/register", json={"email": email, "password": "senha-forte-123"}).status_code == 200
        return test_client

    return type("Env", (), {"client": staticmethod(client), "store": profile_store})


def test_options_are_public_and_profile_routes_need_login(env):
    anonimo = env.client(None)
    assert {p["key"] for p in anonimo.get("/api/profile/options").json()["profiles"]} >= {"estudante", "saude"}
    assert anonimo.get("/api/profile").status_code == 401
    assert anonimo.put("/api/profile", json={"profile": "saude"}).status_code == 401


def test_get_and_put_profile_through_the_api(env):
    client = env.client()
    assert client.get("/api/profile").json() == {"profile": None, "healthPack": True, "configured": False}
    assert client.put("/api/profile", json={"profile": "estudante"}).json() == {"profile": "estudante", "healthPack": False, "configured": True}
    assert client.put("/api/profile", json={"profile": "estudante", "healthPack": True}).json()["healthPack"] is True
    assert client.get("/api/profile").json() == {"profile": "estudante", "healthPack": True, "configured": True}
    assert client.put("/api/profile", json={"profile": "astronauta"}).status_code == 400
    assert client.put("/api/profile", json={"profile": ""}).status_code == 422
    assert client.put("/api/profile", json={}).status_code == 422
    assert env.client("bia@exemplo.com").get("/api/profile").json()["configured"] is False


def test_home_page_carries_the_profile_for_the_first_paint(env):
    anonimo = env.client(None).get("/").text
    assert 'data-profile=""' in anonimo and 'data-health-pack="1"' in anonimo  # sem conta: pacote visivel
    client = env.client()
    client.put("/api/profile", json={"profile": "pesquisador"})
    page = client.get("/").text
    assert 'data-profile="pesquisador"' in page and 'data-health-pack="0"' in page
    client.put("/api/profile", json={"profile": "saude"})
    assert 'data-profile="saude"' in client.get("/").text and 'data-health-pack="1"' in client.get("/").text
    assert 'id="profile-link"' in page
