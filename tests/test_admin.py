"""Painel de administracao: quem e administrador, visao geral, usuarios com plano e uso, suspensao, redefinicao, exclusao e protecoes."""

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from account_consent import ConsentStore
from account_flags import AccountFlags
from account_store import AccountStore
from account_tokens import AccountTokens
from admin_service import AdminService
from billing import BillingStore
from config import Settings
from db import Database
from discovery import DiscoveryService
from library_store import LibraryStore
from ratelimit import SlidingWindowLimiter
from reports import ReportStore
from test_discovery import FakeCatalog, make_work
from usage import UsageLog
from web import create_app
from workflow import AnalysisService, ArticleRepository

BOSS = "chefe@exemplo.com"
ANA = "ana@exemplo.com"
BIA = "bia@exemplo.com"
PASSWORD = "senha-forte-123"
TOKEN = {"Authorization": "Bearer " + "a" * 30}


class Inbox:
    def __init__(self):
        self.sent = []

    def send(self, message):
        self.sent.append(message)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "a.sqlite3"))
    accounts = AccountStore()
    accounts.initialize()
    database = Database(database_url="", sqlite_path=str(tmp_path / "a.sqlite3"))
    billing, tokens = BillingStore(database), AccountTokens(database)
    consent, flags, library, reports = ConsentStore(database), AccountFlags(database), LibraryStore(database), ReportStore(database)
    for item in (billing, tokens, consent, flags, library, reports):
        item.initialize()
    admin = AdminService(database, billing, tokens, consent, flags)
    discovery = DiscoveryService([FakeCatalog(works=[make_work(str(n)) for n in (1, 2)])], SlidingWindowLimiter(1000, 60), fallback=None)
    repository = ArticleRepository(lambda raw: ("T", "Resumo suficiente para o teste.", "s"))
    service = AnalysisService(repository, MagicMock(), SlidingWindowLimiter(50, 60))
    inbox = Inbox()

    def build(**overrides):
        values = {"session_secret": "k" * 40, "login_attempts_per_minute": 1000, "admin_emails": (BOSS,), "pix_key": "k@exemplo.com",
                  "pix_name": "Empresa", **overrides}
        app = create_app(service, repository, Settings(**values), account_store_factory=lambda: accounts, search_fn=lambda *a, **k: [],
                         discovery=discovery, library=library, reports=reports, billing=billing, mailer=inbox, account_tokens=tokens,
                         consent=consent, flags=flags, admin=admin, usage_log=UsageLog())
        return TestClient(app, base_url="https://testserver" if values.get("production") else "http://testserver")

    def person(client_factory, email):
        client = client_factory()
        assert client.post("/api/auth/register", json={"email": email, "password": PASSWORD, "acceptTerms": True}).status_code == 200
        return client

    def same_site(client, email):
        """Outra pessoa no MESMO servidor (mesmo cache de sessoes): um novo navegador, com os proprios cookies."""
        other = TestClient(client.app, base_url=str(client.base_url))
        assert other.post("/api/auth/register", json={"email": email, "password": PASSWORD, "acceptTerms": True}).status_code == 200
        return other

    return type("Env", (), {"build": staticmethod(build), "person": staticmethod(person), "same_site": staticmethod(same_site), "billing": billing, "tokens": tokens,
                            "inbox": inbox, "flags": flags, "library": library, "accounts": accounts, "consent": consent})


def test_the_panel_is_off_when_nobody_is_configured_and_the_session_endpoint_never_errors(env):
    nobody = env.build(admin_emails=())
    assert nobody.get("/api/admin/session").json() == {"admin": False}
    assert nobody.get("/api/admin/overview").status_code == 404 and nobody.get("/api/admin/users", headers=TOKEN).status_code == 404


def test_only_listed_accounts_are_administrators_by_session(env):
    boss = env.person(env.build, BOSS)
    ana = env.person(env.build, ANA)
    anonymous = env.build()
    assert boss.get("/api/admin/session").json() == {"admin": True, "email": BOSS}
    assert ana.get("/api/admin/session").json() == {"admin": False, "email": None}
    assert anonymous.get("/api/admin/session").json() == {"admin": False, "email": None}
    assert ana.get("/api/admin/overview").status_code == 401 and anonymous.get("/api/admin/users").status_code == 401
    assert boss.get("/api/admin/overview").status_code == 200


def test_in_production_an_administrator_must_have_a_confirmed_email(env):
    boss = env.person(lambda: env.build(production=True), BOSS)
    assert boss.get("/api/admin/session").json()["admin"] is False and boss.get("/api/admin/overview").status_code == 401
    env.tokens.mark_verified(BOSS)
    assert boss.get("/api/admin/session").json()["admin"] is True and boss.get("/api/admin/overview").status_code == 200


def test_the_token_still_works_for_scripts_and_a_wrong_token_is_refused(env):
    assert env.build().get("/api/admin/overview", headers=TOKEN).status_code == 401  # sem ADMIN_TOKEN configurado o token nao vale
    client = env.build(admin_token="a" * 30)
    assert client.get("/api/admin/overview", headers=TOKEN).status_code == 200
    assert client.get("/api/admin/overview", headers={"Authorization": "Bearer errado"}).status_code == 401
    assert client.get("/api/admin/session", headers=TOKEN).json() == {"admin": True, "email": None}


def test_overview_counts_people_plans_payments_and_revenue(env):
    boss = env.person(env.build, BOSS)
    env.person(env.build, ANA)
    env.person(env.build, BIA)
    env.tokens.mark_verified(ANA)
    paid = env.billing.create_request(ANA, "pro", 3, 8700)
    env.billing.confirm(paid.id)
    env.billing.create_request(BIA, "pro", 1, 2900)
    env.flags.suspend(BIA, "teste")
    overview = boss.get("/api/admin/overview").json()
    assert overview["users"] == 3 and overview["verified"] == 1 and overview["suspended"] == 1
    assert overview["byPlan"] == {"gratuito": 2, "pro": 1, "max": 0} and overview["pendingPayments"] == 1
    assert overview["revenueTotalCents"] == 8700 and overview["revenueLast30DaysCents"] == 8700 and overview["newLast7Days"] == 3


def test_users_list_search_paginate_and_show_plan_and_usage(env):
    boss = env.person(env.build, BOSS)
    ana = env.person(env.build, ANA)
    env.person(env.build, BIA)
    ana.post("/api/library", json={"ref": "1"})
    ana.post("/api/library", json={"ref": "2"})
    ana.post("/api/lists", json={"name": "L"})
    env.billing.grant(ANA, "pro", 30)
    page = boss.get("/api/admin/users").json()
    assert page["total"] == 3 and [u["email"] for u in page["users"]] == [ANA, BIA, BOSS]
    row = next(u for u in page["users"] if u["email"] == ANA)
    assert row["plan"] == "pro" and row["usage"] == {"library": 2, "lists": 1, "reports": 0} and row["verified"] is False
    assert [u["email"] for u in boss.get("/api/admin/users", params={"q": "bia"}).json()["users"]] == [BIA]
    assert boss.get("/api/admin/users", params={"q": "%"}).json()["total"] == 0  # curinga do usuario nao vira "todos"
    second = boss.get("/api/admin/users", params={"limit": 2, "offset": 2}).json()
    assert second["total"] == 3 and [u["email"] for u in second["users"]] == [BOSS]


def test_user_detail_shows_terms_suspension_and_payments(env):
    boss = env.person(env.build, BOSS)
    env.person(env.build, ANA)
    env.billing.confirm(env.billing.create_request(ANA, "pro", 1, 2900).id)
    env.flags.suspend(ANA, "chargeback")
    detail = boss.get(f"/api/admin/users/{ANA}").json()
    assert detail["email"] == ANA and detail["terms"]["version"] and detail["suspension"]["reason"] == "chargeback"
    assert detail["payments"][0]["status"] == "confirmado" and detail["isAdmin"] is False
    assert boss.get(f"/api/admin/users/{BOSS}").json()["isAdmin"] is True
    assert boss.get("/api/admin/users/ninguem@exemplo.com").status_code == 404


def test_suspending_blocks_login_and_open_sessions_and_unsuspending_restores_access(env):
    boss = env.person(env.build, BOSS)
    ana = env.same_site(boss, ANA)
    assert ana.get("/api/auth/me").json()["user"] == ANA
    assert boss.post(f"/api/admin/users/{ANA}/suspend", json={"reason": "abuso"}).json() == {"suspended": True}
    assert ana.get("/api/auth/me").json()["user"] is None  # a sessao aberta deixa de valer na hora
    fresh = TestClient(boss.app, base_url="http://testserver")
    refused = fresh.post("/api/auth/login", json={"email": ANA, "password": PASSWORD})
    assert refused.status_code == 403 and "suspensa" in refused.json()["error"]
    assert fresh.post("/api/auth/login", json={"email": ANA, "password": "senha-errada-999"}).status_code == 401  # nao revela o estado
    assert boss.post(f"/api/admin/users/{ANA}/unsuspend").json() == {"unsuspended": True}
    assert fresh.post("/api/auth/login", json={"email": ANA, "password": PASSWORD}).status_code == 200


def test_administrators_cannot_be_suspended_or_deleted_and_deletion_needs_the_email_typed_again(env):
    boss = env.person(env.build, BOSS)
    other = env.person(env.build, "outro-admin@exemplo.com")
    env.person(env.build, ANA)
    assert boss.post(f"/api/admin/users/{BOSS}/suspend", json={}).status_code == 400
    assert boss.request("DELETE", f"/api/admin/users/{BOSS}", json={"confirm": BOSS}).status_code == 400
    assert other.get("/api/admin/session").json()["admin"] is False
    assert boss.request("DELETE", f"/api/admin/users/{ANA}", json={"confirm": "errado@exemplo.com"}).status_code == 400
    assert env.accounts.exists(ANA)


def test_deleting_an_account_removes_everything_but_keeps_confirmed_payments(env):
    boss = env.person(env.build, BOSS)
    ana = env.same_site(boss, ANA)
    ana.post("/api/library", json={"ref": "1"})
    paid = env.billing.create_request(ANA, "pro", 1, 2900)
    env.billing.confirm(paid.id)
    env.billing.create_request(ANA, "pro", 3, 8700)
    env.flags.suspend(ANA, "x")
    assert boss.request("DELETE", f"/api/admin/users/{ANA}", json={"confirm": ANA.upper()}).json() == {"deleted": True}
    assert not env.accounts.exists(ANA) and env.library.items(ANA) == [] and env.billing.subscription(ANA) is None
    assert env.consent.get(ANA) is None and not env.flags.is_suspended(ANA)
    assert env.billing.get(paid.id).status == "confirmado"  # registro de pagamento (obrigacao fiscal)
    assert ana.get("/api/auth/me").json()["user"] is None


def test_self_service_account_deletion_also_removes_the_subscription_and_exports_billing_data(env):
    ana = env.person(env.build, ANA)
    env.billing.confirm(env.billing.create_request(ANA, "pro", 1, 2900).id)
    exported = ana.get("/api/account/export").json()
    assert exported["subscription"]["plan"] == "pro" and exported["payments"][0]["status"] == "confirmado"
    assert ana.request("DELETE", "/api/account", json={"password": PASSWORD}).status_code == 200
    assert env.billing.subscription(ANA) is None


def test_reset_password_link_and_manual_verification(env):
    boss = env.person(env.build, BOSS)
    env.person(env.build, ANA)
    env.inbox.sent.clear()
    assert boss.post(f"/api/admin/users/{ANA}/reset-password").json() == {"sent": True}
    assert env.inbox.sent[-1].to == ANA and "#/redefinir?token=" in env.inbox.sent[-1].text
    assert boss.post(f"/api/admin/users/{ANA}/reset-password").json() == {"sent": False}  # ja ha um link recente
    assert boss.post(f"/api/admin/users/{ANA}/verify").json() == {"verified": True} and env.tokens.is_verified(ANA)


def test_payments_listing_has_pending_and_history_and_system_info(env):
    boss = env.person(env.build, BOSS)
    env.person(env.build, ANA)
    done = env.billing.create_request(ANA, "pro", 1, 2900)
    env.billing.confirm(done.id, "ok")
    env.billing.create_request(ANA, "pro", 3, 8700)
    pending = boss.get("/api/admin/billing/requests").json()["requests"]
    history = boss.get("/api/admin/billing/requests", params={"status": "confirmado"}).json()["requests"]
    assert [item["amount"] for item in pending] == ["R$ 87,00"] and [item["amount"] for item in history] == ["R$ 29,00"]
    system = boss.get("/api/admin/system").json()
    assert system["database"] in ("SQLite", "PostgreSQL") and system["pixConfigured"] is True and system["adminEmails"] == [BOSS]
    assert system["mailEnabled"] is True and system["billingEnforced"] is False and "totals" in system["usage"]


def test_admin_emails_are_normalized_from_the_environment(monkeypatch):
    for name in ("APP_ENV", "REQUIRE_TERMS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ADMIN_EMAILS", " Chefe@Exemplo.com , , outro@exemplo.com,chefe@exemplo.com ")
    assert Settings.from_env().admin_emails == ("chefe@exemplo.com", "outro@exemplo.com")
