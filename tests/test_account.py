"""Conta: resumo do perfil, troca de senha, copia dos dados, exclusao (LGPD) e sessao de conta que deixou de existir."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import interests
from account_store import AccountStore
from alerts import AlertService, AlertStore
from catalog import Work
from citations import Author
from config import Settings
from db import Database
from discovery import DiscoveryService
from library_store import LibraryStore
from profiles import ProfileStore
from ratelimit import SlidingWindowLimiter
from reports import ReportStore
from sessions import SessionSigner
from web import SESSION_COOKIE, create_app
from workflow import AnalysisService, ArticleRepository

PASSWORD = "senha-forte-123"
EMAIL = "ana@exemplo.com"
SECRET = "k" * 40


def make_work(ref):
    return Work(ref=ref, title=f"Estudo {ref}", authors=(Author("Silva", "Ana"),), journal="Revista X", year=2024, doi=f"10.1/{ref}",
                abstract="Background: x. Results: reduced 12% (p<0.05).", source="Europe PMC")


# ------------------------------------------------------------------ armazenamento de contas
@pytest.fixture
def accounts(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "a.sqlite3"))
    store = AccountStore()
    store.initialize()
    return store


def test_account_store_exists_created_at_change_password_and_delete(accounts):
    assert not accounts.exists(EMAIL) and accounts.created_at(EMAIL) == ""
    assert accounts.create_user(EMAIL, PASSWORD)
    assert accounts.exists("  ANA@exemplo.com ") and len(accounts.created_at(EMAIL)) == 19
    assert accounts.change_password(EMAIL, "outra-senha-456")
    assert accounts.authenticate(EMAIL, "outra-senha-456") and not accounts.authenticate(EMAIL, PASSWORD)
    assert not accounts.change_password("ninguem@exemplo.com", "outra-senha-456")
    assert accounts.delete_user(EMAIL) and not accounts.exists(EMAIL) and not accounts.delete_user(EMAIL)
    assert not accounts.authenticate(EMAIL, "outra-senha-456")


# ------------------------------------------------------------------ rotas
@pytest.fixture
def env(accounts, tmp_path):
    database = Database(database_url="", sqlite_path=str(tmp_path / "a.sqlite3"))
    library, reports, profiles, alert_store = LibraryStore(database), ReportStore(database), ProfileStore(database), AlertStore(database)
    for store in (library, reports, profiles, alert_store):
        store.initialize()
    alerts = AlertService(alert_store, lambda query, user: ())

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
    settings = Settings(session_secret=SECRET, login_attempts_per_minute=100)
    app = create_app(service, repository, settings, account_store_factory=lambda: accounts, search_fn=lambda *a, **k: [], discovery=discovery,
                     library=library, alerts=alerts, reports=reports, profiles=profiles)

    def client(email=EMAIL, register=True):
        test_client = TestClient(app, base_url="http://testserver")
        if email and register:
            assert test_client.post("/api/auth/register", json={"email": email, "password": PASSWORD}).status_code == 200
        return test_client

    return type("Env", (), {
        "client": staticmethod(client), "accounts": accounts, "library": library, "reports": reports, "profiles": profiles,
        "alerts": alerts, "alert_store": alert_store, "database": database,
    })


def fill(env, email=EMAIL):
    env.library.save(email, make_work("1"))
    created = env.library.create_list(email, "Minha lista")
    env.library.add_to_list(email, created.id, make_work("2"))
    env.library.save_analysis(email, make_work("1"), "medicina", "Resumo Clínico", "# Texto")
    env.reports.create(email, list_name="Minha lista", works=[make_work("2")], title="Meu relatório")
    env.alert_store.set_preferences(email, interests.validar([{"area": "medicina", "subtopics": ["pediatria"]}], ["pt"], ["metformina"]))
    env.alert_store.add_alerts(email, [(make_work("9"), "Medicina: Pediatria")])
    env.profiles.set(email, "saude")


def test_account_routes_require_login(env):
    anonimo = env.client(None)
    assert anonimo.get("/api/account").status_code == 401 and anonimo.get("/api/account/export").status_code == 401
    assert anonimo.post("/api/account/password", json={"current": "a", "new": "b"}).status_code == 401
    assert anonimo.request("DELETE", "/api/account", json={"password": "x"}).status_code == 401


def test_summary_counts_everything_the_account_has(env):
    client = env.client()
    empty = client.get("/api/account").json()
    assert empty["email"] == EMAIL and len(empty["createdAt"]) == 19 and empty["counts"] == {"library": 0, "lists": 0, "analyses": 0, "reports": 0}
    assert empty["profile"] == {"profile": None, "healthPack": True, "configured": False}
    fill(env)
    full = client.get("/api/account").json()
    assert full["counts"] == {"library": 1, "lists": 1, "analyses": 1, "reports": 1}
    assert full["interests"]["topics"] == 1 and full["interests"]["terms"] == 1 and full["interests"]["unread"] == 1
    assert full["profile"]["profile"] == "saude"
    assert env.client("bia@exemplo.com").get("/api/account").json()["counts"]["library"] == 0  # outra conta nao enxerga


def test_change_password_checks_current_policy_and_difference(env):
    client = env.client()
    assert client.post("/api/account/password", json={"current": "errada-123", "new": "nova-senha-789"}).status_code == 400
    assert client.post("/api/account/password", json={"current": PASSWORD, "new": "curta"}).status_code == 400
    assert client.post("/api/account/password", json={"current": PASSWORD, "new": PASSWORD}).json()["error"].startswith("A nova senha precisa")
    assert client.post("/api/account/password", json={"current": PASSWORD, "new": "12345678"}).status_code == 400  # senha comum
    ok = client.post("/api/account/password", json={"current": PASSWORD, "new": "nova-senha-789"})
    assert ok.status_code == 200 and ok.json() == {"ok": True}
    other = env.client(None)
    assert other.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 401
    assert other.post("/api/auth/login", json={"email": EMAIL, "password": "nova-senha-789"}).status_code == 200


def test_export_has_every_kind_of_data_and_no_password_material(env):
    client = env.client()
    fill(env)
    response = client.get("/api/account/export")
    assert response.status_code == 200 and response.headers["content-disposition"] == 'attachment; filename="meus-dados.json"'
    data = response.json()
    assert data["account"]["email"] == EMAIL and data["exportedAt"] and data["profile"] == {"profile": "saude", "healthPack": True}
    assert [w["title"] for w in data["library"]] == ["Estudo 1"] and data["library"][0]["tags"] == []
    assert data["lists"][0]["name"] == "Minha lista" and data["lists"][0]["works"][0]["title"] == "Estudo 2" and data["lists"][0]["shared"] is False
    assert data["analyses"][0]["markdown"] == "# Texto" and data["analyses"][0]["label"] == "Resumo Clínico"
    report = data["reports"][0]
    assert report["title"] == "Meu relatório" and report["studies"][0]["included"] is True and report["version"] == 1
    assert data["interests"]["terms"] == ["metformina"] and data["alerts"][0]["topic"] == "Medicina: Pediatria"
    raw = response.text.lower()
    assert "password" not in raw and "salt" not in raw and "pbkdf2" not in raw
    assert env.client("bia@exemplo.com").get("/api/account/export").json()["library"] == []


def test_delete_requires_the_password_and_removes_everything(env):
    client = env.client()
    other = env.client("bia@exemplo.com")
    fill(env)
    fill(env, "bia@exemplo.com")
    assert client.request("DELETE", "/api/account", json={"password": "errada-123"}).status_code == 400
    assert env.accounts.exists(EMAIL) and len(env.library.items(EMAIL)) == 1  # nada foi apagado
    gone = client.request("DELETE", "/api/account", json={"password": PASSWORD})
    assert gone.status_code == 200 and gone.json() == {"deleted": True}
    assert not env.accounts.exists(EMAIL)
    assert env.library.items(EMAIL) == [] and env.library.lists(EMAIL) == [] and env.library.analyses(EMAIL) == []
    assert env.reports.summaries(EMAIL) == [] and env.alert_store.alerts(EMAIL) == [] and env.alert_store.preferences(EMAIL)[0].empty
    assert env.profiles.get(EMAIL).configured is False
    owned = [("library_items", "user_email"), ("reading_lists", "owner_email"), ("saved_analyses", "user_email"), ("reports", "owner_email"),
             ("interest_prefs", "user_email"), ("interest_baselines", "user_email"), ("alert_seen", "user_email"), ("alerts", "user_email"),
             ("user_profiles", "user_email")]
    for table, column in owned:
        assert env.database.query(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (EMAIL,))[0][0] == 0, table  # noqa: S608
    assert env.client(None).post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD}).status_code == 401
    # a outra conta continua inteira
    assert other.get("/api/account").json()["counts"] == {"library": 1, "lists": 1, "analyses": 1, "reports": 1}
    assert env.database.query("SELECT COUNT(*) FROM reading_list_items")[0][0] == 1  # so o item da lista da outra conta


def test_a_deleted_account_is_logged_out_everywhere_and_the_email_can_be_reused(env):
    first = env.client()
    cookie = first.cookies.get(SESSION_COOKIE)
    second = env.client(None)
    second.cookies.set(SESSION_COOKIE, cookie)  # a mesma sessao em outro aparelho
    assert second.get("/api/auth/me").json() == {"user": EMAIL}
    first.request("DELETE", "/api/account", json={"password": PASSWORD})
    assert first.get("/api/auth/me").json() == {"user": None}  # o cookie foi limpo
    assert second.get("/api/auth/me").json() == {"user": None}  # o outro aparelho cai junto
    assert second.get("/api/account").status_code == 401
    again = env.client()  # o mesmo e-mail pode ser cadastrado de novo, sem dados antigos
    assert again.get("/api/account").json()["counts"]["library"] == 0


def test_a_valid_cookie_for_an_account_that_never_existed_is_not_a_session(env):
    ghost = env.client(None)
    ghost.cookies.set(SESSION_COOKIE, SessionSigner(SECRET).issue("fantasma@exemplo.com"))
    assert ghost.get("/api/auth/me").json() == {"user": None} and ghost.get("/api/account").status_code == 401


def test_session_survives_when_the_accounts_database_fails(env, monkeypatch):
    client = env.client()
    monkeypatch.setattr(env.accounts, "exists", MagicMock(side_effect=__import__("account_store").AccountStoreError("fora do ar")))
    other = env.client(None)
    other.cookies.set(SESSION_COOKIE, SessionSigner(SECRET).issue("nova@exemplo.com"))
    assert other.get("/api/auth/me").json() == {"user": "nova@exemplo.com"}  # falha do banco nao derruba sessao
    assert client.get("/api/auth/me").json() == {"user": EMAIL}
