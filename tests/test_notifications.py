"""Notificacoes do sininho: retratacao, mudanca regulatoria, novidades dos relatorios, preferencias e rotas."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import notifications as nt
from account_store import AccountStore
from alerts import AlertService, AlertStore
from brasil import anvisa, conitec, consulta, rename
from catalog import Work
from citations import Author
from config import Settings
from db import Database
from discovery import DiscoveryService
from domain import NexusError, RateLimitedError
from library_store import LibraryStore
from notifications import (
    KINDS,
    NewNotification,
    NotificationService,
    NotificationStore,
    describe_regulatory_change,
    regulatory_fingerprint,
)
from profiles import ProfileStore
from ratelimit import SlidingWindowLimiter
from reports import ReportStore
from web import create_app
from workflow import AnalysisService, ArticleRepository

EMAIL = "ana@exemplo.com"
PASSWORD = "senha-forte-123"
START = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def make_work(ref, **overrides):
    base = {"ref": ref, "title": f"Estudo {ref}", "authors": (Author("Silva", "Ana"),), "journal": "Revista X", "year": 2025, "doi": f"10.1/{ref}",
            "abstract": "Background: x. Results: reduced 12% (p<0.05).", "source": "Europe PMC"}
    base.update(overrides)
    return Work(**base)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


@pytest.fixture(scope="module")
def bases():
    return anvisa.carregar(), conitec.carregar(), rename.carregar()


@pytest.fixture
def parts(tmp_path, monkeypatch, bases):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "a.sqlite3"))
    AccountStore().initialize()
    database = Database(database_url="", sqlite_path=str(tmp_path / "a.sqlite3"))
    library, reports, store = LibraryStore(database), ReportStore(database), NotificationStore(database)
    for item in (library, reports, store):
        item.initialize()
    clock = Clock()
    remote: dict[str, Work] = {}
    calls: list[str] = []

    def fetch(ref):
        calls.append(ref)
        if ref == "falha":
            raise NexusError("fonte fora do ar")
        if ref == "limite":
            raise RateLimitedError("muitas consultas")
        return remote.get(ref)

    holder = {"bases": bases}
    service = NotificationService(store, fetch_work=fetch, library=library, reports=reports, bases=lambda: holder["bases"], clock=clock)
    return type("Parts", (), {"service": service, "store": store, "library": library, "reports": reports, "clock": clock, "remote": remote,
                              "calls": calls, "holder": holder, "database": database})


# ------------------------------------------------------------------ caixa e preferencias
def test_store_dedupes_groups_and_limits(parts):
    store = parts.store
    first = NewNotification("retratacao", "k1", "Titulo", "Corpo", "#/x")
    assert store.add(EMAIL, first) and not store.add(EMAIL, first)
    assert store.add(EMAIL, NewNotification("relatorio-lista", "l1", "A", "b", "#/r", group_key="g"))
    assert store.add(EMAIL, NewNotification("relatorio-lista", "l2", "B", "b", "#/r", group_key="g"))  # substitui o l1 (nao lido)
    titles = sorted(n.title for n in store.notifications(EMAIL))
    assert titles == ["B", "Titulo"] and store.unread(EMAIL) == 2
    only = store.notifications(EMAIL)[0]
    assert only.priority == KINDS[only.kind][0] and only.read is False
    assert store.add("outra@exemplo.com", first)  # a chave e por conta


def test_store_trims_the_box_and_isolates_accounts(parts, monkeypatch):
    monkeypatch.setattr(nt, "MAX_NOTIFICATIONS", 3)
    for index in range(5):
        parts.store.add(EMAIL, NewNotification("retratacao", f"k{index}", f"T{index}", "", "#/"))
    assert len(parts.store.notifications(EMAIL)) == 3 and parts.store.notifications("outra@exemplo.com") == []


def test_mark_read_and_dismiss(parts):
    parts.store.add(EMAIL, NewNotification("retratacao", "a", "A", "", "#/"))
    parts.store.add(EMAIL, NewNotification("regulatorio", "b", "B", "", "#/"))
    first = parts.store.notifications(EMAIL)[0]
    assert parts.store.mark_read(EMAIL, first.id) and parts.store.unread(EMAIL) == 1
    assert not parts.store.mark_read(EMAIL, "inexistente") and not parts.store.mark_read("outra@exemplo.com", first.id)
    parts.store.mark_read(EMAIL)
    assert parts.store.unread(EMAIL) == 0
    parts.store.dismiss("outra@exemplo.com", first.id)
    assert len(parts.store.notifications(EMAIL)) == 2
    parts.store.dismiss(EMAIL, first.id)
    assert len(parts.store.notifications(EMAIL)) == 1


def test_prefs_default_on_ignore_unknown_and_survive_corruption(parts):
    assert parts.store.prefs(EMAIL) == dict.fromkeys(KINDS, True)
    saved = parts.store.set_prefs(EMAIL, {"retratacao": False, "inexistente": False})
    assert saved["retratacao"] is False and "inexistente" not in saved and saved["regulatorio"] is True
    assert parts.store.prefs(EMAIL)["retratacao"] is False
    parts.store._db.execute("UPDATE notification_prefs SET data = 'quebrado'")  # noqa: SLF001
    assert parts.store.prefs(EMAIL) == dict.fromkeys(KINDS, True)


def test_retraction_status_roundtrip_and_chunks(parts):
    parts.store.set_retraction("1", True)
    parts.store.set_retraction("2", False)
    parts.store.set_retraction("1", True)
    status = parts.store.retraction_status(["1", "2", "3"])
    assert status["1"][0] is True and status["2"][0] is False and "3" not in status
    refs = [f"r{i}" for i in range(450)]
    parts.store.set_retraction("r449", True)
    assert parts.store.retraction_status(refs)["r449"][0] is True  # passa por varios blocos


@pytest.mark.sqlite_only  # "isolado" = outro arquivo SQLite; no PostgreSQL todos os armazens dividem o mesmo schema
def test_due_users_needs_the_accounts_table_and_orders_oldest_first(parts):
    accounts = AccountStore()
    for email in ("a@x.com", "b@x.com", "c@x.com"):
        accounts.create_user(email, PASSWORD)
    parts.store.touch("b@x.com", START - timedelta(hours=10))
    parts.store.touch("c@x.com", START - timedelta(hours=1))
    assert parts.store.due_users(START - timedelta(hours=6), 10) == ["a@x.com", "b@x.com"]  # nunca verificado primeiro
    assert parts.store.due_users(START - timedelta(hours=6), 1) == ["a@x.com"]
    assert parts.store.last_run("b@x.com") == START - timedelta(hours=10) and parts.store.last_run("z@x.com") is None
    isolated = NotificationStore(Database(database_url="", sqlite_path=str(parts.database.sqlite_path) + ".vazio"))
    isolated.initialize()
    assert isolated.due_users(START, 10) == []  # sem tabela de contas: nada a verificar, sem erro


# ------------------------------------------------------------------ regulatorio (puro)
def test_fingerprint_and_description_cover_conitec_rename_and_anvisa(bases):
    item = consulta.situacao("dapagliflozina", bases[0], bases[1], rename_data=bases[2])
    now = regulatory_fingerprint(item)
    assert now["conitec"] and now["anvisa_ativo"] is True and isinstance(now["rename"], list)
    assert describe_regulatory_change(now, now, item) == []
    older = {**now, "conitec": now["conitec"][1:], "rename": [], "anvisa_ativo": False}
    lines = describe_regulatory_change(older, now, item)
    assert any(line.startswith("Conitec: nova decisão") for line in lines) and "ANVISA: passou a ter registro ativo" in lines
    if now["rename"]:
        assert any(line.startswith("Rename: passou a constar") for line in lines)
    gone = describe_regulatory_change({**now, "rename": ["Básico"]}, {**now, "rename": []}, item)
    assert "Rename: deixou de constar" in gone
    changed = describe_regulatory_change({**now, "rename": ["Básico"]}, {**now, "rename": ["Estratégico"]}, item)
    assert "Rename: componente alterado para estratégico" in changed
    assert "ANVISA: não tem mais registro ativo" in describe_regulatory_change(now, {**now, "anvisa_ativo": False}, item)
    removed = describe_regulatory_change({**now, "conitec": now["conitec"] + ["2000|x|y|z"]}, now, item)
    assert any("não consta mais na base" in line for line in removed)
    many = describe_regulatory_change({**now, "conitec": []}, {**now, "conitec": now["conitec"] * 1}, item)
    assert len([line for line in many if line.startswith("Conitec: nova decisão")]) <= nt.CONITEC_SHOWN


# ------------------------------------------------------------------ vigia de retratacoes
def seed_retraction(parts):
    parts.library.save(EMAIL, make_work("1"))
    created = parts.library.create_list(EMAIL, "Minha lista")
    parts.library.add_to_list(EMAIL, created.id, make_work("1"))
    parts.library.add_to_list(EMAIL, created.id, make_work("2"))
    parts.reports.create(EMAIL, list_name="L", works=[make_work("3"), make_work("4")], title="Meu relatório")
    parts.remote.update({"1": make_work("1", retracted=True), "2": make_work("2"), "3": make_work("3", retracted=True), "4": make_work("4")})


def test_retracted_articles_in_library_lists_and_reports_are_flagged_once(parts):
    seed_retraction(parts)
    result = parts.service.run(EMAIL)
    assert result.ran and result.created == {"retratacao": 2}
    notes = {n.data["ref"]: n for n in parts.store.notifications(EMAIL)}
    assert set(notes) == {"1", "3"} and all(n.priority == 2 and n.kind == "retratacao" for n in notes.values())
    assert notes["1"].title == "Artigo retratado: Estudo 1" and notes["1"].link == "#/artigo?ref=1"
    assert "na sua biblioteca e na lista “Minha lista”" in notes["1"].body and "no relatório “Meu relatório”" in notes["3"].body
    assert "Confira o aviso de retratação" in notes["1"].body
    parts.clock.advance(hours=7)
    assert parts.service.run(EMAIL).created == {}  # nao repete


def test_excluded_report_studies_are_not_watched_and_unchanged_ones_do_not_alert(parts):
    seed_retraction(parts)
    report = parts.reports.summaries(EMAIL)[0]
    parts.reports.update(EMAIL, report.id, title="", question="", method_note="", items=[("3", False, "")])
    parts.service.run(EMAIL)
    assert {n.data["ref"] for n in parts.store.notifications(EMAIL)} == {"1"}  # o 3 foi excluido do relatorio


def test_known_retracted_at_save_time_needs_no_fetch(parts):
    parts.library.save(EMAIL, make_work("9", retracted=True))
    parts.service.run(EMAIL)
    assert [n.data["ref"] for n in parts.store.notifications(EMAIL)] == ["9"] and "9" not in parts.calls


def test_each_article_is_rechecked_at_most_once_a_week_and_within_the_budget(parts):
    seed_retraction(parts)
    parts.service.run(EMAIL)
    first = len(parts.calls)
    assert first == 4  # biblioteca, lista (1 e 2) e relatorio (3 e 4), sem repetir o 1
    parts.clock.advance(hours=7)
    parts.service.run(EMAIL)
    assert len(parts.calls) == first  # menos de uma semana
    parts.clock.advance(days=8)
    parts.service.run(EMAIL)
    assert len(parts.calls) == first + 4
    parts.library.save(EMAIL, make_work("5"))
    parts.library.save(EMAIL, make_work("6"))
    parts.remote.update({"5": make_work("5"), "6": make_work("6")})
    parts.clock.advance(hours=7)
    before = len(parts.calls)
    parts.service.run(EMAIL, refresh_budget=1)
    assert len(parts.calls) == before + 1  # o orcamento limita a conferencia


def test_source_failures_are_skipped_and_rate_limit_stops_the_loop(parts):
    parts.library.save(EMAIL, make_work("falha"))
    parts.library.save(EMAIL, make_work("1"))
    parts.remote["1"] = make_work("1", retracted=True)
    parts.service.run(EMAIL)
    assert [n.data["ref"] for n in parts.store.notifications(EMAIL)] == ["1"]  # a falha de uma fonte nao impede as outras
    parts.library.save("lim@x.com", make_work("limite"))
    parts.library.save("lim@x.com", make_work("2"))
    parts.clock.advance(hours=7)
    parts.service.run("lim@x.com")
    assert "2" not in parts.calls[parts.calls.index("limite"):]  # estourou o limite: para por aqui


def test_turning_off_a_kind_stops_those_notifications(parts):
    seed_retraction(parts)
    parts.store.set_prefs(EMAIL, {"retratacao": False})
    result = parts.service.run(EMAIL)
    assert result.ran and result.created == {} and parts.store.notifications(EMAIL) == []


# ------------------------------------------------------------------ vigia regulatorio
def report_with_substance(parts, term="dapagliflozina"):
    report = parts.reports.create(EMAIL, list_name="L", works=[make_work("7")], title="Relatório da substância")
    parts.reports.update(EMAIL, report.id, title="", question="", method_note="", items=[], substances=[term])
    return report


def test_first_run_only_remembers_the_regulatory_state_then_changes_alert(parts, bases):
    report = report_with_substance(parts)
    assert parts.service.run(EMAIL).created == {}  # linha de base, sem aviso
    saved = json.loads(parts.store.regulatory_fingerprint(EMAIL, "dapagliflozina"))
    assert saved["conitec"] and saved["anvisa_ativo"] is True
    parts.store.set_regulatory_fingerprint(EMAIL, "dapagliflozina", json.dumps({**saved, "conitec": saved["conitec"][1:], "anvisa_ativo": False}))
    parts.clock.advance(hours=7)
    result = parts.service.run(EMAIL)
    assert result.created == {"regulatorio": 1}
    [note] = parts.store.notifications(EMAIL)
    assert note.kind == "regulatorio" and note.priority == 2 and note.link == f"#/relatorio/{report.id}"
    assert note.title == "Mudança regulatória: Dapagliflozina" and "Conitec: nova decisão" in note.body and "ANVISA: passou a ter registro ativo" in note.body
    assert "não significa disponibilidade" in note.body
    parts.clock.advance(hours=7)
    assert parts.service.run(EMAIL).created == {}  # o estado novo foi guardado: sem repeticao


def test_regulatory_watch_skips_when_the_bases_cannot_be_read_or_nothing_is_confirmed(parts):
    parts.reports.create(EMAIL, list_name="L", works=[make_work("7")])
    assert parts.service.run(EMAIL).created == {}  # sem substancias confirmadas
    report_with_substance(parts)
    parts.holder["bases"] = None
    parts.clock.advance(hours=7)
    assert parts.service.run(EMAIL).created == {}
    assert parts.store.regulatory_fingerprint(EMAIL, "dapagliflozina") is None  # nem memorizou


def test_corrupt_stored_fingerprint_is_replaced_without_an_alert(parts):
    report_with_substance(parts)
    parts.store.set_regulatory_fingerprint(EMAIL, "dapagliflozina", "quebrado")
    assert parts.service.run(EMAIL).created == {}
    assert json.loads(parts.store.regulatory_fingerprint(EMAIL, "dapagliflozina"))["conitec"]


# ------------------------------------------------------------------ novidades dos relatorios
def report_from_list(parts):
    created = parts.library.create_list(EMAIL, "Hipertensão")
    for ref in ("1", "2"):
        parts.library.add_to_list(EMAIL, created.id, make_work(ref))
    report = parts.reports.create(EMAIL, list_name="Hipertensão", works=[make_work("1"), make_work("2")], title="Exercício e pressão", source_list_id=created.id)
    return created, report


def test_new_articles_in_the_source_list_notify_and_replace_the_previous_notice(parts):
    created, report = report_from_list(parts)
    assert parts.service.run(EMAIL).created == {}
    parts.library.add_to_list(EMAIL, created.id, make_work("3"))
    parts.clock.advance(hours=7)
    assert parts.service.run(EMAIL).created == {"relatorio-lista": 1}
    [note] = parts.store.notifications(EMAIL)
    assert note.kind == "relatorio-lista" and note.priority == 1 and note.link == f"#/relatorio/{report.id}"
    assert note.title == "“Exercício e pressão”: 1 artigo novo na lista de origem" and "Estudo 3" in note.body and "Hipertensão" in note.body
    parts.library.add_to_list(EMAIL, created.id, make_work("4"))
    parts.clock.advance(hours=7)
    parts.service.run(EMAIL)
    [latest] = parts.store.notifications(EMAIL)  # o aviso anterior (nao lido) foi substituido
    assert latest.title.endswith("2 artigos novos na lista de origem") and latest.id != note.id
    parts.clock.advance(hours=7)
    assert parts.service.run(EMAIL).created == {}  # mesmo conjunto: nao repete
    parts.reports.add_works(EMAIL, report.id, [make_work("3"), make_work("4")], origin="lista")
    parts.clock.advance(hours=7)
    assert parts.service.run(EMAIL).created == {}  # ja entraram no relatorio


def test_report_list_watch_ignores_deleted_lists_and_many_titles_are_abbreviated(parts):
    created, _ = report_from_list(parts)
    for ref in ("3", "4", "5", "6", "7"):
        parts.library.add_to_list(EMAIL, created.id, make_work(ref))
    parts.service.run(EMAIL)
    assert "e mais 2" in parts.store.notifications(EMAIL)[0].body
    parts.library.delete_list(EMAIL, created.id)
    parts.clock.advance(hours=7)
    assert parts.service.run(EMAIL).created == {}


# ------------------------------------------------------------------ orquestracao
def test_run_respects_the_interval_and_force_uses_the_short_one(parts):
    assert parts.service.run(EMAIL).ran
    parts.clock.advance(minutes=5)
    assert parts.service.run(EMAIL).reason == "intervalo" and parts.service.run(EMAIL, force=True).reason == "intervalo"
    parts.clock.advance(minutes=11)
    assert parts.service.run(EMAIL, force=True).ran
    assert parts.service.run(EMAIL).reason == "intervalo"  # o automatico continua esperando 6 horas


def test_run_all_refreshes_a_global_batch_then_runs_due_accounts(parts):
    accounts = AccountStore()
    for email in (EMAIL, "bia@exemplo.com"):
        accounts.create_user(email, PASSWORD)
    seed_retraction(parts)
    parts.library.save("bia@exemplo.com", make_work("1"))
    summary = parts.service.run_all()
    assert summary["due"] == 2 and summary["ran"] == 2 and summary["failed"] == 0 and summary["refreshed"] == 4
    assert summary["notified"] == 3  # ana: artigos 1 e 3; bia: artigo 1
    assert parts.service.run_all()["due"] == 0  # ambas acabaram de rodar


def test_run_all_survives_a_failing_account(parts, monkeypatch):
    AccountStore().create_user(EMAIL, PASSWORD)
    monkeypatch.setattr(parts.service, "run", MagicMock(side_effect=RuntimeError("falha isolada")))
    assert parts.service.run_all()["failed"] == 1


# ------------------------------------------------------------------ rotas
@pytest.fixture
def env(parts, tmp_path):
    database = parts.database
    alert_store, profiles = AlertStore(database), ProfileStore(database)
    alert_store.initialize()
    profiles.initialize()
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
    settings = Settings(session_secret="k" * 40, login_attempts_per_minute=100, alerts_cron_token="t" * 30)
    app = create_app(service, repository, settings, account_store_factory=AccountStore, search_fn=lambda *a, **k: [], discovery=discovery,
                     library=parts.library, alerts=alerts, reports=parts.reports, profiles=profiles, notifications=parts.service)

    def client(email=EMAIL, register=True):
        test_client = TestClient(app, base_url="http://testserver")
        if email and register:
            assert test_client.post("/api/auth/register", json={"email": email, "password": PASSWORD}).status_code == 200
        return test_client

    return type("Env", (), {"client": staticmethod(client), "alert_store": alert_store, "parts": parts})


def test_bell_box_merges_every_kind_with_unread_important_first(env):
    client = env.client()
    env.alert_store.add_alerts(EMAIL, [(make_work("9", title="Artigo novo de interesse"), "Medicina: Pediatria")])
    env.parts.store.add(EMAIL, NewNotification("relatorio-lista", "l1", "Lista", "corpo", "#/relatorio/x"))
    env.parts.store.add(EMAIL, NewNotification("retratacao", "r1", "Retratado", "corpo", "#/artigo?ref=1"))
    box = client.get("/api/alerts").json()
    assert box["unread"] == 3
    assert box["alerts"][0]["kind"] == "retratacao"  # o mais importante (prioridade alta, nao lido) no topo
    assert {item["kind"] for item in box["alerts"][1:]} == {"novo-artigo", "relatorio-lista"}
    first = box["alerts"][0]
    assert first["priority"] == 2 and first["href"] == "#/artigo?ref=1" and first["topic"] == "Artigo retratado" and first["work"] is None
    article = next(item for item in box["alerts"] if item["kind"] == "novo-artigo")
    assert article["title"] == "Artigo novo de interesse" and article["href"] == "#/artigo?ref=9" and article["work"]["ref"] == "9"


def test_read_and_dismiss_work_for_both_kinds(env):
    client = env.client()
    env.alert_store.add_alerts(EMAIL, [(make_work("9"), "t")])
    env.parts.store.add(EMAIL, NewNotification("retratacao", "r1", "Retratado", "", "#/"))
    ids = {item["kind"]: item["id"] for item in client.get("/api/alerts").json()["alerts"]}
    assert client.post("/api/alerts/read", json={"id": ids["retratacao"]}).json()["unread"] == 1
    assert client.post("/api/alerts/read", json={"id": ids["novo-artigo"]}).json()["unread"] == 0
    assert client.post("/api/alerts/read", json={"id": "nao-existe"}).status_code == 404
    env.parts.store.add(EMAIL, NewNotification("regulatorio", "g1", "Mudou", "", "#/"))
    assert client.post("/api/alerts/read", json={}).json()["unread"] == 0
    assert len(client.delete("/api/alerts", params={"id": ids["retratacao"]}).json()["alerts"]) == 2
    assert len(client.delete("/api/alerts", params={"id": ids["novo-artigo"]}).json()["alerts"]) == 1


def test_check_route_runs_the_watchers_and_reports_what_was_created(env):
    client = env.client()
    seed_retraction(env.parts)
    result = client.post("/api/alerts/check", json={"force": True}).json()
    assert result["ran"] and result["new"] == 2 and result["notified"] == {"retratacao": 2} and result["unread"] == 2
    assert {item["kind"] for item in result["alerts"]} == {"retratacao"}


def test_check_route_honors_the_interest_alert_toggle(env):
    client = env.client()
    client.put("/api/notifications/prefs", json={"kinds": {"novo-artigo": False}})
    client.put("/api/interests", json={"topics": [{"area": "medicina", "subtopics": ["pediatria"]}], "languages": [], "terms": []})
    result = client.post("/api/alerts/check", json={}).json()
    assert result["reason"] == "desativado"
    assert env.alert_store.preferences(EMAIL)[1] is None  # a verificacao de interesses nem rodou


def test_notification_prefs_routes(env):
    client = env.client()
    data = client.get("/api/notifications/prefs").json()
    assert data["channel"] == "sininho" and [k["key"] for k in data["kinds"]] == list(KINDS)
    assert all(k["enabled"] for k in data["kinds"]) and {k["priority"] for k in data["kinds"]} == {1, 2}
    saved = client.put("/api/notifications/prefs", json={"kinds": {"regulatorio": False, "inventado": False}}).json()
    assert {k["key"]: k["enabled"] for k in saved["kinds"]}["regulatorio"] is False
    assert "inventado" not in {k["key"] for k in saved["kinds"]}
    assert env.client(None).get("/api/notifications/prefs").status_code == 401
    assert env.client("bia@exemplo.com").get("/api/notifications/prefs").json()["kinds"][0]["enabled"] is True


def test_scheduled_route_also_runs_the_watchers(env):
    env.client()
    seed_retraction(env.parts)
    scheduler = env.client(None)
    summary = scheduler.post("/api/internal/alerts/run", headers={"Authorization": "Bearer " + "t" * 30}).json()
    assert summary["watch"]["ran"] == 1 and summary["watch"]["notified"] == 2 and summary["watch"]["refreshed"] == 4
    assert env.parts.store.unread(EMAIL) == 2


def test_account_export_and_delete_include_notifications(env):
    client = env.client()
    seed_retraction(env.parts)
    client.post("/api/alerts/check", json={"force": True})
    exported = client.get("/api/account/export").json()
    assert [n["kind"] for n in exported["notifications"]] == ["retratacao", "retratacao"] and exported["notificationPrefs"]["retratacao"] is True
    assert client.request("DELETE", "/api/account", json={"password": PASSWORD}).status_code == 200
    for table in ("notifications", "regulatory_state", "watch_state", "notification_prefs"):
        assert env.parts.database.query(f"SELECT COUNT(*) FROM {table} WHERE user_email = ?", (EMAIL,))[0][0] == 0, table  # noqa: S608

