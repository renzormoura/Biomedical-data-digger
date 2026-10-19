"""Feed de novidades academicas: leitura dos feeds, armazenamento, atualizacao, filtros e rotas. Nenhum teste usa a rede."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
import requests
from fastapi.testclient import TestClient

import feed as feedmod
import interests
from account_store import AccountStore
from alerts import AlertService, AlertStore
from catalog import CatalogError, Work
from config import Settings
from db import Database
from discovery import DiscoveryService
from feed import (
    FeedItem,
    FeedService,
    FeedStore,
    FetchResult,
    SourceState,
    clean_snippet,
    http_fetch,
    parse_date,
    parse_feed,
    safe_url,
)
from feed_sources import ARTICLE_TIERS, SOURCE_BY_ID, SOURCES, TIERS, Source
from library_store import LibraryStore
from ratelimit import SlidingWindowLimiter
from web import create_app
from workflow import AnalysisService, ArticleRepository

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
EMAIL = "ana@exemplo.com"


# ------------------------------------------------------------------ lista curada
def test_curated_sources_are_well_formed():
    assert len({s.id for s in SOURCES}) == len(SOURCES) == len(SOURCE_BY_ID)
    areas = {a["key"] for a in interests.catalogo()["areas"]}
    for source in SOURCES:
        assert source.tier in TIERS and source.language in ("pt", "en") and source.url.startswith("https://") and source.site.startswith("https://")
        assert set(source.areas) <= areas and 1 <= source.max_items <= 100
    assert {"revista", "preprint"} == set(ARTICLE_TIERS)
    covered = {a for s in SOURCES for a in s.areas}
    assert {"medicina", "engenharia", "computacao", "exatas", "ambiente", "psicologia", "educacao", "sociais", "biologia", "agrarias"} <= covered
    assert sum(1 for s in SOURCES if "agrarias" in s.areas) >= 3 and sum(1 for s in SOURCES if "sociais" in s.areas) >= 8
    assert {s.id for s in SOURCES if s.undated} == {"nber"}


# ------------------------------------------------------------------ datas, trechos e links
@pytest.mark.parametrize("raw,expected", [
    ("Sun, 18 Oct 2026 13:15:00 +0000", datetime(2026, 10, 18, 13, 15, tzinfo=timezone.utc)),
    ("Fri, 16 Oct 2026 13:50:00 -0300", datetime(2026, 10, 16, 16, 50, tzinfo=timezone.utc)),
    ("18 Oct 2026 18:00:00 -030", datetime(2026, 10, 18, 21, 0, tzinfo=timezone.utc)),  # variante da Folha
    ("2026-10-16T14:00:00Z", datetime(2026, 10, 16, 14, 0, tzinfo=timezone.utc)),
    ("2026-10-16T08:31:11-07:00", datetime(2026, 10, 16, 15, 31, 11, tzinfo=timezone.utc)),
    ("2026-10-16", datetime(2026, 10, 16, tzinfo=timezone.utc)),
])
def test_parse_date_understands_the_formats_feeds_use(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "ontem", "32 Foo 2026", None])
def test_parse_date_returns_none_when_unreadable(raw):
    assert parse_date(raw) is None


def test_clean_snippet_strips_markup_and_cuts_on_a_word():
    assert clean_snippet("<p>Um <b>estudo</b> &amp; seus <a href='x'>resultados</a>.</p>") == "Um estudo & seus resultados."
    assert clean_snippet("") == "" and clean_snippet("texto simples   com   espaços") == "texto simples com espaços"
    long = clean_snippet("palavra " * 100, 50)
    assert len(long) <= 51 and long.endswith("…") and not long.endswith(" …")
    assert "script" not in clean_snippet("<script>alert(1)</script>Texto")  # a marcacao sai; o texto do script nao vira link


@pytest.mark.parametrize("raw,expected", [
    ("https://exemplo.com/a", "https://exemplo.com/a"), ("  http://exemplo.com/a ", "http://exemplo.com/a"),
    ("javascript:alert(1)", ""), ("ftp://x.com/a", ""), ("//exemplo.com", ""), ("", ""), ("https://x.com/a b", ""), ("https://x.com/" + "a" * 2100, ""),
])
def test_safe_url_only_allows_plain_http_links(raw, expected):
    assert safe_url(raw) == expected


# ------------------------------------------------------------------ leitura de feeds
RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>X</title>
<item><title>  Estudo sobre   pediatria  </title><link>https://exemplo.com/1</link><description>&lt;p&gt;Crian\xc3\xa7as &lt;b&gt;vacinadas&lt;/b&gt;&lt;/p&gt;</description><pubDate>Sun, 18 Oct 2026 10:00:00 +0000</pubDate></item>
<item><title>Sem link</title><description>x</description></item>
<item><title></title><link>https://exemplo.com/2</link></item>
<item><title>Link perigoso</title><link>javascript:alert(1)</link></item>
<item><title>So guid</title><guid isPermaLink="true">https://exemplo.com/g</guid></item>
<item><title>Guid nao e link</title><guid isPermaLink="false">abc-123</guid></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>X</title>
<entry><title>Artigo Atom</title><link rel="self" href="https://exemplo.com/self"/><link rel="alternate" href="https://exemplo.com/atom1"/>
<summary>Resumo do artigo</summary><published>2026-10-16T14:00:00Z</published></entry>
<entry><title>Com conteudo</title><link href="https://exemplo.com/atom2"/><content type="html">&lt;p&gt;Texto &lt;i&gt;completo&lt;/i&gt;&lt;/p&gt;</content><updated>2026-10-15T09:00:00Z</updated></entry>
</feed>"""

RDF = b"""<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" xmlns="http://purl.org/rss/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/">
<item rdf:about="https://exemplo.com/rdf1"><title>Artigo RDF</title><link>https://exemplo.com/rdf1</link><description>Resumo RDF</description><dc:date>2026-10-16</dc:date></item>
</rdf:RDF>"""


def test_parse_rss_keeps_only_items_with_title_and_a_safe_link():
    entries = parse_feed(RSS)
    assert [e.title for e in entries] == ["Estudo sobre pediatria", "So guid"]
    first = entries[0]
    assert first.url == "https://exemplo.com/1" and first.snippet == "Crianças vacinadas" and first.published == datetime(2026, 10, 18, 10, tzinfo=timezone.utc)
    assert entries[1].url == "https://exemplo.com/g" and entries[1].published is None


def test_parse_atom_uses_the_alternate_link_and_summary_or_content():
    entries = parse_feed(ATOM)
    assert [(e.title, e.url, e.snippet) for e in entries] == [
        ("Artigo Atom", "https://exemplo.com/atom1", "Resumo do artigo"), ("Com conteudo", "https://exemplo.com/atom2", "Texto completo")]
    assert entries[0].published == datetime(2026, 10, 16, 14, tzinfo=timezone.utc) and entries[1].published == datetime(2026, 10, 15, 9, tzinfo=timezone.utc)


def test_parse_rdf_reads_dc_date():
    [entry] = parse_feed(RDF)
    assert entry.title == "Artigo RDF" and entry.url == "https://exemplo.com/rdf1" and entry.published == datetime(2026, 10, 16, tzinfo=timezone.utc)


def test_parse_feed_refuses_entity_expansion_and_garbage():
    with pytest.raises(CatalogError):
        parse_feed(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><rss><channel><item><title>&a;</title><link>https://x.com</link></item></channel></rss>')
    with pytest.raises(CatalogError):
        parse_feed(b"isto nao e xml")
    assert parse_feed(b"<html><body>pagina</body></html>") == []


# ------------------------------------------------------------------ busca na rede (requests simulado)
class FakeResponse:
    def __init__(self, status=200, content=b"<rss/>", headers=None):
        self.status_code, self._content, self.headers = status, content, headers or {}

    def iter_content(self, size):
        for start in range(0, len(self._content), size):
            yield self._content[start:start + size]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_http_fetch_sends_a_polite_conditional_request(monkeypatch):
    seen = {}

    def fake_get(url, headers, timeout, stream):
        seen.update(url=url, headers=headers, timeout=timeout)
        return FakeResponse(200, b"<rss/>", {"ETag": '"abc"', "Last-Modified": "Sat, 17 Oct 2026 10:00:00 GMT"})

    monkeypatch.setattr(requests, "get", fake_get)
    result = http_fetch("https://exemplo.com/feed", etag='"old"', last_modified="Fri, 16 Oct 2026 10:00:00 GMT")
    assert result == FetchResult(200, b"<rss/>", '"abc"', "Sat, 17 Oct 2026 10:00:00 GMT")
    assert "BiomedicalDataDigger" in seen["headers"]["User-Agent"] and seen["headers"]["If-None-Match"] == '"old"'
    assert seen["headers"]["If-Modified-Since"] == "Fri, 16 Oct 2026 10:00:00 GMT" and seen["timeout"] == feedmod.HTTP_TIMEOUT


def test_http_fetch_statuses_limits_and_errors(monkeypatch):
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(304))
    assert http_fetch("https://x.com/f").status == 304
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(403))
    assert http_fetch("https://x.com/f") == FetchResult(403)
    monkeypatch.setattr(feedmod, "MAX_FEED_BYTES", 100)
    monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse(200, b"x" * 500))
    with pytest.raises(CatalogError, match="maior"):
        http_fetch("https://x.com/f")
    monkeypatch.setattr(requests, "get", MagicMock(side_effect=requests.ConnectionError("x")))
    with pytest.raises(CatalogError, match="Sem resposta"):
        http_fetch("https://x.com/f")
    with pytest.raises(CatalogError):
        http_fetch("file:///etc/passwd")


# ------------------------------------------------------------------ armazenamento
@pytest.fixture
def store(tmp_path):
    result = FeedStore(Database(database_url="", sqlite_path=str(tmp_path / "f.sqlite3")))
    result.initialize()
    return result


def make_item(item_id, published, source="fiocruz", **overrides):
    base = {"source_id": source, "url": f"https://exemplo.com/{item_id}", "title": f"Item {item_id}", "snippet": "", "date_known": True,
            "topics": (), "areas": ()}
    base.update(overrides)
    return FeedItem(item_id, published_at=published.isoformat(timespec="seconds"), **base)


def test_store_upserts_orders_prunes_and_survives_corrupt_json(store):
    store.upsert([make_item("a", NOW - timedelta(days=1)), make_item("b", NOW), make_item("c", NOW - timedelta(days=60))], NOW.isoformat())
    store.upsert([make_item("b", NOW, title="Novo título")], NOW.isoformat())
    assert [i.id for i in store.recent()] == ["b", "a", "c"] and store.recent()[0].title == "Novo título"
    assert store.prune(NOW - timedelta(days=45)) == 1 and [i.id for i in store.recent()] == ["b", "a"]
    assert len(store.recent(limit=1)) == 1
    store._db.execute("UPDATE feed_items SET topics = 'quebrado', areas = 'quebrado' WHERE id = 'a'")  # noqa: SLF001
    broken = next(i for i in store.recent() if i.id == "a")
    assert broken.topics == () and broken.areas == ()


def test_store_state_roundtrip(store):
    assert store.state("fiocruz") is None and store.states() == {} and store.latest_fetch() == ""
    store.set_state(SourceState("fiocruz", "2026-10-18T10:00:00+00:00", "", "falhou", 0))
    store.set_state(SourceState("opas", "2026-10-18T11:00:00+00:00", "2026-10-18T11:00:00+00:00", "", 5, '"e"', "Sat"))
    assert store.state("fiocruz").error == "falhou" and store.state("opas").etag == '"e"' and store.state("opas").items == 5
    assert set(store.states()) == {"fiocruz", "opas"} and store.latest_fetch() == "2026-10-18T11:00:00+00:00"


# ------------------------------------------------------------------ atualizacao
def rss(*items):
    body = "".join(f"<item><title>{t}</title><link>{u}</link><description>{d}</description><pubDate>{p}</pubDate></item>" for t, u, d, p in items)
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>X</title>{body}</channel></rss>'.encode()


def stamp(delta=timedelta()):
    return (NOW - delta).strftime("%a, %d %b %Y %H:%M:%S +0000")


class Fetcher:
    def __init__(self, content=None, status=200, error=None):
        self.content, self.status, self.error, self.calls = content, status, error, []

    def __call__(self, url, etag="", last_modified=""):
        self.calls.append((url, etag, last_modified))
        if self.error:
            raise CatalogError(self.error)
        return FetchResult(self.status, self.content or b"", '"v1"', "Sat, 17 Oct 2026 10:00:00 GMT")


def service_with(store, fetcher):
    return FeedService(store, fetcher, clock=lambda: NOW)


PEDIATRIA = Source("teste", "Fonte de teste", "https://exemplo.com/feed", "https://exemplo.com", "en", "divulgacao", ("medicina",), max_items=3)


def test_refresh_source_stores_recent_items_with_topics_areas_and_a_short_snippet(store):
    content = rss(("Vacinas em pediatria reduzem internações", "https://exemplo.com/1", "<p>Crianças vacinadas tiveram menos casos.</p>", stamp()),
                  ("Novo método de fundição de aço", "https://exemplo.com/2", "Engenharia de materiais.", stamp(timedelta(days=2))),
                  ("Notícia velha", "https://exemplo.com/3", "x", stamp(timedelta(days=100))),
                  ("Notícia do futuro", "https://exemplo.com/4", "x", stamp(timedelta(days=-30))))
    fetcher = Fetcher(content)
    count = service_with(store, fetcher).refresh_source(PEDIATRIA)
    assert count == 2
    by_url = {i.url: i for i in store.recent()}
    first = by_url["https://exemplo.com/1"]
    assert first.snippet == "Crianças vacinadas tiveram menos casos." and first.date_known and "medicina/pediatria" in first.topics and first.areas[0] == "medicina"
    assert "engenharia" in by_url["https://exemplo.com/2"].areas  # area dos temas citados somada a da fonte
    assert "https://exemplo.com/3" not in by_url and "https://exemplo.com/4" not in by_url  # antigo demais e data futura
    state = store.state("teste")
    assert state.error == "" and state.items == 2 and state.etag == '"v1"' and state.last_ok == NOW.isoformat(timespec="seconds")


def test_refresh_source_keeps_only_the_newest_max_items_and_dedupes(store):
    content = rss(*[(f"Item {n}", f"https://exemplo.com/{n}", "", stamp(timedelta(hours=n))) for n in range(8)])
    service = service_with(store, Fetcher(content))
    assert service.refresh_source(PEDIATRIA) == 3
    service.refresh_source(PEDIATRIA)
    assert [i.title for i in store.recent()] == ["Item 0", "Item 1", "Item 2"]  # sem duplicar


def test_items_without_a_date_use_the_fetch_time_and_are_marked(store):
    content = b'<?xml version="1.0"?><rss><channel><item><title>Sem data</title><link>https://exemplo.com/s</link></item></channel></rss>'
    service_with(store, Fetcher(content)).refresh_source(PEDIATRIA)
    [item] = store.recent()
    assert item.date_known is False and item.published_at == NOW.isoformat(timespec="seconds")


def test_not_modified_keeps_the_previous_state_and_sends_the_validators(store):
    first = Fetcher(rss(("Item", "https://exemplo.com/1", "", stamp())))
    service_with(store, first).refresh_source(PEDIATRIA)
    second = Fetcher(status=304)
    assert service_with(store, second).refresh_source(PEDIATRIA) == 1
    assert second.calls[0][1:] == ('"v1"', "Sat, 17 Oct 2026 10:00:00 GMT") and store.state("teste").error == ""


@pytest.mark.parametrize("fetcher", [Fetcher(error="Sem resposta da fonte."), Fetcher(status=403), Fetcher(b"isto nao e xml"), Fetcher(status=304)])
def test_source_failures_are_recorded_and_never_raise_or_drop_old_items(store, fetcher):
    service_with(store, Fetcher(rss(("Antigo", "https://exemplo.com/1", "", stamp())))).refresh_source(PEDIATRIA)
    count = service_with(store, fetcher).refresh_source(PEDIATRIA)
    if fetcher.status == 304:  # 304 com estado anterior nao e falha
        assert store.state("teste").error == ""
    else:
        assert store.state("teste").error and count == 1
    assert [i.title for i in store.recent()] == ["Antigo"]


def test_a_failure_before_any_success_leaves_an_empty_state(store):
    service_with(store, Fetcher(error="Sem resposta da fonte.")).refresh_source(PEDIATRIA)
    state = store.state("teste")
    assert state.error == "Sem resposta da fonte." and state.last_ok == "" and state.items == 0


def test_due_sources_respect_the_interval_and_go_oldest_first(store):
    service = service_with(store, Fetcher(rss()))
    assert len(service.due_sources()) == len(SOURCES)
    store.set_state(SourceState("fiocruz", (NOW - timedelta(hours=1)).isoformat(), "", "", 0))
    store.set_state(SourceState("opas", (NOW - timedelta(hours=5)).isoformat(), "", "", 0))
    due = [s.id for s in service.due_sources()]
    assert "fiocruz" not in due and due.index("opas") == len(due) - 1 or "opas" in due
    assert "fiocruz" in [s.id for s in service.due_sources(force=True)]


def test_refresh_runs_a_budgeted_batch_prunes_and_reports(store):
    store.upsert([make_item("velho", NOW - timedelta(days=100))], NOW.isoformat())
    fetcher = Fetcher(rss(("Estudo novo", "https://exemplo.com/1", "", stamp())))  # tem palavra de pesquisa: passa tambem nos jornais
    summary = service_with(store, fetcher).refresh(budget=5)
    assert summary == {"due": len(SOURCES), "refreshed": 5, "failed": 0, "items": 5, "skipped": 0}
    assert len(fetcher.calls) == 5 and all(i.id != "velho" for i in store.recent())
    failing = service_with(store, Fetcher(error="fora do ar")).refresh(budget=2)
    assert failing["failed"] == 2 and failing["refreshed"] == 0


def test_refresh_does_not_run_twice_at_once_and_background_only_when_due(store):
    service = service_with(store, Fetcher(rss()))
    service._lock.acquire()  # noqa: SLF001
    assert service.refresh()["skipped"] == 1 and service.refresh_in_background() is False
    service._lock.release()  # noqa: SLF001
    for source in SOURCES:
        store.set_state(SourceState(source.id, NOW.isoformat(), NOW.isoformat(), "", 0))
    assert service.refresh_in_background() is False  # nada vencido


def test_background_refresh_starts_a_thread_when_sources_are_due(store, monkeypatch):
    started = []

    class FakeThread:
        def __init__(self, target, kwargs, daemon):
            started.append((target, kwargs, daemon))

        def start(self):
            started.append("iniciou")

    monkeypatch.setattr(feedmod.threading, "Thread", FakeThread)
    service = service_with(store, Fetcher(rss()))
    assert service.refresh_in_background() is True
    assert started[0][1] == {"budget": feedmod.ON_DEMAND_BUDGET} and started[0][2] is True and started[1] == "iniciou"


# ------------------------------------------------------------------ leitura filtrada
def seed(store):
    items = [
        make_item("1", NOW - timedelta(hours=1), "fiocruz", title="Vacinas em pediatria", topics=("medicina", "medicina/pediatria"), areas=("medicina",)),
        make_item("2", NOW - timedelta(hours=2), "mit-news", title="Novo chip de computação", topics=("computacao",), areas=("engenharia", "computacao")),
        make_item("3", NOW - timedelta(hours=3), "nature", title="Preprint sobre câncer", topics=("medicina", "medicina/oncologia"), areas=("medicina",)),
        make_item("4", NOW - timedelta(hours=4), "folha-saude", title="Dieta e metformina em idosos", topics=("medicina",), areas=("medicina", "nutricao")),
    ]
    store.upsert(items, NOW.isoformat())


def prefs_for(*subs, terms=()):
    return interests.validar([{"area": "medicina", "subtopics": list(subs)}] if subs else [], [], list(terms))


def test_page_everything_and_filters(store):
    seed(store)
    service = service_with(store, Fetcher())
    page = service.page(prefs=None, mode="tudo")
    assert [i["title"] for i in page.items] == ["Vacinas em pediatria", "Novo chip de computação", "Preprint sobre câncer", "Dieta e metformina em idosos"]
    assert page.total == 4 and not page.has_more and not page.personalized
    first = page.items[0]
    assert first["kind"] == "noticia" and first["source"]["tierLabel"] == "Instituição" and first["areas"] == ["Medicina"] and first["url"].startswith("https://")
    assert [i["kind"] for i in page.items] == ["noticia", "noticia", "artigo", "noticia"]  # nature e revista
    assert [i["title"] for i in service.page(prefs=None, mode="tudo", kind="artigos").items] == ["Preprint sobre câncer"]
    assert len(service.page(prefs=None, mode="tudo", kind="noticias").items) == 3
    assert [i["id"] for i in service.page(prefs=None, mode="tudo", area="computacao").items] == ["2"]
    assert [i["id"] for i in service.page(prefs=None, mode="tudo", language="pt").items] == ["1", "4"]
    assert service.page(prefs=None, mode="tudo", area="agrarias").items == []


def test_personalized_page_shows_only_what_cites_the_interests(store):
    seed(store)
    service = service_with(store, Fetcher())
    only_pediatria = service.page(prefs=prefs_for("pediatria"), mode="voce")
    assert only_pediatria.personalized and [i["id"] for i in only_pediatria.items] == ["1"] and only_pediatria.items[0]["matched"] == ["Medicina: Pediatria"]
    whole_area = service.page(prefs=interests.validar([{"area": "medicina", "subtopics": []}], [], []), mode="voce")
    assert [i["id"] for i in whole_area.items] == ["1", "3", "4"]
    with_term = service.page(prefs=prefs_for(terms=["metformina"]), mode="voce")
    assert [i["id"] for i in with_term.items] == ["4"] and with_term.items[0]["matched"] == ["“metformina”"]
    everything = service.page(prefs=prefs_for("pediatria"), mode="tudo")
    assert not everything.personalized and everything.total == 4
    no_prefs = service.page(prefs=interests.Preferences(), mode="voce")
    assert not no_prefs.personalized and no_prefs.total == 4  # sem interesses, mostra tudo


def test_page_paginates_and_merges_articles_from_the_alerts(store):
    sources = ["fiocruz", "opas", "oms", "bmj", "jama"]
    items = [make_item(str(n), NOW - timedelta(minutes=n), sources[n % 5], topics=("medicina",), areas=("medicina",)) for n in range(25)]
    store.upsert(items, NOW.isoformat())
    service = service_with(store, Fetcher())
    first = service.page(prefs=None, mode="tudo")
    second = service.page(prefs=None, mode="tudo", page=2)
    assert len(first.items) == feedmod.PAGE_SIZE and first.has_more and len(second.items) == 5 and not second.has_more and first.total == 25
    article = {"id": "x", "kind": "artigo", "title": "Artigo novo", "publishedAt": (NOW + timedelta(minutes=1)).isoformat(), "url": "#/artigo?ref=1", "source": {}}
    merged = service.page(prefs=prefs_for("pediatria"), mode="voce", article_items=[article])
    assert [i["id"] for i in merged.items] == ["x"]
    assert service.page(prefs=None, mode="tudo", article_items=[article]).items[0]["id"] == "x"
    assert all(i["id"] != "x" for i in service.page(prefs=None, mode="tudo", kind="noticias", article_items=[article]).items)
    assert all(i["id"] != "x" for i in service.page(prefs=None, mode="tudo", language="pt", article_items=[article]).items)


# ------------------------------------------------------------------ rotas
@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "app.sqlite3"))
    AccountStore().initialize()
    database = Database(database_url="", sqlite_path=str(tmp_path / "app.sqlite3"))
    library, alert_store, feed_store = LibraryStore(database), AlertStore(database), FeedStore(database)
    for item in (library, alert_store, feed_store):
        item.initialize()
    alerts = AlertService(alert_store, lambda query, user: ())
    feed_service = FeedService(feed_store, Fetcher(rss(("Vacinas em pediatria", "https://exemplo.com/p", "Crianças", stamp()), ("Chips", "https://exemplo.com/c", "computação", stamp()))))
    # os itens ja guardados valem como "atualizados": o teste nao dispara thread de rede
    for source in SOURCES:
        feed_store.set_state(SourceState(source.id, NOW.isoformat(), NOW.isoformat(), "", 0))
    monkeypatch.setattr(feedmod, "_now", lambda: NOW)
    feed_service._clock = lambda: NOW  # noqa: SLF001

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
                     library=library, alerts=alerts, feed=feed_service)

    def client(email=None):
        test_client = TestClient(app, base_url="http://testserver")
        if email:
            assert test_client.post("/api/auth/register", json={"email": email, "password": "senha-forte-123"}).status_code == 200
        return test_client

    return type("Env", (), {"client": staticmethod(client), "store": feed_store, "alert_store": alert_store, "service": feed_service})


def test_feed_route_is_public_and_returns_the_cards(env):
    seed(env.store)
    data = env.client().get("/api/feed", params={"mode": "tudo"}).json()
    assert data["total"] == 4 and data["personalized"] is False and data["hasInterests"] is False and data["refreshing"] is False
    card = data["items"][0]
    assert set(card) >= {"id", "kind", "title", "snippet", "url", "publishedAt", "areas", "matched", "source"} and card["source"]["tierLabel"] == "Instituição"
    assert env.client().get("/api/feed", params={"area": "computacao", "mode": "tudo"}).json()["total"] == 1


def test_feed_route_personalizes_for_a_logged_in_account_and_includes_new_articles(env):
    seed(env.store)
    client = env.client(EMAIL)
    client.put("/api/interests", json={"topics": [{"area": "medicina", "subtopics": ["pediatria"]}], "languages": [], "terms": []})
    env.alert_store.add_alerts(EMAIL, [(Work(ref="9", title="Artigo novo de pediatria", journal="Revista X", year=2026), "Medicina: Pediatria")])
    data = client.get("/api/feed").json()
    assert data["personalized"] and data["hasInterests"]
    assert [i["kind"] for i in data["items"]].count("artigo") == 1
    article = next(i for i in data["items"] if i["kind"] == "artigo")
    assert article["internal"] is True and article["url"] == "#/artigo?ref=9" and article["matched"] == ["Medicina: Pediatria"]
    assert {i["title"] for i in data["items"] if i["kind"] == "noticia"} == {"Vacinas em pediatria"}
    everything = client.get("/api/feed", params={"mode": "tudo"}).json()
    assert everything["total"] == 4 and not everything["personalized"]  # em "tudo" os artigos dos alertas ficam de fora


def test_feed_route_validates_parameters(env):
    client = env.client()
    for params in ({"mode": "x"}, {"kind": "x"}, {"page": 0}, {"page": 51}, {"area": "a" * 40}):
        assert client.get("/api/feed", params=params).status_code == 422


def test_feed_route_reports_when_it_is_still_loading(env, monkeypatch):
    monkeypatch.setattr(env.service, "refresh_in_background", lambda: True)
    assert env.client().get("/api/feed", params={"mode": "tudo"}).json()["refreshing"] is True


def test_feed_sources_route_lists_every_source_with_type_and_status(env):
    env.store.set_state(SourceState("bmj", NOW.isoformat(), "", "HTTP 403", 0))
    data = env.client().get("/api/feed/sources").json()
    assert len(data["sources"]) == len(SOURCES) and {t["key"] for t in data["tiers"]} == set(TIERS)
    bmj = next(s for s in data["sources"] if s["id"] == "bmj")
    assert bmj["failing"] is True and bmj["tierLabel"] == "Revista" and bmj["areas"] == ["Medicina"] and bmj["site"].startswith("https://")
    assert next(s for s in data["sources"] if s["id"] == "jornal-usp")["areas"] == ["Qualquer área"]


def test_scheduled_route_also_refreshes_the_feed(env):
    for source in SOURCES:  # tudo vencido
        env.store.set_state(SourceState(source.id, (NOW - timedelta(days=1)).isoformat(), "", "", 0))
    summary = env.client().post("/api/internal/alerts/run", headers={"Authorization": "Bearer " + "t" * 30}).json()
    assert summary["feed"]["due"] == len(SOURCES) and summary["feed"]["refreshed"] == len(SOURCES) and summary["feed"]["failed"] == 0
    assert env.client().get("/api/feed", params={"mode": "tudo"}).json()["total"] >= 2


# ------------------------------------------------------------------ qualidade do feed
JORNAL = Source("jornal-teste", "Jornal de teste", "https://exemplo.com/j", "https://exemplo.com", "pt", "jornal", ("medicina",))


def test_newspaper_items_need_a_research_cue_other_tiers_do_not(store):
    content = rss(("Pesquisadores descobrem novo tratamento", "https://exemplo.com/1", "Estudo com 200 pacientes.", stamp()),
                  ("Meu noivo não me toca; devo me casar mesmo assim?", "https://exemplo.com/2", "Conselhos de relacionamento.", stamp()),
                  ("Receita de bolo fofinho", "https://exemplo.com/3", "Ingredientes simples.", stamp()))
    service_with(store, Fetcher(content)).refresh_source(JORNAL)
    assert [i.title for i in store.recent()] == ["Pesquisadores descobrem novo tratamento"]
    service_with(store, Fetcher(content)).refresh_source(Source("revista-teste", "Revista", "https://exemplo.com/r", "https://exemplo.com", "pt", "revista"))
    assert len([i for i in store.recent() if i.source_id == "revista-teste"]) == 3  # fora dos jornais, nada e filtrado por palavra


def test_one_source_cannot_flood_the_feed(store):
    items = [make_item(f"f{n}", NOW - timedelta(minutes=n), "fiocruz", areas=("medicina",)) for n in range(30)]
    items += [make_item("o1", NOW - timedelta(hours=5), "opas", areas=("medicina",))]
    store.upsert(items, NOW.isoformat())
    page = service_with(store, Fetcher()).page(prefs=None, mode="tudo")
    assert page.total == feedmod.PER_SOURCE_VIEW + 1 and any(i["source"]["id"] == "opas" for i in page.items)
