"""Alertas de artigos novos: preferencias de interesse por conta, verificacao periodica e caixa de avisos (o "sininho").

Como funciona: ao salvar os interesses, a proxima verificacao apenas *memoriza* os artigos recentes ja existentes
(a linha de base), para nao despejar artigos antigos como se fossem novos. Nas verificacoes seguintes, todo artigo recente
que ainda nao tinha sido visto vira um aviso. A verificacao roda quando o usuario esta com o site aberto (nao ha
tarefa em segundo plano nem e-mail ainda) e respeita um intervalo minimo para nao sobrecarregar as fontes.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from catalog import SearchQuery, Work
from db import Database
from domain import DiggerError, NotFoundError
from interests import Preferences, Topic, carregar

AUTO_INTERVAL = timedelta(hours=6)
MANUAL_INTERVAL = timedelta(minutes=15)
MAX_SEARCHES = 24
MAX_NEW_PER_CHECK = 30
MAX_ALERTS = 200
MAX_SEEN = 5000
RECENT_YEARS = 1  # considera artigos do ano corrente e do anterior
PER_SEARCH = 10
MAX_ABSTRACT_CHARS = 1500
WORKERS = 4

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS interest_prefs (user_email TEXT PRIMARY KEY, data TEXT NOT NULL, updated_at TEXT NOT NULL, last_checked TEXT)",
    "CREATE TABLE IF NOT EXISTS interest_baselines (user_email TEXT NOT NULL, search_key TEXT NOT NULL, PRIMARY KEY (user_email, search_key))",
    "CREATE TABLE IF NOT EXISTS alert_seen (user_email TEXT NOT NULL, work_key TEXT NOT NULL, seen_at TEXT NOT NULL, PRIMARY KEY (user_email, work_key))",
    """CREATE TABLE IF NOT EXISTS alerts (
        id TEXT PRIMARY KEY, user_email TEXT NOT NULL, work_key TEXT NOT NULL, ref TEXT NOT NULL, data TEXT NOT NULL,
        topic TEXT NOT NULL, created_at TEXT NOT NULL, read_at TEXT, UNIQUE (user_email, work_key))""",
    "CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts (user_email, created_at)",
)


@dataclass(frozen=True)
class Alert:
    id: str
    work: Work
    topic: str
    created_at: str
    read: bool


@dataclass(frozen=True)
class CheckResult:
    ran: bool  # False quando o intervalo minimo ainda nao passou ou nao ha interesses
    new: int = 0
    reason: str = ""  # "sem-interesses" | "intervalo" | ""
    baseline: bool = False  # a verificacao so memorizou os artigos atuais
    notes: tuple[str, ...] = field(default_factory=tuple)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def work_key(work: Work) -> str:
    """Identidade do artigo entre fontes: o DOI quando existe, senao a referencia da fonte."""
    return (work.doi.strip().lower() if work.doi else "") or work.ref


def _snapshot(work: Work) -> str:
    data = work.to_dict()
    data["abstract"] = str(data["abstract"])[:MAX_ABSTRACT_CHARS]
    return json.dumps(data, ensure_ascii=False)


def _search_key(topic_key: str, language: str, term: str = "") -> str:
    base = f"{topic_key}|{language}|{term.lower()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]


class AlertStore:
    def __init__(self, database: Database | None = None) -> None:
        self._db = database or Database()

    def initialize(self) -> None:
        with self._db.transaction() as tx:
            for statement in _SCHEMA:
                tx.execute(statement)

    # ------------------------------------------------------------------ preferencias
    def preferences(self, user: str) -> tuple[Preferences, datetime | None]:
        rows = self._db.query("SELECT data, last_checked FROM interest_prefs WHERE user_email = ?", (user,))
        if not rows:
            return Preferences(), None
        try:
            raw = json.loads(rows[0][0])
        except ValueError:
            raw = {}
        checked = None
        if rows[0][1]:
            try:
                checked = datetime.fromisoformat(rows[0][1])
            except ValueError:
                checked = None
        return carregar(raw if isinstance(raw, dict) else {}), checked

    def set_preferences(self, user: str, prefs: Preferences) -> None:
        # last_checked volta a nulo: a proxima verificacao pode rodar de imediato
        self._db.execute(
            """INSERT INTO interest_prefs (user_email, data, updated_at, last_checked) VALUES (?, ?, ?, NULL)
               ON CONFLICT (user_email) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at, last_checked = NULL""",
            (user, json.dumps(prefs.to_dict(), ensure_ascii=False), _iso(_now())),
        )

    def touch_checked(self, user: str, moment: datetime) -> None:
        self._db.execute("UPDATE interest_prefs SET last_checked = ? WHERE user_email = ?", (_iso(moment), user))

    # ------------------------------------------------------------------ verificacao
    def baselined(self, user: str) -> set[str]:
        return {row[0] for row in self._db.query("SELECT search_key FROM interest_baselines WHERE user_email = ?", (user,))}

    def add_baselines(self, user: str, keys: list[str]) -> None:
        with self._db.transaction() as tx:
            for key in keys:
                tx.execute("INSERT INTO interest_baselines (user_email, search_key) VALUES (?, ?) ON CONFLICT DO NOTHING", (user, key))

    def seen(self, user: str, keys: list[str]) -> set[str]:
        found: set[str] = set()
        for start in range(0, len(keys), 200):
            chunk = keys[start:start + 200]
            marks = ", ".join("?" for _ in chunk)
            rows = self._db.query(f"SELECT work_key FROM alert_seen WHERE user_email = ? AND work_key IN ({marks})", (user, *chunk))  # noqa: S608 - so marcadores
            found.update(row[0] for row in rows)
        return found

    def mark_seen(self, user: str, keys: list[str]) -> None:
        now = _iso(_now())
        with self._db.transaction() as tx:
            for key in keys:
                tx.execute("INSERT INTO alert_seen (user_email, work_key, seen_at) VALUES (?, ?, ?) ON CONFLICT DO NOTHING", (user, key, now))
            tx.execute(
                "DELETE FROM alert_seen WHERE user_email = ? AND work_key NOT IN "
                "(SELECT work_key FROM alert_seen WHERE user_email = ? ORDER BY seen_at DESC LIMIT ?)",
                (user, user, MAX_SEEN),
            )

    def add_alerts(self, user: str, items: list[tuple[Work, str]]) -> int:
        created = 0
        now = _iso(_now())
        with self._db.transaction() as tx:
            for work, topic in items:
                created += tx.execute(
                    """INSERT INTO alerts (id, user_email, work_key, ref, data, topic, created_at, read_at) VALUES (?, ?, ?, ?, ?, ?, ?, NULL)
                       ON CONFLICT (user_email, work_key) DO NOTHING""",
                    (uuid.uuid4().hex, user, work_key(work), work.ref, _snapshot(work), topic, now),
                )
            tx.execute(
                "DELETE FROM alerts WHERE user_email = ? AND id NOT IN (SELECT id FROM alerts WHERE user_email = ? ORDER BY created_at DESC LIMIT ?)",
                (user, user, MAX_ALERTS),
            )
        return created

    # ------------------------------------------------------------------ caixa de avisos
    def alerts(self, user: str, limit: int = 50) -> list[Alert]:
        rows = self._db.query(
            "SELECT id, data, topic, created_at, read_at FROM alerts WHERE user_email = ? ORDER BY created_at DESC, id LIMIT ?", (user, limit)
        )
        result = []
        for alert_id, raw, topic, created, read_at in rows:
            try:
                data = json.loads(raw)
            except ValueError:
                data = {}
            result.append(Alert(alert_id, Work.from_dict(data if isinstance(data, dict) else {}), topic, created, read_at is not None))
        return result

    def unread(self, user: str) -> int:
        return int(self._db.query("SELECT COUNT(*) FROM alerts WHERE user_email = ? AND read_at IS NULL", (user,))[0][0])

    def mark_read(self, user: str, alert_id: str | None = None) -> None:
        now = _iso(_now())
        if alert_id is None:
            self._db.execute("UPDATE alerts SET read_at = ? WHERE user_email = ? AND read_at IS NULL", (now, user))
        elif not self._db.execute("UPDATE alerts SET read_at = COALESCE(read_at, ?) WHERE user_email = ? AND id = ?", (now, user, alert_id)):
            raise NotFoundError("Aviso não encontrado.")

    def dismiss(self, user: str, alert_id: str) -> None:
        self._db.execute("DELETE FROM alerts WHERE user_email = ? AND id = ?", (user, alert_id))


Searcher = Callable[[SearchQuery, str], tuple[Work, ...]]  # (consulta, usuario) -> artigos


@dataclass(frozen=True)
class _Search:
    topic: str  # rotulo para exibir
    key: str
    query: SearchQuery


class AlertService:
    def __init__(self, store: AlertStore, searcher: Searcher, clock: Callable[[], datetime] = _now) -> None:
        self._store = store
        self._search = searcher
        self._clock = clock

    @property
    def store(self) -> AlertStore:
        return self._store

    def _searches(self, prefs: Preferences, today: datetime) -> list[_Search]:
        """Uma busca por (tema, idioma) e por palavra-chave; sem idioma escolhido, sem filtro de idioma."""
        languages = list(prefs.languages) or [""]
        base = {"sort": "recent", "year_from": today.year - RECENT_YEARS, "per_page": PER_SEARCH}
        searches: list[_Search] = []
        topics: list[Topic] = prefs.selected()
        for topic in topics:
            for language in languages:
                searches.append(_Search(topic.label, _search_key(topic.key, language), SearchQuery(q=topic.query(language), language=language, **base)))  # type: ignore[arg-type]
        for term in prefs.terms:
            for language in languages:
                searches.append(_Search(f"“{term}”", _search_key("termo", language, term), SearchQuery(q=term, language=language, **base)))  # type: ignore[arg-type]
        return searches[:MAX_SEARCHES]

    def check(self, user: str, *, force: bool = False) -> CheckResult:
        prefs, last = self._store.preferences(user)
        if prefs.empty:
            return CheckResult(False, reason="sem-interesses")
        now = self._clock()
        wait = MANUAL_INTERVAL if force else AUTO_INTERVAL
        if last is not None and now - last < wait:
            return CheckResult(False, reason="intervalo")
        searches = self._searches(prefs, now)
        notes: list[str] = []

        def run(item: _Search) -> tuple[_Search, tuple[Work, ...] | None]:
            try:
                return item, self._search(item.query, user)
            except DiggerError as error:
                notes.append(error.user_message)
                return item, None

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            outcomes = list(pool.map(run, searches))
        done = [(item, works) for item, works in outcomes if works is not None]
        if not done:
            return CheckResult(False, reason="fontes", notes=tuple(dict.fromkeys(notes)))
        baselined = self._store.baselined(user)
        fresh_baselines: list[str] = []
        candidates: dict[str, tuple[Work, str]] = {}
        silent: dict[str, None] = {}
        for item, works in done:
            usable = [w for w in works if not w.retracted and w.title.strip()]
            if item.key not in baselined:
                fresh_baselines.append(item.key)
                silent.update({work_key(w): None for w in usable})
                continue
            for work in usable:
                candidates.setdefault(work_key(work), (work, item.topic))
        known = self._store.seen(user, list(candidates))
        novos = [(w, topic) for key, (w, topic) in candidates.items() if key not in known and key not in silent]
        novos.sort(key=lambda pair: (pair[0].year or 0, pair[0].cited_by), reverse=True)
        novos = novos[:MAX_NEW_PER_CHECK]
        created = self._store.add_alerts(user, novos) if novos else 0
        self._store.mark_seen(user, list(silent) + [work_key(w) for w, _ in novos])
        if fresh_baselines:
            self._store.add_baselines(user, fresh_baselines)
        self._store.touch_checked(user, now)
        return CheckResult(True, new=created, baseline=bool(fresh_baselines) and not created, notes=tuple(dict.fromkeys(notes)))
