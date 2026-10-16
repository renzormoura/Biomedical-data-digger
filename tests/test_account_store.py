import pytest

import account_store as module
from account_store import AccountStore, InvalidCredentialsFormat, validate_credentials


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "accounts.sqlite3"))
    monkeypatch.setenv("APP_ENV", "development")
    instance = AccountStore()
    instance.initialize()
    return instance


def test_create_and_authenticate(store):
    assert store.create_user("Ana@Example.com", "senha-forte-1")
    assert store.authenticate("ana@example.com", "senha-forte-1")
    assert not store.authenticate("ana@example.com", "outra-senha")


def test_duplicate_email_is_rejected_case_insensitively(store):
    assert store.create_user("ana@example.com", "senha-forte-1")
    assert not store.create_user("ANA@example.com", "senha-forte-2")


def test_unknown_user_does_not_authenticate_and_pays_hash_cost(store, monkeypatch):
    calls = []
    original = AccountStore._password_digest
    monkeypatch.setattr(AccountStore, "_password_digest", staticmethod(lambda p, s: calls.append(1) or original(p, s)))
    assert not store.authenticate("ghost@example.com", "qualquer-coisa")
    assert calls, "deveria gastar PBKDF2 mesmo sem usuario (anti-timing)"


def test_passwords_are_salted_and_not_stored_in_clear(store, tmp_path):
    store.create_user("a@example.com", "mesma-senha-123")
    store.create_user("b@example.com", "mesma-senha-123")
    with store._connection() as connection:
        rows = connection.execute("SELECT password_hash, password_salt FROM users").fetchall()
    assert rows[0][0] != rows[1][0] and rows[0][1] != rows[1][1]
    assert all("mesma-senha-123" not in cell for row in rows for cell in row)


def test_production_requires_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(module.AccountStoreError):
        AccountStore()


def test_importing_module_does_not_touch_database():
    assert not hasattr(module, "account_store")


@pytest.mark.parametrize(
    "email,password",
    [
        ("", "senha-forte-1"),
        ("sem-arroba", "senha-forte-1"),
        ("a@b", "senha-forte-1"),
        ("a@example.com", ""),
        ("a@example.com", "curta"),
        ("a@example.com", "x" * 129),
        ("a@example.com", "password"),
        ("a@example.com", "12345678"),
    ],
)
def test_validate_credentials_rejects_bad_input(email, password):
    with pytest.raises(InvalidCredentialsFormat):
        validate_credentials(email, password)


def test_validate_credentials_normalizes():
    assert validate_credentials("  Ana@Example.COM ", "  senha-forte-1 ") == ("ana@example.com", "senha-forte-1")
