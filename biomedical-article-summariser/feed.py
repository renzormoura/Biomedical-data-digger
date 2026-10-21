"""Feed de novidades academicas: le os feeds publicos da lista curada, guarda titulo, trecho curto e link, e mostra o que combina
com os interesses da pessoa. Quem clica vai para o site da fonte; nada e copiado alem do titulo e de ate 300 caracteres de resumo.

Por seguranca e educacao com as fontes: XML sem entidades (via `xmlutil`), limite de tamanho por feed, so links http(s), requisicao
condicional (ETag e Last-Modified), intervalo minimo entre buscas de uma mesma fonte e identificacao do robo. Falha de uma fonte nunca
derruba as demais, e itens antigos sao apagados.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from xml.etree.ElementTree import Element

import requests
from bs4 import BeautifulSoup

import interests
from catalog import CatalogError
from db import Database
from feed_sources import ARTICLE_TIERS, SOURCE_BY_ID, SOURCES, TIERS, Source
from timeutil import iso_utc as _iso
from timeutil import utcnow as _now
from xmlutil import parse_xml, text_of

REFRESH_INTERVAL = timedelta(hours=3)  # intervalo minimo entre buscas de uma mesma fonte
KEEP_DAYS = 45
SNIPPET_CHARS = 300
TITLE_CHARS = 300
MAX_FEED_BYTES = 3_000_000
HTTP_TIMEOUT = 15
WORKERS = 8
ON_DEMAND_BUDGET = 12  # fontes buscadas quando alguem abre o feed e os dados estao velhos
PAGE_SIZE = 20
PER_SOURCE_ROUND = 2  # por "rodada", cada fonte entra com ate isto antes de a proxima rodada comecar: a rolagem mistura as fontes
PER_SOURCE_VIEW = 12  # no maximo isto de cada fonte na tela, para uma fonte que publica muito nao tomar o feed
MAX_CANDIDATES = 800
RECENT_TTL = 30.0  # segundos que a lista de candidatos fica em memoria
USER_AGENT = "Lastro/1.0 (agregador de manchetes academicas)"
FUTURE_TOLERANCE = timedelta(days=2)

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS feed_items (
        id TEXT PRIMARY KEY, source_id TEXT NOT NULL, url TEXT NOT NULL, title TEXT NOT NULL, snippet TEXT NOT NULL,
        published_at TEXT NOT NULL, date_known INTEGER NOT NULL, topics TEXT NOT NULL, areas TEXT NOT NULL, fetched_at TEXT NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_feed_items_date ON feed_items (published_at)",
    """CREATE TABLE IF NOT EXISTS feed_state (
        source_id TEXT PRIMARY KEY, last_fetch TEXT NOT NULL, last_ok TEXT, etag TEXT, last_modified TEXT, error TEXT NOT NULL, items INTEGER NOT NULL)""",
)

# jornais trazem tambem comportamento, culinaria e cotidiano: so entra o que cita pesquisa ou ciencia
ACADEMIC_CUES = re.compile(r"estud|pesquis|cientist|cient[ií]fic|universid|ensaio cl[ií]nico|peri[oó]dico|publicad|descobert|study|researchers?", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_BLOCK_END = re.compile(r"</(?:p|div|li|h[1-6]|tr|blockquote)>|<br\s*/?>", re.IGNORECASE)  # fim de bloco vira espaco
_SPACES = re.compile(r"\s+")
_TZ_SHORT = re.compile(r"\s([+-]\d{3})$")  # "-030" (Folha) vira "-0300"
_WEEKDAY = re.compile(r"^[A-Za-z]{3},\s*")


@dataclass(frozen=True)
class Entry:
    title: str
    url: str
    snippet: str
    published: datetime | None  # None = o feed nao informa (ou informa de forma ilegivel)


@dataclass(frozen=True)
class FetchResult:
    status: int
    content: bytes = b""
    etag: str = ""
    last_modified: str = ""


@dataclass(frozen=True)
class FeedItem:
    id: str
    source_id: str
    url: str
    title: str
    snippet: str
    published_at: str
    date_known: bool
    topics: tuple[str, ...]
    areas: tuple[str, ...]


@dataclass(frozen=True)
class SourceState:
    source_id: str
    last_fetch: str
    last_ok: str
    error: str
    items: int
    etag: str = ""
    last_modified: str = ""


@dataclass(frozen=True)
class FeedPage:
    items: list[dict[str, Any]]
    total: int
    has_more: bool
    personalized: bool
    updated_at: str
    notes: list[str] = field(default_factory=list)




# ---------------------------------------------------------------------- leitura dos feeds (puro)
def parse_date(value: str) -> datetime | None:
    """Datas de feed: RFC 822 (com variantes como a da Folha) e ISO 8601; sempre em UTC, ou None se ilegivel."""
    text = (value or "").strip()
    if not text:
        return None
    padded = _TZ_SHORT.sub(lambda m: f" {m.group(1)}0", text)  # "-030" (Folha) e lido como -0300; sem isso viraria -00:30
    candidates = list(dict.fromkeys([padded, text, _WEEKDAY.sub("", padded)]))
    for candidate in candidates:
        try:
            parsed = parsedate_to_datetime(candidate)
        except (TypeError, ValueError, IndexError):
            continue
        if parsed is not None:
            return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def clean_snippet(html: str, limit: int = SNIPPET_CHARS) -> str:
    """Texto puro do resumo do feed, sem marcacao, em ate `limit` caracteres (cortado numa palavra)."""
    if not html:
        return ""
    if "<" in html:
        soup = BeautifulSoup(_BLOCK_END.sub(" ", html), "html.parser")
        for tag in soup(["script", "style"]):  # o conteudo de script e estilo nao e texto de leitura
            tag.decompose()
        text = soup.get_text()
    else:
        text = unescape(html)  # feeds que codificam duas vezes deixam "&#8220;" como texto
    text = _SPACES.sub(" ", _TAG.sub(" ", text)).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(" ,;:.-–—")
    return f"{cut}…"


def safe_url(value: str) -> str:
    link = (value or "").strip()
    return link if link.startswith(("http://", "https://")) and len(link) <= 2000 and " " not in link else ""


def _local(tag: object) -> str:
    return str(tag).rsplit("}", 1)[-1]


def _children(element: Element, name: str) -> list[Element]:
    return [child for child in element if _local(child.tag) == name]


def _entry_link(element: Element) -> str:
    for link in _children(element, "link"):
        href = link.attrib.get("href")
        if href:  # Atom: <link rel="alternate" href="..."/>
            if link.attrib.get("rel", "alternate") == "alternate":
                return safe_url(href)
            continue
        if link.text and link.text.strip():  # RSS e RDF
            return safe_url(link.text)
    for guid in _children(element, "guid"):
        if guid.attrib.get("isPermaLink", "true").lower() != "false" and guid.text:
            return safe_url(guid.text)
    return ""


def parse_feed(content: bytes) -> list[Entry]:
    """Itens de um feed RSS 2.0, Atom ou RSS 1.0 (RDF). Itens sem titulo ou sem link valido sao descartados."""
    root = parse_xml(content)
    entries: list[Entry] = []
    for element in root.iter():
        if _local(element.tag) not in ("item", "entry"):
            continue
        title = " ".join(unescape(text_of(_children(element, "title")[0])).split())[:TITLE_CHARS] if _children(element, "title") else ""  # alguns feeds codificam duas vezes
        link = _entry_link(element)
        if not title or not link:
            continue
        summary = ""
        for name in ("description", "summary", "encoded", "content"):
            found = _children(element, name)
            if found:
                summary = "".join(found[0].itertext())
                if summary.strip():
                    break
        when = None
        for name in ("pubDate", "published", "updated", "date"):
            found = _children(element, name)
            if found and found[0].text:
                when = parse_date(found[0].text)
                if when:
                    break
        entries.append(Entry(title, link, clean_snippet(summary), when))
    return entries


def item_id(source_id: str, url: str) -> str:
    return hashlib.sha256(f"{source_id}|{url}".encode()).hexdigest()[:24]


# ---------------------------------------------------------------------- armazenamento
class FeedStore:
    def __init__(self, database: Database | None = None) -> None:
        self._db = database or Database()
        self._recent_cache: tuple[float, int, list[FeedItem]] | None = None  # (quando, limite, itens): evita reler 800 linhas a cada visita

    def initialize(self) -> None:
        with self._db.transaction() as tx:
            for statement in _SCHEMA:
                tx.execute(statement)

    def upsert(self, items: Sequence[FeedItem], fetched_at: str) -> None:
        self._recent_cache = None
        with self._db.transaction() as tx:
            for item in items:
                tx.execute(
                    """INSERT INTO feed_items (id, source_id, url, title, snippet, published_at, date_known, topics, areas, fetched_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT (id) DO UPDATE SET title = excluded.title, snippet = excluded.snippet, topics = excluded.topics,
                       areas = excluded.areas, fetched_at = excluded.fetched_at""",
                    (item.id, item.source_id, item.url, item.title, item.snippet, item.published_at, 1 if item.date_known else 0,
                     json.dumps(item.topics), json.dumps(item.areas), fetched_at),
                )

    def prune(self, cutoff: datetime) -> int:
        self._recent_cache = None
        return self._db.execute("DELETE FROM feed_items WHERE published_at < ?", (_iso(cutoff),))

    def recent(self, limit: int = MAX_CANDIDATES) -> list[FeedItem]:
        cached = self._recent_cache
        if cached is not None and cached[1] == limit and time.monotonic() - cached[0] < RECENT_TTL:
            return cached[2]
        items = self._load_recent(limit)
        self._recent_cache = (time.monotonic(), limit, items)
        return items

    def _load_recent(self, limit: int) -> list[FeedItem]:
        rows = self._db.query(
            "SELECT id, source_id, url, title, snippet, published_at, date_known, topics, areas FROM feed_items "
            "ORDER BY published_at DESC, id LIMIT ?", (limit,),
        )
        items = []
        for iid, source_id, url, title, snippet, published, known, topics, areas in rows:
            try:
                topic_list, area_list = json.loads(topics), json.loads(areas)
            except ValueError:
                topic_list, area_list = [], []
            items.append(FeedItem(iid, source_id, url, title, snippet, published, bool(known), tuple(topic_list), tuple(area_list)))
        return items

    def state(self, source_id: str) -> SourceState | None:
        rows = self._db.query("SELECT source_id, last_fetch, last_ok, error, items, etag, last_modified FROM feed_state WHERE source_id = ?", (source_id,))
        if not rows:
            return None
        sid, last_fetch, last_ok, error, count, etag, modified = rows[0]
        return SourceState(sid, last_fetch, last_ok or "", error, int(count), etag or "", modified or "")

    def states(self) -> dict[str, SourceState]:
        rows = self._db.query("SELECT source_id, last_fetch, last_ok, error, items, etag, last_modified FROM feed_state")
        return {r[0]: SourceState(r[0], r[1], r[2] or "", r[3], int(r[4]), r[5] or "", r[6] or "") for r in rows}

    def set_state(self, state: SourceState) -> None:
        self._db.execute(
            """INSERT INTO feed_state (source_id, last_fetch, last_ok, etag, last_modified, error, items) VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT (source_id) DO UPDATE SET last_fetch = excluded.last_fetch, last_ok = excluded.last_ok, etag = excluded.etag,
               last_modified = excluded.last_modified, error = excluded.error, items = excluded.items""",
            (state.source_id, state.last_fetch, state.last_ok or None, state.etag, state.last_modified, state.error, state.items),
        )

    def latest_fetch(self) -> str:
        rows = self._db.query("SELECT MAX(last_fetch) FROM feed_state")
        return str(rows[0][0]) if rows and rows[0][0] else ""


# ---------------------------------------------------------------------- busca na rede
def http_fetch(url: str, etag: str = "", last_modified: str = "") -> FetchResult:
    """Busca um feed com requisicao condicional e limite de tamanho. So http(s); nunca guarda cookies."""
    if not url.startswith(("http://", "https://")):
        raise CatalogError("Endereço de feed inválido.")
    headers = {"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5"}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    try:
        with requests.get(url, headers=headers, timeout=HTTP_TIMEOUT, stream=True) as response:
            if response.status_code == 304:
                return FetchResult(304)
            if response.status_code != 200:
                return FetchResult(response.status_code)
            content = b""
            for chunk in response.iter_content(65536):
                content += chunk
                if len(content) > MAX_FEED_BYTES:
                    raise CatalogError("O feed é maior que o esperado.")
            return FetchResult(200, content, response.headers.get("ETag", ""), response.headers.get("Last-Modified", ""))
    except requests.RequestException as error:
        raise CatalogError(f"Sem resposta da fonte ({type(error).__name__}).") from error


Fetcher = Callable[[str, str, str], FetchResult]


# ---------------------------------------------------------------------- servico
def _mix_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mistura as fontes sem perder a ordem por data: as `PER_SOURCE_ROUND` mais novas de cada fonte vem primeiro, depois as proximas.

    Sem isso, uma fonte que publica tudo de uma vez (ou sem data no feed) ocupava a primeira tela inteira.
    """
    seen: dict[str, int] = {}
    banded = []
    for row in rows:  # `rows` ja vem do mais novo para o mais antigo
        source_id = str(row.get("source", {}).get("id", ""))
        banded.append((seen.get(source_id, 0) // PER_SOURCE_ROUND, row))
        seen[source_id] = seen.get(source_id, 0) + 1
    banded.sort(key=lambda pair: pair[0])  # estavel: dentro de cada rodada, a ordem por data continua
    return [row for _, row in banded]


class FeedService:
    def __init__(self, store: FeedStore, fetcher: Fetcher = http_fetch, clock: Callable[[], datetime] = _now) -> None:
        self._store = store
        self._fetch = fetcher
        self._clock = clock
        self._lock = threading.Lock()

    @property
    def store(self) -> FeedStore:
        return self._store

    # -- atualizacao -------------------------------------------------------
    def classify(self, entry: Entry, source: Source) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """(temas citados no titulo e no trecho, areas do item): as areas juntam as da fonte e as dos temas citados."""
        keys = tuple(interests.topic_keys_in(f"{entry.title}. {entry.snippet}"))
        areas = tuple(dict.fromkeys([*source.areas, *(key.partition("/")[0] for key in keys)]))
        return keys, areas

    def refresh_source(self, source: Source) -> int:
        """Busca uma fonte e guarda os itens recentes; devolve quantos itens ela tem agora. Nunca levanta por falha da fonte."""
        now = self._clock()
        previous = self._store.state(source.id)
        try:
            result = self._fetch(source.url, previous.etag if previous else "", previous.last_modified if previous else "")
            if result.status == 304 and previous:
                self._store.set_state(SourceState(source.id, _iso(now), previous.last_ok, "", previous.items, previous.etag, previous.last_modified))
                return previous.items
            if result.status != 200:
                raise CatalogError(f"A fonte respondeu HTTP {result.status}.")
            entries = parse_feed(result.content)
        except CatalogError as error:
            self._store.set_state(SourceState(source.id, _iso(now), previous.last_ok if previous else "", str(error)[:200], previous.items if previous else 0,
                                              previous.etag if previous else "", previous.last_modified if previous else ""))
            return previous.items if previous else 0
        cutoff = now - timedelta(days=KEEP_DAYS)
        newest = sorted(entries, key=lambda e: e.published or now, reverse=True)[: source.max_items]
        items = []
        for entry in newest:
            published = entry.published
            if published is not None and (published < cutoff or published > now + FUTURE_TOLERANCE):
                continue  # antigo demais, ou data futura (nao serve para ordenar)
            if source.tier == "jornal" and not ACADEMIC_CUES.search(f"{entry.title} {entry.snippet}"):
                continue
            topics, areas = self.classify(entry, source)
            items.append(FeedItem(item_id(source.id, entry.url), source.id, entry.url, entry.title, entry.snippet,
                                  _iso(published or now), published is not None, topics, areas))
        self._store.upsert(items, _iso(now))
        self._store.set_state(SourceState(source.id, _iso(now), _iso(now), "", len(items), result.etag, result.last_modified))
        return len(items)

    def due_sources(self, force: bool = False) -> list[Source]:
        states = self._store.states()
        cutoff = _iso(self._clock() - REFRESH_INTERVAL)
        due = [s for s in SOURCES if force or s.id not in states or states[s.id].last_fetch < cutoff]
        return sorted(due, key=lambda s: states[s.id].last_fetch if s.id in states else "")

    def refresh(self, budget: int | None = None, force: bool = False) -> dict[str, int]:
        """Atualiza as fontes vencidas (as mais antigas primeiro, ate `budget`) e apaga itens antigos. Uma execucao por vez."""
        if not self._lock.acquire(blocking=False):
            return {"due": 0, "refreshed": 0, "failed": 0, "items": 0, "skipped": 1}
        try:
            due = self.due_sources(force)
            batch = due[:budget] if budget else due
            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                counts = list(pool.map(self.refresh_source, batch))
            self._store.prune(self._clock() - timedelta(days=KEEP_DAYS))
            states = self._store.states()
            failed = sum(1 for s in batch if states.get(s.id) and states[s.id].error)
            return {"due": len(due), "refreshed": len(batch) - failed, "failed": failed, "items": sum(counts), "skipped": 0}
        finally:
            self._lock.release()

    def refresh_in_background(self) -> bool:
        """Dispara uma atualizacao parcial em segundo plano se ha fontes vencidas; devolve se disparou."""
        if self._lock.locked() or not self.due_sources():
            return False
        threading.Thread(target=self.refresh, kwargs={"budget": ON_DEMAND_BUDGET}, daemon=True).start()
        return True

    # -- leitura -----------------------------------------------------------
    def page(
        self, *, prefs: interests.Preferences | None, mode: str = "voce", kind: str = "todos", area: str = "", language: str = "",
        page: int = 1, article_items: Sequence[dict[str, Any]] = (),
    ) -> FeedPage:
        """Itens do feed, do mais recente para o mais antigo. Em "voce" so entram os que citam algum interesse da pessoa."""
        personalized = bool(prefs and not prefs.empty and mode == "voce")
        selected = prefs.selected() if prefs else []
        terms = list(prefs.terms) if prefs else []
        rows: list[dict[str, Any]] = []
        per_source: dict[str, int] = {}
        for item in self._store.recent():
            source = SOURCE_BY_ID.get(item.source_id)
            if source is None:
                continue
            is_article = source.tier in ARTICLE_TIERS
            if kind == "artigos" and not is_article or kind == "noticias" and is_article:
                continue
            if language and source.language != language:
                continue
            if area and area not in item.areas:
                continue
            matched: list[str] = []
            if personalized:
                matched = [topic.label for topic in selected if topic.key in item.topics]
                matched += [f"“{term}”" for term in terms if interests.mentions(f"{item.title}. {item.snippet}", (term,))]
                if not matched:
                    continue
            per_source[item.source_id] = per_source.get(item.source_id, 0) + 1
            if per_source[item.source_id] > PER_SOURCE_VIEW:
                continue
            rows.append({
                "id": item.id, "kind": "artigo" if is_article else "noticia", "title": item.title, "snippet": item.snippet, "url": item.url,
                "publishedAt": item.published_at, "dateKnown": item.date_known, "areas": [interests.area_label(a) for a in item.areas], "areaKeys": list(item.areas),
                "matched": list(dict.fromkeys(matched)),
                "source": {"id": source.id, "name": source.name, "tier": source.tier, "tierLabel": TIERS[source.tier][0], "language": source.language, "site": source.site},
            })
        if kind in ("todos", "artigos") and not language and article_items:
            rows += [dict(entry) for entry in article_items if not area or entry.get("area") == area]
        rows.sort(key=lambda row: row["publishedAt"], reverse=True)
        rows = _mix_sources(rows)
        total = len(rows)
        start = (max(page, 1) - 1) * PAGE_SIZE
        return FeedPage(rows[start:start + PAGE_SIZE], total, start + PAGE_SIZE < total, personalized, self._store.latest_fetch())
