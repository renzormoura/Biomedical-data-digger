"""Biblioteca pessoal, etiquetas e listas de leitura por conta.

Cada artigo salvo guarda um *retrato* dos metadados (`Work.to_dict`), de modo que a biblioteca
abre sem consultar a fonte e sobrevive a mudancas nas APIs. Toda operacao confere o dono; uma
lista pode ser compartilhada por um link publico somente leitura que nao expoe o e-mail do dono.
"""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache

from catalog import Work
from db import Database, Transaction
from domain import LimitReachedError, NotFoundError

MAX_ITEMS = 500
MAX_LISTS = 50
MAX_LIST_ITEMS = 200
MAX_TAGS = 12
MAX_TAG_CHARS = 30
MAX_NAME_CHARS = 80
MAX_ABSTRACT_CHARS = 4000

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS library_items (
        user_email TEXT NOT NULL, ref TEXT NOT NULL, data TEXT NOT NULL, tags TEXT NOT NULL,
        saved_at TEXT NOT NULL, PRIMARY KEY (user_email, ref))""",
    """CREATE TABLE IF NOT EXISTS reading_lists (
        id TEXT PRIMARY KEY, owner_email TEXT NOT NULL, name TEXT NOT NULL, share_token TEXT UNIQUE,
        created_at TEXT NOT NULL)""",
    """CREATE TABLE IF NOT EXISTS reading_list_items (
        list_id TEXT NOT NULL REFERENCES reading_lists(id) ON DELETE CASCADE, ref TEXT NOT NULL,
        data TEXT NOT NULL, position INTEGER NOT NULL, PRIMARY KEY (list_id, ref))""",
    "CREATE INDEX IF NOT EXISTS idx_lists_owner ON reading_lists (owner_email)",
)


@dataclass(frozen=True)
class LibraryItem:
    work: Work
    tags: tuple[str, ...]
    saved_at: str


@dataclass(frozen=True)
class ReadingList:
    id: str
    name: str
    share_token: str | None
    created_at: str
    works: tuple[Work, ...] = field(default_factory=tuple)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _snapshot(work: Work) -> str:
    data = work.to_dict()
    data["abstract"] = str(data["abstract"])[:MAX_ABSTRACT_CHARS]
    return json.dumps(data, ensure_ascii=False)


def _work(raw: str) -> Work:
    try:
        data = json.loads(raw)
    except ValueError:
        data = {}
    return Work.from_dict(data if isinstance(data, dict) else {})


def clean_tags(tags: list[str]) -> tuple[str, ...]:
    cleaned: list[str] = []
    for tag in tags:
        text = " ".join("".join(ch if ch.isprintable() else " " for ch in str(tag)).split())[:MAX_TAG_CHARS]
        if text and text.lower() not in {t.lower() for t in cleaned}:
            cleaned.append(text)
    return tuple(cleaned[:MAX_TAGS])


def clean_name(name: str) -> str:
    return " ".join("".join(ch if ch.isprintable() else " " for ch in name).split())[:MAX_NAME_CHARS]


class LibraryStore:
    def __init__(self, database: Database | None = None) -> None:
        self._db = database or Database()

    def initialize(self) -> None:
        with self._db.transaction() as tx:
            for statement in _SCHEMA:
                tx.execute(statement)

    # ------------------------------------------------------------------ biblioteca
    def save(self, user: str, work: Work) -> None:
        with self._db.transaction() as tx:
            existing = tx.query("SELECT 1 FROM library_items WHERE user_email = ? AND ref = ?", (user, work.ref))
            if not existing:
                count = tx.query("SELECT COUNT(*) FROM library_items WHERE user_email = ?", (user,))[0][0]
                if count >= MAX_ITEMS:
                    raise LimitReachedError(f"Sua biblioteca chegou ao limite de {MAX_ITEMS} artigos.")
            tx.execute(
                """INSERT INTO library_items (user_email, ref, data, tags, saved_at) VALUES (?, ?, ?, '[]', ?)
                   ON CONFLICT (user_email, ref) DO UPDATE SET data = excluded.data""",
                (user, work.ref, _snapshot(work), _now()),
            )

    def remove(self, user: str, ref: str) -> None:
        self._db.execute("DELETE FROM library_items WHERE user_email = ? AND ref = ?", (user, ref))

    def items(self, user: str) -> list[LibraryItem]:
        rows = self._db.query(
            "SELECT data, tags, saved_at FROM library_items WHERE user_email = ? ORDER BY saved_at DESC, ref", (user,)
        )
        return [LibraryItem(_work(data), _load_tags(tags), saved_at) for data, tags, saved_at in rows]

    def saved_refs(self, user: str, refs: list[str]) -> set[str]:
        if not refs:
            return set()
        marks = ",".join("?" for _ in refs)
        # so os marcadores "?" sao montados dinamicamente; os valores sempre vao como parametros
        sql = f"SELECT ref FROM library_items WHERE user_email = ? AND ref IN ({marks})"  # noqa: S608
        rows = self._db.query(sql, (user, *refs))
        return {row[0] for row in rows}

    def set_tags(self, user: str, ref: str, tags: list[str]) -> tuple[str, ...]:
        cleaned = clean_tags(tags)
        changed = self._db.execute(
            "UPDATE library_items SET tags = ? WHERE user_email = ? AND ref = ?",
            (json.dumps(cleaned, ensure_ascii=False), user, ref),
        )
        if not changed:
            raise NotFoundError("Artigo não encontrado na sua biblioteca.")
        return cleaned

    # ------------------------------------------------------------------ listas
    def create_list(self, user: str, name: str) -> ReadingList:
        name = clean_name(name)
        if not name:
            raise NotFoundError("Dê um nome à lista.")
        with self._db.transaction() as tx:
            if tx.query("SELECT COUNT(*) FROM reading_lists WHERE owner_email = ?", (user,))[0][0] >= MAX_LISTS:
                raise LimitReachedError(f"Você chegou ao limite de {MAX_LISTS} listas.")
            list_id, created = uuid.uuid4().hex, _now()
            tx.execute("INSERT INTO reading_lists (id, owner_email, name, created_at) VALUES (?, ?, ?, ?)",
                       (list_id, user, name, created))
        return ReadingList(id=list_id, name=name, share_token=None, created_at=created)

    def _owned(self, tx: Transaction, user: str, list_id: str) -> None:
        if not tx.query("SELECT 1 FROM reading_lists WHERE id = ? AND owner_email = ?", (list_id, user)):
            raise NotFoundError("Lista não encontrada.")

    def delete_list(self, user: str, list_id: str) -> None:
        with self._db.transaction() as tx:
            self._owned(tx, user, list_id)
            tx.execute("DELETE FROM reading_list_items WHERE list_id = ?", (list_id,))
            tx.execute("DELETE FROM reading_lists WHERE id = ?", (list_id,))

    def lists(self, user: str) -> list[ReadingList]:
        rows = self._db.query(
            "SELECT id, name, share_token, created_at FROM reading_lists WHERE owner_email = ? ORDER BY created_at, id",
            (user,),
        )
        return [self._with_items(ReadingList(*row)) for row in rows]

    def _with_items(self, reading_list: ReadingList) -> ReadingList:
        rows = self._db.query("SELECT data FROM reading_list_items WHERE list_id = ? ORDER BY position", (reading_list.id,))
        return ReadingList(reading_list.id, reading_list.name, reading_list.share_token, reading_list.created_at,
                           tuple(_work(data) for (data,) in rows))

    def add_to_list(self, user: str, list_id: str, work: Work) -> None:
        with self._db.transaction() as tx:
            self._owned(tx, user, list_id)
            if tx.query("SELECT 1 FROM reading_list_items WHERE list_id = ? AND ref = ?", (list_id, work.ref)):
                return
            count = tx.query("SELECT COUNT(*) FROM reading_list_items WHERE list_id = ?", (list_id,))[0][0]
            if count >= MAX_LIST_ITEMS:
                raise LimitReachedError(f"Esta lista chegou ao limite de {MAX_LIST_ITEMS} artigos.")
            tx.execute("INSERT INTO reading_list_items (list_id, ref, data, position) VALUES (?, ?, ?, ?)",
                       (list_id, work.ref, _snapshot(work), count))

    def remove_from_list(self, user: str, list_id: str, ref: str) -> None:
        with self._db.transaction() as tx:
            self._owned(tx, user, list_id)
            tx.execute("DELETE FROM reading_list_items WHERE list_id = ? AND ref = ?", (list_id, ref))

    # ------------------------------------------------------------------ compartilhamento
    def share(self, user: str, list_id: str) -> str:
        """Gera (ou devolve) o token do link publico somente leitura."""
        with self._db.transaction() as tx:
            self._owned(tx, user, list_id)
            current = tx.query("SELECT share_token FROM reading_lists WHERE id = ?", (list_id,))[0][0]
            if current:
                return str(current)
            token = secrets.token_urlsafe(9)
            tx.execute("UPDATE reading_lists SET share_token = ? WHERE id = ?", (token, list_id))
            return token

    def unshare(self, user: str, list_id: str) -> None:
        with self._db.transaction() as tx:
            self._owned(tx, user, list_id)
            tx.execute("UPDATE reading_lists SET share_token = NULL WHERE id = ?", (list_id,))

    def shared(self, token: str) -> ReadingList | None:
        """Lista publica pelo token. Nao devolve o e-mail do dono."""
        if not token or len(token) > 64:
            return None
        rows = self._db.query("SELECT id, name, share_token, created_at FROM reading_lists WHERE share_token = ?", (token,))
        return self._with_items(ReadingList(*rows[0])) if rows else None


def _load_tags(raw: str) -> tuple[str, ...]:
    try:
        value = json.loads(raw)
    except ValueError:
        return ()
    return tuple(str(t) for t in value) if isinstance(value, list) else ()


@lru_cache(maxsize=1)
def get_library_store() -> LibraryStore:
    store = LibraryStore()
    store.initialize()
    return store
