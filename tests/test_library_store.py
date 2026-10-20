import pytest

from catalog import Work
from citations import Author
from db import Database, DatabaseError
from domain import LimitReachedError, NotFoundError
from library_store import (
    MAX_ABSTRACT_CHARS,
    MAX_ITEMS,
    MAX_LIST_ITEMS,
    MAX_LISTS,
    MAX_TAG_CHARS,
    MAX_TAGS,
    LibraryStore,
    clean_name,
    clean_tags,
)

ANA, BIA = "ana@exemplo.com", "bia@exemplo.com"


def work(ref="1", **overrides):
    base = {"ref": ref, "title": f"Artigo {ref}", "authors": (Author("Silva", "Ana"),), "journal": "Revista", "year": 2022,
            "doi": f"10.0000/{ref}", "abstract": "Resumo.", "keywords": ("a", "b"), "source": "Europe PMC"}
    base.update(overrides)
    return Work(**base)


@pytest.fixture
def store(tmp_path):
    instance = LibraryStore(Database(database_url="", sqlite_path=str(tmp_path / "lib.sqlite3")))
    instance.initialize()
    return instance


# ------------------------------------------------------------------ banco
def test_database_translates_placeholders_for_postgres_only():
    from db import Transaction

    assert Transaction(None, postgres=True)._sql("SELECT ? , ?") == "SELECT %s , %s"
    assert Transaction(None, postgres=False)._sql("SELECT ? , ?") == "SELECT ? , ?"


@pytest.mark.sqlite_only
def test_database_picks_backend_from_url_and_normalizes_postgres_scheme():
    assert Database(database_url="", sqlite_path="x.db").uses_postgres is False
    pg = Database(database_url="postgres://u:p@host/db", sqlite_path="x.db")
    assert pg.uses_postgres and pg.url == "postgresql://u:p@host/db"


def test_transaction_rolls_back_on_error(tmp_path):
    db = Database(database_url="", sqlite_path=str(tmp_path / "t.sqlite3"))
    db.execute("CREATE TABLE t (a TEXT PRIMARY KEY)")
    with pytest.raises(RuntimeError), db.transaction() as tx:
        tx.execute("INSERT INTO t VALUES (?)", ("x",))
        raise RuntimeError("falhou")
    assert db.query("SELECT COUNT(*) FROM t") == [(0,)]


def test_missing_psycopg_gives_a_safe_error(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "psycopg", None)
    with pytest.raises(DatabaseError, match="psycopg"):
        Database(database_url="postgresql://u:senha-secreta@h/d").query("SELECT 1")


# ------------------------------------------------------------------ biblioteca
def test_save_list_and_remove_items_per_user(store):
    store.save(ANA, work("1"))
    store.save(ANA, work("2"))
    store.save(BIA, work("3"))
    assert sorted(i.work.ref for i in store.items(ANA)) == ["1", "2"]
    assert [i.work.ref for i in store.items(BIA)] == ["3"]
    store.remove(ANA, "1")
    assert [i.work.ref for i in store.items(ANA)] == ["2"]
    store.remove(ANA, "nao-existe")  # idempotente


def test_snapshot_roundtrip_and_abstract_is_truncated(store):
    store.save(ANA, work("1", abstract="x" * 10_000, study_types=("Meta-análise",), open_access=True))
    saved = store.items(ANA)[0].work
    assert saved.title == "Artigo 1" and saved.authors == (Author("Silva", "Ana"),) and saved.open_access
    assert saved.study_types == ("Meta-análise",) and len(saved.abstract) == MAX_ABSTRACT_CHARS


def test_saving_twice_keeps_tags_and_refreshes_data(store):
    store.save(ANA, work("1"))
    store.set_tags(ANA, "1", ["TCC"])
    store.save(ANA, work("1", title="Título atualizado"))
    item = store.items(ANA)[0]
    assert item.tags == ("TCC",) and item.work.title == "Título atualizado" and len(store.items(ANA)) == 1


def test_library_limit(store, monkeypatch):
    import library_store

    monkeypatch.setattr(library_store, "MAX_ITEMS", 2)
    store.save(ANA, work("1"))
    store.save(ANA, work("2"))
    store.save(ANA, work("2"))  # reenvio nao conta como novo
    with pytest.raises(LimitReachedError, match="limite"):
        store.save(ANA, work("3"))
    store.save(BIA, work("3"))  # o limite e por conta
    assert MAX_ITEMS == 500


def test_saved_refs_marks_only_the_users_items(store):
    store.save(ANA, work("1"))
    store.save(BIA, work("2"))
    assert store.saved_refs(ANA, ["1", "2", "3"]) == {"1"} and store.saved_refs(ANA, []) == set()


def test_tags_are_cleaned_deduplicated_and_limited(store):
    store.save(ANA, work("1"))
    tags = store.set_tags(ANA, "1", ["TCC", "tcc", "  Saúde \n pública ", "", "x" * 100] + [f"t{i}" for i in range(30)])
    assert tags[0] == "TCC" and tags[1] == "Saúde pública" and len(tags[2]) == MAX_TAG_CHARS
    assert len(tags) == MAX_TAGS and len({t.lower() for t in tags}) == len(tags)
    assert store.items(ANA)[0].tags == tags


def test_tags_on_unsaved_or_foreign_item_are_rejected(store):
    store.save(BIA, work("9"))
    with pytest.raises(NotFoundError):
        store.set_tags(ANA, "9", ["x"])


def test_clean_helpers():
    assert clean_tags(["a", "A", "b"]) == ("a", "b")
    assert clean_name("  Minha \x00 lista  ") == "Minha lista" and len(clean_name("x" * 500)) == 80


# ------------------------------------------------------------------ listas
def test_lists_are_private_to_their_owner(store):
    reading = store.create_list(ANA, "Leituras")
    store.add_to_list(ANA, reading.id, work("1"))
    assert [item.name for item in store.lists(ANA)] == ["Leituras"] and store.lists(BIA) == []
    for action in (
        lambda: store.add_to_list(BIA, reading.id, work("2")),
        lambda: store.remove_from_list(BIA, reading.id, "1"),
        lambda: store.delete_list(BIA, reading.id),
        lambda: store.share(BIA, reading.id),
        lambda: store.unshare(BIA, reading.id),
    ):
        with pytest.raises(NotFoundError):
            action()
    assert len(store.lists(ANA)[0].works) == 1  # nada foi alterado


def test_list_items_keep_insertion_order_without_duplicates(store):
    reading = store.create_list(ANA, "Ordem")
    for ref in ("3", "1", "2", "1"):
        store.add_to_list(ANA, reading.id, work(ref))
    assert [w.ref for w in store.lists(ANA)[0].works] == ["3", "1", "2"]
    store.remove_from_list(ANA, reading.id, "1")
    assert [w.ref for w in store.lists(ANA)[0].works] == ["3", "2"]


def test_list_name_is_required_and_cleaned(store):
    with pytest.raises(NotFoundError, match="nome"):
        store.create_list(ANA, "  \n ")
    assert store.create_list(ANA, "  Aula   1 ").name == "Aula 1"


def test_list_limits(store, monkeypatch):
    import library_store

    monkeypatch.setattr(library_store, "MAX_LISTS", 1)
    first = store.create_list(ANA, "Uma")
    with pytest.raises(LimitReachedError):
        store.create_list(ANA, "Duas")
    monkeypatch.setattr(library_store, "MAX_LIST_ITEMS", 1)
    store.add_to_list(ANA, first.id, work("1"))
    with pytest.raises(LimitReachedError):
        store.add_to_list(ANA, first.id, work("2"))
    assert (MAX_LISTS, MAX_LIST_ITEMS) == (50, 200)


def test_deleting_a_list_removes_its_items_and_share_link(store):
    reading = store.create_list(ANA, "Temporária")
    store.add_to_list(ANA, reading.id, work("1"))
    token = store.share(ANA, reading.id)
    store.delete_list(ANA, reading.id)
    assert store.lists(ANA) == [] and store.shared(token) is None
    assert store._db.query("SELECT COUNT(*) FROM reading_list_items") == [(0,)]


# ------------------------------------------------------------------ compartilhamento
def test_share_link_is_stable_public_readonly_and_hides_the_owner(store):
    reading = store.create_list(ANA, "Turma 3")
    store.add_to_list(ANA, reading.id, work("1"))
    token = store.share(ANA, reading.id)
    assert store.share(ANA, reading.id) == token and len(token) >= 12
    public = store.shared(token)
    assert public.name == "Turma 3" and [w.ref for w in public.works] == ["1"]
    assert ANA not in repr(public) and not hasattr(public, "owner_email")


def test_unshare_revokes_the_link_and_a_new_share_makes_a_new_token(store):
    reading = store.create_list(ANA, "Rev")
    token = store.share(ANA, reading.id)
    store.unshare(ANA, reading.id)
    assert store.shared(token) is None
    assert store.share(ANA, reading.id) != token


@pytest.mark.parametrize("bad", ["", "nao-existe", "x" * 200, "' OR 1=1 --", "%"])
def test_shared_lookup_rejects_unknown_or_hostile_tokens(store, bad):
    store.create_list(ANA, "Qualquer")
    assert store.shared(bad) is None


def test_corrupted_snapshot_does_not_break_listing(store):
    store.save(ANA, work("1"))
    store._db.execute("UPDATE library_items SET data = 'nao-json', tags = '{{' WHERE ref = '1'")
    item = store.items(ANA)[0]
    assert item.work.title == "Título não informado" and item.tags == ()
