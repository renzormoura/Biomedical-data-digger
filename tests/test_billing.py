"""Planos, assinatura e pagamento por Pix: BR Code, pedidos, confirmacao pelo administrador, vencimento e limites por plano."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import plans
from account_consent import ConsentStore
from account_flags import AccountFlags
from account_store import AccountStore
from account_tokens import AccountTokens
from admin_service import AdminService
from billing import CANCELLED, CONFIRMED, PENDING, BillingStore
from config import ConfigurationError, Settings
from db import Database
from discovery import DiscoveryService
from domain import LimitReachedError, NotFoundError
from library_store import LibraryStore
from pix import br_code, crc16
from ratelimit import SlidingWindowLimiter
from reports import ReportStore
from test_discovery import FakeCatalog, make_work
from web import create_app
from workflow import AnalysisService, ArticleRepository

EMAIL = "ana@exemplo.com"
PASSWORD = "senha-forte-123"
ADMIN = {"Authorization": "Bearer " + "a" * 30}
START = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


# ------------------------------------------------------------------ Pix
def test_crc16_matches_the_ccitt_false_reference_vector():
    assert crc16("123456789") == "29B1"


def test_br_code_has_the_expected_fields_and_a_valid_checksum():
    code = br_code("chave@exemplo.com", "Maria da Silva Ltda", "São Paulo", 2900, "NXSABC123")
    assert code.startswith("000201010211") and "br.gov.bcb.pix" in code and "chave@exemplo.com" in code
    assert "540529.00" in code and "5802BR" in code and "NXSABC123" in code
    assert "5919Maria da Silva Ltda" in code  # nome sem acento, com o tamanho do campo
    assert code[-8:-4] == "6304" and code[-4:] == crc16(code[:-4])  # o CRC cobre tudo ate "6304"


def test_br_code_normalizes_the_name_and_city_and_validates_the_input():
    code = br_code("11999998888", "José Ação Ltda", "Florianópolis-SC Brasil", 150, "x1")
    assert "Jose Acao Ltda" in code and "6015FLORIANOPOLIS-S" in code  # cidade em maiusculas, no maximo 15 caracteres
    assert "54041.50" in code
    for bad in ((" ", "N", "C", 100, "t"), ("k", "N", "C", 0, "t")):
        with pytest.raises(ValueError):
            br_code(*bad)


# ------------------------------------------------------------------ armazem
@pytest.fixture
def store(tmp_path):
    clock = Clock()
    database = Database(database_url="", sqlite_path=str(tmp_path / "b.sqlite3"))
    result = BillingStore(database, clock=clock)
    result.initialize()
    result.clock = clock
    return result


def test_requests_are_reused_limited_and_cancellable(store):
    first = store.create_request(EMAIL, "pro", 1, 2900)
    assert first.status == PENDING and first.reference.startswith("NXS") and len(first.reference) == 13
    assert store.create_request(EMAIL, "pro", 1, 2900).id == first.id  # o mesmo pedido nao se repete
    store.create_request(EMAIL, "pro", 3, 8700)
    store.create_request(EMAIL, "pro", 12, 34800)
    with pytest.raises(LimitReachedError):
        store.create_request(EMAIL, "pro", 2, 5800)
    assert not store.cancel(first.id, email="outra@exemplo.com") and store.cancel(first.id, email=EMAIL)
    assert store.get(first.id).status == CANCELLED and len(store.pending()) == 2


def test_confirming_activates_extends_and_expires_with_the_clock(store):
    request = store.create_request(EMAIL, "pro", 1, 2900)
    assert store.plan_key(EMAIL) == plans.FREE_KEY
    subscription = store.confirm(request.id, "pix recebido")
    assert subscription.expires_at == START + timedelta(days=30) and store.plan_key(EMAIL) == plans.PRO_KEY
    assert store.get(request.id).status == CONFIRMED and store.get(request.id).note == "pix recebido"
    with pytest.raises(NotFoundError):
        store.confirm(request.id)  # confirmar duas vezes nao soma duas vezes
    store.clock.advance(days=10)
    second = store.confirm(store.create_request(EMAIL, "pro", 3, 8700).id)
    assert second.expires_at == START + timedelta(days=30 + 90)  # renova a partir do vencimento, sem perder dias
    store.clock.advance(days=200)
    assert store.plan_key(EMAIL) == plans.FREE_KEY  # vencida: volta ao gratuito


def test_grant_extends_the_same_plan_and_revoke_removes_it(store):
    first = store.grant(EMAIL, "pro", 15)
    assert first.expires_at == START + timedelta(days=15) and store.plan_key(EMAIL) == plans.PRO_KEY
    assert store.grant(EMAIL, "pro", 15).expires_at == START + timedelta(days=30)  # soma ao vencimento atual
    assert store.revoke(EMAIL) and store.plan_key(EMAIL) == plans.FREE_KEY and not store.revoke(EMAIL)


def test_deleting_user_data_keeps_only_the_confirmed_payment_records(store):
    paid = store.create_request(EMAIL, "pro", 1, 2900)
    store.confirm(paid.id)
    open_request = store.create_request(EMAIL, "pro", 3, 8700)
    store.delete_user_data(EMAIL)
    assert store.subscription(EMAIL) is None and store.get(open_request.id) is None
    assert store.get(paid.id).status == CONFIRMED  # registro de pagamento (obrigacao fiscal)


# ------------------------------------------------------------------ rotas
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
    clock = Clock()
    billing = BillingStore(database, clock=clock)
    library, reports = LibraryStore(database), ReportStore(database)
    tokens, consent, flags = AccountTokens(database), ConsentStore(database), AccountFlags(database)
    for item in (billing, library, reports, tokens, consent, flags):
        item.initialize()
    admin = AdminService(database, billing, tokens, consent, flags)
    catalog = FakeCatalog(works=[make_work(str(n)) for n in range(1, 6)])
    discovery = DiscoveryService([catalog], SlidingWindowLimiter(1000, 60), fallback=None)
    repository = ArticleRepository(lambda raw: ("T", "Resumo suficiente para o teste.", "s"))
    service = AnalysisService(repository, MagicMock(), SlidingWindowLimiter(50, 60))
    inbox = Inbox()

    def build(**overrides):
        values = {"session_secret": "k" * 40, "login_attempts_per_minute": 1000, "admin_token": "a" * 30,
                  "pix_key": "chave@exemplo.com", "pix_name": "Empresa Exemplo", "pix_city": "SAO PAULO", **overrides}
        app = create_app(service, repository, Settings(**values), account_store_factory=lambda: accounts, search_fn=lambda *a, **k: [],
                         discovery=discovery, library=library, reports=reports, billing=billing, mailer=inbox,
                         account_tokens=tokens, consent=consent, flags=flags, admin=admin)
        client = TestClient(app, base_url="http://testserver")
        client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD})
        return client

    return type("Env", (), {"build": staticmethod(build), "billing": billing, "inbox": inbox, "clock": clock})


def test_plans_are_public_and_show_prices_and_limits(env):
    body = env.build(pro_price_cents=4990).get("/api/billing/plans").json()
    pro = next(p for p in body["plans"] if p["key"] == "pro")
    assert pro["priceCents"] == 4990 and pro["price"] == "R$ 49,90" and pro["limits"]["library"] == 500
    assert body["periods"] == [1, 3, 12] and body["pixAvailable"] is True and body["enforced"] is False


def test_requesting_a_plan_returns_the_pix_and_needs_an_account(env):
    client = env.build()
    anonymous = TestClient(client.app, base_url="http://testserver")
    assert anonymous.post("/api/billing/requests", json={"plan": "pro", "months": 1}).status_code == 401
    made = client.post("/api/billing/requests", json={"plan": "pro", "months": 3}).json()
    assert made["amountCents"] == 8700 and made["amount"] == "R$ 87,00" and made["status"] == "pendente"
    assert made["reference"] in made["pix"]["copyPaste"] and made["pix"]["key"] == "chave@exemplo.com"
    assert client.post("/api/billing/requests", json={"plan": "pro", "months": 2}).status_code == 400
    assert client.post("/api/billing/requests", json={"plan": "gratuito", "months": 1}).status_code == 400
    assert client.get("/api/billing/me").json()["requests"][0]["id"] == made["id"]
    assert client.delete(f"/api/billing/requests/{made['id']}").json() == {"cancelled": True}
    assert client.delete(f"/api/billing/requests/{made['id']}").status_code == 404


def test_without_a_pix_key_requests_are_unavailable(env):
    client = env.build(pix_key="")
    assert client.post("/api/billing/requests", json={"plan": "pro", "months": 1}).status_code == 503
    assert client.get("/api/billing/plans").json()["pixAvailable"] is False


def test_admin_routes_need_the_token_and_confirming_activates_and_emails(env):
    client = env.build()
    request_id = client.post("/api/billing/requests", json={"plan": "pro", "months": 1}).json()["id"]
    assert client.get("/api/admin/billing/requests").status_code == 401
    assert client.get("/api/admin/billing/requests", headers={"Authorization": "Bearer errado"}).status_code == 401
    assert env.build(admin_token="").get("/api/admin/billing/requests", headers=ADMIN).status_code == 404  # desativado sem token
    pending = client.get("/api/admin/billing/requests", headers=ADMIN).json()["requests"]
    assert [item["email"] for item in pending] == [EMAIL]
    confirmed = client.post(f"/api/admin/billing/requests/{request_id}/confirm", headers=ADMIN, json={"note": "extrato ok"}).json()
    assert confirmed["confirmed"] and confirmed["plan"] == "pro" and confirmed["expiresAt"].startswith("2026-11-19")
    assert [m.to for m in env.inbox.sent][-1] == EMAIL and "ativo até 19/11/2026" in env.inbox.sent[-1].text
    assert client.post(f"/api/admin/billing/requests/{request_id}/confirm", headers=ADMIN, json={}).status_code == 404
    me = client.get("/api/billing/me").json()
    assert me["plan"] == "pro" and me["active"] is True and me["requests"][0]["status"] == "confirmado"


def test_admin_can_grant_revoke_cancel_and_list_accounts(env):
    client = env.build()
    assert client.post("/api/admin/billing/grant", headers=ADMIN, json={"email": "ninguem@exemplo.com", "plan": "pro", "days": 5}).status_code == 404
    assert client.post("/api/admin/billing/grant", headers=ADMIN, json={"email": EMAIL, "plan": "gratuito", "days": 5}).status_code == 400
    granted = client.post("/api/admin/billing/grant", headers=ADMIN, json={"email": EMAIL, "plan": "pro", "days": 30}).json()
    assert granted["plan"] == "pro"
    listed = client.get("/api/admin/users", headers=ADMIN).json()["users"]
    assert listed[0]["email"] == EMAIL and listed[0]["plan"] == "pro"
    assert client.post("/api/admin/billing/revoke", headers=ADMIN, json={"email": EMAIL}).json() == {"revoked": True}
    request_id = client.post("/api/billing/requests", json={"plan": "pro", "months": 1}).json()["id"]
    assert client.post(f"/api/admin/billing/requests/{request_id}/cancel", headers=ADMIN).json() == {"cancelled": True}


def test_limits_apply_only_when_enforced_and_follow_the_plan(env, monkeypatch):
    monkeypatch.setattr(plans, "FREE", replace(plans.FREE, library=2, lists=1, reports=0))
    relaxed = env.build()  # sem BILLING_ENFORCED: limites do Pro para todos
    for ref in ("1", "2", "3"):
        assert relaxed.post("/api/library", json={"ref": ref}).status_code == 200

    client = env.build(billing_enforced=True)
    client.post("/api/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert client.post("/api/library", json={"ref": "3"}).status_code == 200  # ja salvo: nao ocupa outro lugar
    blocked = client.post("/api/library", json={"ref": "4"})
    assert blocked.status_code == 409 and "plano Gratuito permite até 2 artigos" in blocked.json()["error"]
    assert client.post("/api/lists", json={"name": "A"}).status_code == 200
    assert client.post("/api/lists", json={"name": "B"}).status_code == 409
    list_id = client.get("/api/lists").json()["lists"][0]["id"]
    assert client.post("/api/reports", json={"list_id": list_id}).status_code == 409  # gratuito sem relatorio (neste cenario)
    env.billing.grant(EMAIL, "pro", 30)
    assert client.post("/api/library", json={"ref": "4"}).status_code == 200
    assert client.post("/api/lists", json={"name": "B"}).status_code == 200
    assert client.get("/api/billing/me").json()["usage"]["library"] == 4


def test_production_with_billing_requires_the_pix_data(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "s" * 40)
    monkeypatch.setenv("REQUIRE_TERMS", "0")
    monkeypatch.setenv("BILLING_ENFORCED", "1")
    for name in ("PIX_KEY", "PIX_NAME", "SMTP_HOST"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigurationError, match="PIX_KEY"):
        Settings.from_env()
    monkeypatch.setenv("PIX_KEY", "chave@exemplo.com")
    monkeypatch.setenv("PIX_NAME", "Empresa Exemplo")
    monkeypatch.setenv("PRO_PRICE_CENTS", "3990")
    monkeypatch.setenv("MAX_PRICE_CENTS", "5990")
    settings = Settings.from_env()
    assert settings.billing_enforced and settings.pro_price_cents == 3990 and settings.max_price_cents == 5990 and settings.pix_city == "BRASIL"


def test_max_plan_is_listed_after_pro_with_its_own_price_and_limits(env):
    body = env.build().get("/api/billing/plans").json()
    assert [p["key"] for p in body["plans"]] == ["gratuito", "pro", "max"]
    top = body["plans"][2]
    assert top["priceCents"] == 4990 and top["price"] == "R$ 49,90" and top["limits"] == {"library": 2000, "lists": 200, "reports": 100}
    assert next(p for p in env.build(max_price_cents=5990).get("/api/billing/plans").json()["plans"] if p["key"] == "max")["price"] == "R$ 59,90"


def test_max_subscription_charges_its_price_grants_its_limits_and_shows_in_the_overview(env):
    client = env.build(billing_enforced=True)
    made = client.post("/api/billing/requests", json={"plan": "max", "months": 3}).json()
    assert made["plan"] == "max" and made["amountCents"] == 4990 * 3
    client.post(f"/api/admin/billing/requests/{made['id']}/confirm", headers=ADMIN, json={})
    me = client.get("/api/billing/me").json()
    assert me["plan"] == "max" and me["planName"] == "Max" and me["limits"]["library"] == 2000
    overview = client.get("/api/admin/overview", headers=ADMIN).json()
    assert overview["byPlan"]["max"] == 1 and overview["byPlan"]["pro"] == 0
    granted = client.post("/api/admin/billing/grant", headers=ADMIN, json={"email": EMAIL, "plan": "max", "days": 5}).json()
    assert granted["plan"] == "max"
    assert client.post("/api/admin/billing/grant", headers=ADMIN, json={"email": EMAIL, "plan": "inexistente", "days": 5}).status_code == 400
