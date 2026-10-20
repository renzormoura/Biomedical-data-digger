"""Confere se o banco apontado por DATABASE_URL (ou o SQLite local) esta pronto para o servico.

Uso (na raiz do repositorio):  DATABASE_URL=postgresql://... python scripts/verificar_banco.py

Faz, nesta ordem: conecta; cria as tabelas que faltarem (os mesmos `initialize()` da subida, que so usam
`CREATE TABLE IF NOT EXISTS`); confere se todas as tabelas esperadas existem; e testa um ciclo de escrita e leitura que
nao deixa rastros. Imprime um resumo e sai com codigo 1 se algo falhar. Rode antes do primeiro deploy e depois de
trocar de banco. Nao apaga nem altera dados existentes.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "biomedical-article-summariser"))

from account_consent import ConsentStore  # noqa: E402
from account_store import AccountStore  # noqa: E402
from account_tokens import AccountTokens  # noqa: E402
from alerts import AlertStore  # noqa: E402
from db import Database, DatabaseError  # noqa: E402
from feed import FeedStore  # noqa: E402
from library_store import LibraryStore  # noqa: E402
from notifications import NotificationStore  # noqa: E402
from profiles import ProfileStore  # noqa: E402
from reports import ReportStore  # noqa: E402

EXPECTED_TABLES = (
    "users", "account_tokens", "email_verification", "terms_acceptance", "user_profiles", "library_items", "reading_lists", "reading_list_items",
    "saved_analyses", "reports", "report_items", "report_substances", "report_versions", "report_sources", "report_log",
    "interest_prefs", "interest_baselines", "alert_seen", "alerts", "notifications", "retraction_status", "regulatory_state",
    "watch_state", "notification_prefs", "feed_items", "feed_state",
)


def existing_tables(database: Database) -> set[str]:
    if database.uses_postgres:
        rows = database.query("SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()")
    else:
        rows = database.query("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {str(row[0]) for row in rows}


def main() -> int:
    database = Database()
    kind = "PostgreSQL" if database.uses_postgres else f"SQLite ({database.sqlite_path})"
    try:
        database.query("SELECT 1")
    except (DatabaseError, Exception) as error:  # noqa: BLE001 - qualquer falha de conexao interessa aqui
        print(f"FALHA ao conectar em {kind}: {type(error).__name__}", file=sys.stderr)
        return 1
    print(f"Conectado: {kind}")
    for store in (AccountStore(), AccountTokens(database), ConsentStore(database), ProfileStore(database), LibraryStore(database), ReportStore(database),
                  AlertStore(database), NotificationStore(database), FeedStore(database)):
        store.initialize()
    present = existing_tables(database)
    missing = [name for name in EXPECTED_TABLES if name not in present]
    if missing:
        print(f"FALHA: tabelas ausentes: {', '.join(missing)}", file=sys.stderr)
        return 1
    print(f"Tabelas: {len(EXPECTED_TABLES)} de {len(EXPECTED_TABLES)} presentes")

    probe = f"verificacao-{uuid.uuid4().hex}"
    try:
        database.execute("INSERT INTO watch_state (user_email, last_run) VALUES (?, ?)", (probe, "2000-01-01T00:00:00+00:00"))
        found = database.query("SELECT user_email FROM watch_state WHERE user_email = ?", (probe,))
    finally:
        database.execute("DELETE FROM watch_state WHERE user_email = ?", (probe,))
    if not found:
        print("FALHA: a escrita de teste nao foi lida de volta", file=sys.stderr)
        return 1
    print("Escrita e leitura: ok (sem rastros)")
    users = database.query("SELECT COUNT(*) FROM users")[0][0]
    print(f"Contas cadastradas: {users}")
    print("Banco pronto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
