"""Interesses por area/idioma, verificacao de artigos novos e caixa de avisos (sininho)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

import interests
from account_store import AccountStore
from alerts import (
    AUTO_INTERVAL,
    MANUAL_INTERVAL,
    MAX_ALERTS,
    MAX_NEW_PER_CHECK,
    PER_TOPIC_NEW,
    AlertService,
    AlertStore,
    eligible,
    work_key,
)
from catalog import Work
from config import Settings
from db import Database
from discovery import DiscoveryService
from domain import DiggerError, NotFoundError
from library_store import LibraryStore
from ratelimit import SlidingWindowLimiter
from web import create_app
from workflow import AnalysisService, ArticleRepository

EMAIL = "ana@exemplo.com"
START = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def make_work(ref, title=None, doi="", year=2026, **extra):
    return Work(ref=ref, title=title or f"Artigo {ref}: pediatrics, oncology and metformina idosos", doi=doi, year=year, **extra)


# ------------------------------------------------------------------ interesses
def test_catalogo_lists_areas_with_subtopics_and_languages():
    data = interests.catalogo()
    keys = {a["key"] for a in data["areas"]}
    assert {"medicina", "computacao", "sociais"} <= keys
    medicina = next(a for a in data["areas"] if a["key"] == "medicina")
    assert {"pediatria", "oncologia"} <= {s["key"] for s in medicina["subtopics"]}
    assert {"pt", "en", "es"} <= {lang["code"] for lang in data["languages"]}
    assert data["limits"]["topics"] == interests.MAX_TOPICS


def test_validar_accepts_valid_choices_and_deduplicates():
    prefs = interests.validar(
        [{"area": "medicina", "subtopics": ["pediatria", "oncologia", "pediatria"]}, {"area": "medicina", "subtopics": ["cardiologia"]}, {"area": "educacao", "subtopics": []}],
        ["PT", "pt", "en"], ["  diabetes  tipo 2 ", "Diabetes tipo 2", ""],
    )
    assert prefs.topics == (("medicina", ("pediatria", "oncologia", "cardiologia")), ("educacao", ()))
    assert prefs.languages == ("pt", "en") and prefs.terms == ("diabetes tipo 2",)
    labels = [t.label for t in prefs.selected()]
    assert labels == ["Medicina: Pediatria", "Medicina: Oncologia", "Medicina: Cardiologia", "Educação"]
    assert prefs.to_dict()["topics"][0] == {"area": "medicina", "subtopics": ["pediatria", "oncologia", "cardiologia"]}


@pytest.mark.parametrize("topics,languages,terms", [
    ([{"area": "magia"}], [], []),
    ([{"area": "medicina", "subtopics": ["alquimia"]}], [], []),
    ([], ["xx"], []),
    ([], ["pt", "en", "es", "fr", "de"], []),
    ([], [], [f"termo {i}" for i in range(interests.MAX_TERMS + 1)]),
])
def test_validar_rejects_unknown_or_excess(topics, languages, terms):
    with pytest.raises(DiggerError):
        interests.validar(topics, languages, terms)


def test_validar_limits_total_topics():
    many = [{"area": "medicina", "subtopics": [s["key"] for s in interests.catalogo()["areas"][0]["subtopics"]]}, {"area": "computacao", "subtopics": ["llm", "aprendizado-maquina", "saude-digital"]}]
    with pytest.raises(DiggerError, match="no máximo"):
        interests.validar(many, [], [])


def test_topic_query_uses_portuguese_terms_only_for_portuguese():
    topic = interests.validar([{"area": "medicina", "subtopics": ["pediatria"]}], [], []).selected()[0]
    assert topic.query("en") == "pediatrics" and topic.query("pt") == "pediatria" and topic.query("") == "pediatrics"
    assert topic.key == "medicina/pediatria"
    assert topic.alternatives("en")[0] == "pediatrics" and "pediatria" not in topic.alternatives("en")
    assert topic.alternatives("pt")[0] == "pediatria" and "pediatrics" in topic.alternatives("pt")
    assert {"pediatrics", "pediatria"} <= set(topic.alternatives("es")) and {"pediatrics", "pediatria"} <= set(topic.alternatives(""))


@pytest.mark.parametrize("text,alternatives,expected", [
    ("Large language models in radiology", ("large language model",), True),
    ("Language models of the large intestine", ("large language model",), True),  # limitacao: confere palavras, nao a frase
    ("Ventrículo direito persistente", ("direito penal", "legislação"), False),
    ("Aspectos do direito penal brasileiro", ("direito penal",), True),
    ("Pediatric oncology outcomes", ("pediatrics", "pediatric"), True),
    ("Pediatrics today", ("pediatric",), True),  # plural simples
    ("Pediatricians say", ("pediatric",), False),  # palavra inteira: "pediatricians" e outra palavra
    ("PEDIATRÍA y niños", ("pediatria",), True),  # sem acento e sem diferenca de caixa
    ("", ("cancer",), False),
    ("qualquer coisa", (), False),
    ("qualquer coisa", ("",), False),
])
def test_mentions_requires_whole_words_of_some_alternative(text, alternatives, expected):
    assert interests.mentions(text, alternatives) is expected


def test_carregar_drops_what_no_longer_exists_and_survives_garbage():
    prefs = interests.carregar({"topics": [{"area": "medicina", "subtopics": ["pediatria", "extinto"]}, {"area": "extinta"}, "lixo"], "languages": ["pt", "zz"], "terms": ["ok"]})
    assert prefs.topics == (("medicina", ("pediatria",)),) and prefs.languages == ("pt",) and prefs.terms == ("ok",)
    assert interests.carregar({"topics": "x", "languages": 3, "terms": None}).empty
    assert interests.carregar({"terms": [f"t{i}" for i in range(9)]}).terms == ()  # excesso invalida tudo, sem excecao


# ------------------------------------------------------------------ verificacao
class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, delta):
        self.now += delta


class Searcher:
    def __init__(self):
        self.results = {}
        self.calls = []
        self.error = None

    def __call__(self, query, user):
        self.calls.append((query, user))
        if self.error:
            raise self.error
        return tuple(self.results.get(query.q, ()))


@pytest.fixture
def parts(tmp_path):
    store = AlertStore(Database(database_url="", sqlite_path=str(tmp_path / "a.sqlite3")))
    store.initialize()
    searcher, clock = Searcher(), Clock()
    return store, searcher, clock, AlertService(store, searcher, clock)


def choose(store, topics=None, languages=(), terms=()):
    topics = topics or [{"area": "medicina", "subtopics": ["pediatria"]}]
    store.set_preferences(EMAIL, interests.validar(topics, list(languages), list(terms)))


def test_check_without_interests_does_nothing(parts):
    _, searcher, _, service = parts
    result = service.check(EMAIL)
    assert not result.ran and result.reason == "sem-interesses" and searcher.calls == []


def test_first_check_only_records_a_baseline_then_new_articles_alert(parts):
    store, searcher, clock, service = parts
    choose(store)
    searcher.results["pediatrics"] = [make_work("A"), make_work("B")]
    first = service.check(EMAIL)
    assert first.ran and first.new == 0 and first.baseline and store.unread(EMAIL) == 0
    clock.advance(AUTO_INTERVAL + timedelta(minutes=1))
    searcher.results["pediatrics"] = [make_work("C", doi="10.1/c"), make_work("A"), make_work("B")]
    second = service.check(EMAIL)
    assert second.ran and second.new == 1 and not second.baseline
    [alert] = store.alerts(EMAIL)
    assert alert.work.ref == "C" and alert.topic == "Medicina: Pediatria" and not alert.read and store.unread(EMAIL) == 1
    clock.advance(AUTO_INTERVAL + timedelta(minutes=1))
    assert service.check(EMAIL).new == 0  # o mesmo artigo nao avisa duas vezes


def test_interval_is_enforced_and_force_uses_the_shorter_one(parts):
    store, searcher, clock, service = parts
    choose(store)
    searcher.results["pediatrics"] = [make_work("A")]
    assert service.check(EMAIL).ran
    clock.advance(timedelta(minutes=5))
    assert service.check(EMAIL).reason == "intervalo" and service.check(EMAIL, force=True).reason == "intervalo"
    clock.advance(MANUAL_INTERVAL)
    assert service.check(EMAIL, force=True).ran
    assert service.check(EMAIL).reason == "intervalo"  # o automatico continua esperando as 6 horas


def test_saving_preferences_allows_an_immediate_check_and_only_baselines_new_topics(parts):
    store, searcher, clock, service = parts
    choose(store)
    searcher.results["pediatrics"] = [make_work("A")]
    service.check(EMAIL)
    choose(store, [{"area": "medicina", "subtopics": ["pediatria", "oncologia"]}])
    searcher.results["pediatrics"] = [make_work("A"), make_work("N1")]
    searcher.results["oncology cancer"] = [make_work("O1")]
    result = service.check(EMAIL)  # sem esperar o intervalo
    assert result.ran and result.new == 1
    assert [a.work.ref for a in store.alerts(EMAIL)] == ["N1"]  # O1 so entrou na linha de base do tema novo


def test_languages_produce_one_search_each_with_portuguese_terms_for_pt(parts):
    store, searcher, _, service = parts
    choose(store, languages=["pt", "en"])
    service.check(EMAIL)
    queries = {(q.q, q.language) for q, _ in searcher.calls}
    assert queries == {("pediatria", "pt"), ("pediatrics", "en")}
    assert all(q.sort == "recent" and q.year_from == START.year - 1 for q, _ in searcher.calls)
    assert {u for _, u in searcher.calls} == {EMAIL}


def test_keywords_become_their_own_searches(parts):
    store, searcher, clock, service = parts
    choose(store, topics=[], terms=["metformina idosos"])
    searcher.results["metformina idosos"] = [make_work("A")]
    service.check(EMAIL)
    clock.advance(AUTO_INTERVAL + timedelta(minutes=1))
    searcher.results["metformina idosos"] = [make_work("A"), make_work("Z", title="Novo estudo sobre metformina idosos")]
    assert service.check(EMAIL).new == 1
    assert store.alerts(EMAIL)[0].topic == "“metformina idosos”"


def test_same_article_from_two_sources_alerts_once_and_retracted_are_skipped(parts):
    store, searcher, clock, service = parts
    choose(store, [{"area": "medicina", "subtopics": ["pediatria", "oncologia"]}])
    service.check(EMAIL)
    clock.advance(AUTO_INTERVAL + timedelta(minutes=1))
    searcher.results["pediatrics"] = [make_work("PM1", doi="10.1/X"), make_work("R", retracted=True), make_work("S", title="  ")]
    searcher.results["oncology cancer"] = [make_work("W1", doi="10.1/x")]
    assert service.check(EMAIL).new == 1
    assert work_key(make_work("a", doi=" 10.1/X ")) == "10.1/x"


def test_results_that_do_not_talk_about_the_topic_are_ignored(parts):
    store, searcher, clock, service = parts
    choose(store)
    service.check(EMAIL)
    clock.advance(AUTO_INTERVAL + timedelta(minutes=1))
    searcher.results["pediatrics"] = [
        make_work("ruido", title="Persistent right ventricular dysfunction predicts mortality"),
        make_work("certo", title="Vaccination schedules in pediatrics"),
        make_work("por-palavra-chave", title="Outcomes study", keywords=("pediatric",)),
        make_work("de-passagem", title="Statin use after infarction", abstract="Patients were mostly adults; a few children were included."),
        make_work("por-resumo", title="Asthma outcomes", abstract="We followed children seen in pediatrics clinics for two years."),
    ]
    assert service.check(EMAIL).new == 3
    assert {a.work.ref for a in store.alerts(EMAIL)} == {"certo", "por-palavra-chave", "por-resumo"}


def test_source_failures_do_not_consume_the_interval_and_are_reported(parts):
    store, searcher, clock, service = parts
    choose(store)
    searcher.error = DiggerError("Fonte fora do ar.")
    result = service.check(EMAIL)
    assert not result.ran and result.reason == "fontes" and result.notes == ("Fonte fora do ar.",)
    searcher.error = None
    searcher.results["pediatrics"] = [make_work("A")]
    assert service.check(EMAIL).ran  # nao precisou esperar


def test_each_topic_is_capped_and_the_overflow_does_not_queue_up(parts):
    store, searcher, clock, service = parts
    choose(store)
    service.check(EMAIL)
    clock.advance(AUTO_INTERVAL + timedelta(minutes=1))
    searcher.results["pediatrics"] = [make_work(str(i), published=f"2026-10-{10 + i:02d}") for i in range(PER_TOPIC_NEW + 4)]
    assert service.check(EMAIL).new == PER_TOPIC_NEW
    assert [a.work.published for a in store.alerts(EMAIL)][0] == "2026-10-18"  # os mais recentes primeiro
    clock.advance(AUTO_INTERVAL + timedelta(minutes=1))
    assert service.check(EMAIL).new == 0  # os excedentes foram descartados, nao ficaram na fila


def test_total_new_per_check_and_box_size_are_capped(parts):
    store, searcher, clock, service = parts
    topics = [{"area": "medicina", "subtopics": [s["key"] for s in interests.catalogo()["areas"][0]["subtopics"][:10]]}]
    choose(store, topics)
    service.check(EMAIL)
    clock.advance(AUTO_INTERVAL + timedelta(minutes=1))
    for topic in interests.validar(topics, [], []).selected():
        searcher.results[topic.query("en")] = [make_work(f"{topic.sub}-{i}") for i in range(PER_TOPIC_NEW)]
    assert service.check(EMAIL).new == MAX_NEW_PER_CHECK
    store.add_alerts(EMAIL, [(make_work(f"x{i}"), "t") for i in range(MAX_ALERTS)])
    assert len(store.alerts(EMAIL, limit=1000)) == MAX_ALERTS


def test_eligibility_uses_publication_date_and_ignores_absurd_future_years():
    today = START
    assert eligible(make_work("a", published="2026-10-10"), today)
    assert not eligible(make_work("b", published="2026-05-01"), today)  # mais de 60 dias
    assert eligible(make_work("c", published="2027-06-24", year=2027), today)  # data futura: sem data confiavel
    assert eligible(make_work("d", published="", year=2026), today)
    assert not eligible(make_work("e", published="2099-06-10", year=2099), today)
    assert eligible(make_work("f", published="2026-13-99"), today)  # data invalida vira "sem data"


def test_old_articles_do_not_alert_and_are_not_reconsidered(parts):
    store, searcher, clock, service = parts
    choose(store)
    service.check(EMAIL)
    clock.advance(AUTO_INTERVAL + timedelta(minutes=1))
    searcher.results["pediatrics"] = [make_work("velho", published="2026-01-05"), make_work("novo", published="2026-10-17")]
    assert service.check(EMAIL).new == 1 and store.alerts(EMAIL)[0].work.ref == "novo"
    assert store.seen(EMAIL, ["velho"]) == {"velho"}


def test_check_all_runs_only_due_accounts_oldest_first_and_survives_failures(parts):
    store, searcher, clock, service = parts
    store.set_preferences("a@x.com", interests.validar([{"area": "medicina", "subtopics": ["pediatria"]}], [], []))
    store.set_preferences("b@x.com", interests.validar([{"area": "medicina", "subtopics": ["pediatria"]}], [], []))
    store.set_preferences("sem@x.com", interests.validar([], [], []))
    summary = service.check_all()
    assert summary == {"due": 3, "ran": 2, "new": 0, "failed": 0}  # a conta sem interesses entra como vencida, mas nao roda
    assert service.check_all()["due"] == 1  # as duas que rodaram esperam o intervalo; a sem interesses segue sem data
    clock.advance(AUTO_INTERVAL + timedelta(minutes=1))
    original = service.check

    def explode(user, **kwargs):
        if user == "a@x.com":
            raise RuntimeError("falha isolada")
        return original(user, **kwargs)

    service.check = explode
    assert service.check_all() == {"due": 3, "ran": 1, "new": 0, "failed": 1}


def test_mark_read_dismiss_and_isolation_between_users(parts):
    store, _, _, _ = parts
    store.add_alerts(EMAIL, [(make_work("A"), "t"), (make_work("B"), "t")])
    store.add_alerts("outra@exemplo.com", [(make_work("A"), "t")])
    first = store.alerts(EMAIL)[0]
    store.mark_read(EMAIL, first.id)
    assert store.unread(EMAIL) == 1 and store.unread("outra@exemplo.com") == 1
    with pytest.raises(NotFoundError):
        store.mark_read(EMAIL, "inexistente")
    with pytest.raises(NotFoundError):
        store.mark_read("outra@exemplo.com", first.id)  # aviso de outra conta
    store.mark_read(EMAIL)
    assert store.unread(EMAIL) == 0
    store.dismiss("outra@exemplo.com", first.id)  # nao apaga o de outra conta
    assert len(store.alerts(EMAIL)) == 2
    store.dismiss(EMAIL, first.id)
    assert len(store.alerts(EMAIL)) == 1


def test_corrupt_stored_data_degrades_gracefully(parts):
    store, _, _, _ = parts
    db = store._db  # noqa: SLF001
    db.execute("INSERT INTO interest_prefs (user_email, data, updated_at, last_checked) VALUES (?, 'nao-json', 'x', 'data-ruim')", (EMAIL,))
    prefs, checked = store.preferences(EMAIL)
    assert prefs.empty and checked is None
    db.execute("INSERT INTO alerts (id, user_email, work_key, ref, data, topic, created_at) VALUES ('1', ?, 'k', 'r', 'quebrado', 't', 'x')", (EMAIL,))
    assert store.alerts(EMAIL)[0].work.title == "Título não informado"


# ------------------------------------------------------------------ rotas
class Catalog:
    id, name = "fake", "Fake"

    def __init__(self):
        self.works = {}

    def study_types(self):
        return ()

    def search(self, query):
        from catalog import SearchResult

        found = tuple(self.works.get(query.q, ()))
        return SearchResult(works=found, total=len(found), page=1, per_page=10, source="Fake")

    def get(self, ref):
        return None


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "app.sqlite3"))
    AccountStore().initialize()
    database = Database(database_url="", sqlite_path=str(tmp_path / "app.sqlite3"))
    library = LibraryStore(database)
    library.initialize()
    store = AlertStore(database)
    store.initialize()
    catalog = Catalog()
    discovery = DiscoveryService([catalog], SlidingWindowLimiter(100, 60), fallback=None)
    clock = Clock()
    alerts = AlertService(store, lambda q, user: catalog.search(q).works, clock)
    repository = ArticleRepository(lambda raw: ("T", "Resumo suficiente para o teste.", "s"))
    service = AnalysisService(repository, MagicMock(), SlidingWindowLimiter(50, 60))

    def client(email=EMAIL, cron_token=""):
        configured = Settings(session_secret="k" * 40, login_attempts_per_minute=100, alerts_cron_token=cron_token)
        app = create_app(service, repository, configured, account_store_factory=lambda: AccountStore(), search_fn=lambda *a, **k: [], discovery=discovery, library=library, alerts=alerts)
        test_client = TestClient(app, base_url="http://testserver")
        if email:
            assert test_client.post("/api/auth/register", json={"email": email, "password": "senha-forte-123"}).status_code == 200
        return test_client

    return type("Env", (), {"client": staticmethod(client), "catalog": catalog, "clock": clock, "store": store})


def test_interest_routes_require_login_except_the_options(env):
    anonimo = env.client(None)
    assert anonimo.get("/api/interests/options").json()["areas"]
    for method, url in [("get", "/api/interests"), ("get", "/api/alerts"), ("delete", "/api/alerts?id=x")]:
        assert getattr(anonimo, method)(url).status_code == 401
    assert anonimo.put("/api/interests", json={"topics": []}).status_code == 401
    assert anonimo.post("/api/alerts/check", json={}).status_code == 401
    assert anonimo.post("/api/alerts/read", json={}).status_code == 401


def test_save_interests_check_and_read_through_the_api(env):
    client = env.client()
    assert client.get("/api/interests").json() == {"topics": [], "languages": [], "terms": [], "lastChecked": None}
    body = {"topics": [{"area": "medicina", "subtopics": ["pediatria"]}], "languages": ["en"], "terms": []}
    assert client.put("/api/interests", json=body).json()["languages"] == ["en"]
    env.catalog.works["pediatrics"] = [make_work("A")]
    first = client.post("/api/alerts/check", json={}).json()
    assert first["ran"] and first["baseline"] and first["unread"] == 0
    assert client.get("/api/interests").json()["lastChecked"]
    env.clock.advance(AUTO_INTERVAL + timedelta(minutes=1))
    env.catalog.works["pediatrics"] = [make_work("A"), make_work("B", title="New pediatrics study")]
    second = client.post("/api/alerts/check", json={"force": False}).json()
    assert second["new"] == 1 and second["unread"] == 1
    alert = second["alerts"][0]
    assert alert["work"]["title"] == "New pediatrics study" and alert["topic"] == "Medicina: Pediatria" and not alert["read"]
    assert client.post("/api/alerts/check", json={}).json()["reason"] == "intervalo"
    assert client.post("/api/alerts/read", json={"id": alert["id"]}).json()["unread"] == 0
    assert client.post("/api/alerts/read", json={"id": "nao-existe"}).status_code == 404
    assert client.delete("/api/alerts", params={"id": alert["id"]}).json()["alerts"] == []


def test_invalid_interests_are_rejected_and_accounts_are_isolated(env):
    client = env.client()
    assert client.put("/api/interests", json={"topics": [{"area": "magia"}]}).status_code == 400
    assert client.put("/api/interests", json={"languages": ["pt", "en", "es", "fr", "de"]}).status_code == 400
    assert client.put("/api/interests", json={"topics": [{"area": "medicina"}] * 41}).status_code == 422
    client.put("/api/interests", json={"topics": [{"area": "educacao"}]})
    outra = env.client("bia@exemplo.com")
    assert outra.get("/api/interests").json()["topics"] == []
    assert outra.get("/api/alerts").json() == {"unread": 0, "alerts": []}


def test_scheduled_run_is_disabled_without_token_and_protected_with_one(env, tmp_path):
    assert env.client(None).post("/api/internal/alerts/run").status_code == 404
    guarded = env.client(None, cron_token="t" * 30)
    assert guarded.post("/api/internal/alerts/run").status_code == 401
    assert guarded.post("/api/internal/alerts/run", headers={"Authorization": "Bearer errado"}).status_code == 401
    ok = guarded.post("/api/internal/alerts/run", headers={"Authorization": "Bearer " + "t" * 30})
    assert ok.status_code == 200 and ok.json() == {"due": 0, "ran": 0, "new": 0, "failed": 0}


def test_check_reports_reason_when_there_is_nothing_to_watch(env):
    client = env.client()
    assert client.post("/api/alerts/check", json={}).json()["reason"] == "sem-interesses"
