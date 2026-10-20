"""Recuperacao de senha e confirmacao de e-mail: tokens de uso unico, links, respostas sem vazar contas e envio por SMTP."""

import re
import smtplib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import mailer as mailer_module
from account_store import AccountStore
from account_tokens import RESET, VERIFY, AccountTokens
from config import ConfigurationError, Settings
from db import Database
from library_store import LibraryStore
from mailer import EmailMessage, LogMailer, MailError, SmtpMailer, mailer_from_env
from ratelimit import SlidingWindowLimiter
from web import create_app
from workflow import AnalysisService, ArticleRepository

EMAIL = "ana@exemplo.com"
PASSWORD = "senha-forte-123"
NEW_PASSWORD = "outra-senha-forte-456"
START = datetime(2026, 10, 20, 12, 0, tzinfo=timezone.utc)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


class Inbox:
    """Mailer de teste: guarda as mensagens enviadas."""

    def __init__(self, fail=False):
        self.sent: list[EmailMessage] = []
        self.fail = fail

    def send(self, message):
        if self.fail:
            raise MailError("fora do ar")
        self.sent.append(message)

    def token(self, index=-1):
        return re.search(r"token=([\w%-]+)", self.sent[index].text).group(1)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "a.sqlite3"))
    monkeypatch.setenv("APP_ENV", "development")
    accounts = AccountStore()
    accounts.initialize()
    database = Database(database_url="", sqlite_path=str(tmp_path / "a.sqlite3"))
    clock = Clock()
    tokens = AccountTokens(database, clock=clock)
    tokens.initialize()
    library = LibraryStore(database)
    library.initialize()
    repository = ArticleRepository(lambda raw: ("T", "Resumo suficiente para o teste.", "s"))
    service = AnalysisService(repository, MagicMock(), SlidingWindowLimiter(50, 60))
    settings = Settings(session_secret="k" * 40, login_attempts_per_minute=1000, app_base_url="https://app.exemplo.com")
    inbox = Inbox()

    def build(mailer="inbox", with_tokens=True):
        app = create_app(
            service, repository, settings, account_store_factory=lambda: accounts, search_fn=lambda *a, **k: [], library=library,
            account_tokens=tokens if with_tokens else None, mailer=inbox if mailer == "inbox" else mailer,
        )
        return TestClient(app, base_url="http://testserver")

    return type("Env", (), {"client": build(), "build": staticmethod(build), "inbox": inbox, "tokens": tokens, "clock": clock, "accounts": accounts})


def register(env):
    response = env.client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 200
    return response


# ------------------------------------------------------------------ confirmacao de e-mail
def test_registration_sends_a_verification_link_and_the_link_confirms_once(env):
    register(env)
    assert [m.to for m in env.inbox.sent] == [EMAIL]
    assert "https://app.exemplo.com/#/confirmar?token=" in env.inbox.sent[0].text
    assert env.client.get("/api/account").json()["emailVerified"] is False
    token = env.inbox.token()
    assert env.client.post("/api/auth/verify", json={"token": token}).json() == {"verified": True, "email": EMAIL}
    assert env.client.get("/api/account").json()["emailVerified"] is True
    assert env.client.post("/api/auth/verify", json={"token": token}).status_code == 400  # uso unico
    assert env.client.post("/api/auth/verify", json={"token": "lixo"}).status_code == 400


def test_verification_link_expires_after_48_hours(env):
    register(env)
    token = env.inbox.token()
    env.clock.advance(hours=49)
    assert env.client.post("/api/auth/verify", json={"token": token}).status_code == 400


def test_resend_verification_needs_an_account_respects_the_cooldown_and_skips_verified(env):
    assert env.client.post("/api/account/resend-verification").status_code == 401
    register(env)
    assert env.client.post("/api/account/resend-verification").json() == {"sent": False, "reason": "wait"}
    assert len(env.inbox.sent) == 1  # o do cadastro acabou de sair: o reenvio espera 1 minuto
    env.clock.advance(minutes=2)
    assert env.client.post("/api/account/resend-verification").json() == {"sent": True} and len(env.inbox.sent) == 2
    env.inbox.fail = True
    env.clock.advance(minutes=2)
    assert env.client.post("/api/account/resend-verification").status_code == 400
    env.inbox.fail = False
    env.tokens.mark_verified(EMAIL)
    assert env.client.post("/api/account/resend-verification").json() == {"alreadyVerified": True}


def test_a_failing_mail_server_never_breaks_registration(env):
    env.inbox.fail = True
    assert env.client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD}).status_code == 200
    assert env.client.get("/api/auth/me").json()["user"] == EMAIL


# ------------------------------------------------------------------ recuperacao de senha
def test_forgot_answers_the_same_for_known_and_unknown_accounts_and_only_mails_the_known(env):
    register(env)
    env.inbox.sent.clear()
    known = env.client.post("/api/auth/forgot", json={"email": " ANA@exemplo.com "})
    unknown = env.client.post("/api/auth/forgot", json={"email": "ninguem@exemplo.com"})
    garbage = env.client.post("/api/auth/forgot", json={"email": ""})
    assert known.status_code == unknown.status_code == garbage.status_code == 200
    assert known.json() == unknown.json() == garbage.json()
    assert [m.to for m in env.inbox.sent] == [EMAIL]
    assert "#/redefinir?token=" in env.inbox.sent[0].text


def test_forgot_is_rate_limited_per_address_and_never_uses_the_host_header_for_links(env):
    register(env)
    env.inbox.sent.clear()
    env.client.post("/api/auth/forgot", json={"email": EMAIL}, headers={"Host": "atacante.example"})
    env.client.post("/api/auth/forgot", json={"email": EMAIL})
    assert len(env.inbox.sent) == 1  # o segundo pedido dentro de 1 minuto nao envia outro
    assert env.inbox.sent[0].text.count("https://app.exemplo.com/#/redefinir") == 1 and "atacante" not in env.inbox.sent[0].text


def test_reset_changes_the_password_once_and_the_old_password_stops_working(env):
    register(env)
    env.inbox.sent.clear()
    env.client.post("/api/auth/forgot", json={"email": EMAIL})
    token = env.inbox.token()
    assert env.client.post("/api/auth/reset", json={"token": token, "password": "curta"}).status_code == 400
    assert env.tokens.peek(token, RESET) == EMAIL  # senha fraca nao gasta o link
    assert env.client.post("/api/auth/reset", json={"token": token, "password": NEW_PASSWORD}).json() == {"ok": True}
    assert env.client.post("/api/auth/reset", json={"token": token, "password": NEW_PASSWORD}).status_code == 400
    assert not env.accounts.authenticate(EMAIL, PASSWORD) and env.accounts.authenticate(EMAIL, NEW_PASSWORD)
    assert env.tokens.is_verified(EMAIL)  # abrir o link prova que a pessoa controla a caixa de e-mail


def test_reset_link_expires_after_one_hour_and_a_new_request_replaces_the_old_link(env):
    register(env)
    env.client.post("/api/auth/forgot", json={"email": EMAIL})
    first = env.inbox.token()
    env.clock.advance(hours=2)
    assert env.client.post("/api/auth/reset", json={"token": first, "password": NEW_PASSWORD}).status_code == 400
    env.tokens.issue(EMAIL, RESET)  # novo pedido apaga o anterior
    assert env.tokens.peek(first, RESET) is None


def test_a_verification_token_cannot_reset_a_password(env):
    register(env)
    token = env.inbox.token()
    assert env.client.post("/api/auth/reset", json={"token": token, "password": NEW_PASSWORD}).status_code == 400


def test_without_a_mail_provider_recovery_is_unavailable_and_the_account_says_so(env):
    client = env.build(mailer=None)
    assert client.post("/api/auth/forgot", json={"email": EMAIL}).status_code == 503
    client.post("/api/auth/register", json={"email": EMAIL, "password": PASSWORD})
    summary = client.get("/api/account").json()
    assert summary["emailEnabled"] is False and client.post("/api/account/resend-verification").status_code == 503


def test_deleting_the_account_removes_tokens_and_the_verification_mark(env):
    register(env)
    env.client.post("/api/auth/verify", json={"token": env.inbox.token()})
    assert env.client.request("DELETE", "/api/account", json={"password": PASSWORD}).status_code == 200
    assert not env.tokens.is_verified(EMAIL)
    assert env.tokens.last_issued(EMAIL, VERIFY) is None


def test_export_reports_the_verification_state(env):
    register(env)
    exported = env.client.get("/api/account/export").json()
    assert exported["account"]["emailVerified"] is False


# ------------------------------------------------------------------ tokens
def test_tokens_are_stored_only_as_hashes(env):
    raw = env.tokens.issue(EMAIL, RESET)
    rows = env.tokens._db.query("SELECT token_hash FROM account_tokens")  # noqa: SLF001
    assert raw not in rows[0][0] and len(rows[0][0]) == 64


# ------------------------------------------------------------------ envio e configuracao
def test_smtp_mailer_uses_starttls_login_and_wraps_failures(monkeypatch):
    server = MagicMock()
    server.__enter__.return_value = server
    smtp = MagicMock(return_value=server)
    monkeypatch.setattr(smtplib, "SMTP", smtp)
    SmtpMailer("smtp.exemplo.com", 587, "usuario", "segredo", "no-reply@exemplo.com").send(EmailMessage("a@b.com", "Assunto", "Corpo"))
    smtp.assert_called_once_with("smtp.exemplo.com", 587, timeout=mailer_module.SMTP_TIMEOUT)
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("usuario", "segredo")
    sent = server.send_message.call_args.args[0]
    assert sent["To"] == "a@b.com" and sent["From"] == "no-reply@exemplo.com" and sent["Subject"] == "Assunto"
    server.send_message.side_effect = smtplib.SMTPException("segredo-no-erro")
    with pytest.raises(MailError) as error:
        SmtpMailer("h", 25, sender="x@y.z", security="none").send(EmailMessage("a@b.com", "A", "B"))
    assert "segredo" not in str(error.value)


def test_mailer_from_env(monkeypatch):
    for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM", "SMTP_SECURITY"):
        monkeypatch.delenv(name, raising=False)
    assert mailer_from_env(production=True) is None  # nunca o LogMailer em producao: o log mostraria os links
    assert isinstance(mailer_from_env(production=False), LogMailer)
    monkeypatch.setenv("SMTP_HOST", "smtp.exemplo.com")
    with pytest.raises(ValueError, match="SMTP_FROM"):
        mailer_from_env(production=True)
    monkeypatch.setenv("SMTP_FROM", "no-reply@exemplo.com")
    assert isinstance(mailer_from_env(production=True), SmtpMailer)
    monkeypatch.setenv("SMTP_PORT", "abc")
    with pytest.raises(ValueError, match="SMTP_PORT"):
        mailer_from_env(production=True)


def test_production_with_smtp_requires_an_https_base_url(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("SESSION_SECRET", "s" * 40)
    monkeypatch.setenv("REQUIRE_TERMS", "0")  # este teste e so sobre APP_BASE_URL
    monkeypatch.setenv("SMTP_HOST", "smtp.exemplo.com")
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    with pytest.raises(ConfigurationError, match="APP_BASE_URL"):
        Settings.from_env()
    monkeypatch.setenv("APP_BASE_URL", "https://app.exemplo.com/")
    assert Settings.from_env().app_base_url == "https://app.exemplo.com"


def test_log_mailer_writes_instead_of_sending(caplog):
    LogMailer().send(EmailMessage("a@b.com", "Assunto", "Corpo"))
