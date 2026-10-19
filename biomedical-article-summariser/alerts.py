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
from datetime import date, datetime, timedelta, timezone

from catalog import SearchQuery, Work
from db import Database
from domain import DiggerError, NotFoundError
from interests import Preferences, Topic, carregar, mentions

AUTO_INTERVAL = timedelta(hours=6)
MANUAL_INTERVAL = timedelta(minutes=15)
MAX_SEARCHES = 24
MAX_NEW_PER_CHECK = 30
PER_TOPIC_NEW = 5  # temas amplos (ex.: pediatria) trazem centenas por semana; mostramos so os mais recentes
RECENT_DAYS = 60  # com data de publicacao conhecida, artigo mais velho que isso nao conta como novo
MAX_ALERTS = 200
MAX_USERS_PER_RUN = 40  # por execucao agendada; o restante fica para a proxima
MAX_SEEN = 5000
RECENT_YEARS = 1  # considera artigos do ano corrente e do anterior
PER_SEARCH = 20
ABSTRACT_MIN_TERMS = 2  # termos distintos do tema no resumo, quando o titulo nao os traz
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


def eligible(work: Work, now: datetime) -> bool:
    """Pode virar aviso: data conhecida e recente, ou sem data confiavel (so o criterio "ainda nao visto").

    As fontes trazem datas futuras (fasciculos programados, ate 2099 no OpenAIRE); essas nao servem para dizer se e novo,
    mas o ano absurdo descarta o registro.
    """
    if work.year and work.year > now.year + 1:
        return False
    try:
        published = date.fromisoformat(work.published[:10]) if len(work.published) >= 10 else None
    except ValueError:
        published = None
    if published is None or published > now.date():
        return True
    return (now.date() - published).days <= RECENT_DAYS


def on_topic(work: Work, alternatives: tuple[str, ...]) -> bool:
    """As fontes devolvem ruido (uma palavra casa em outro sentido, ou numa citacao de passagem): conferimos o texto.

    Vale quando o titulo, as palavras-chave ou a revista tratam do tema, ou quando o resumo cita ao menos dois termos diferentes.
    """
    if mentions(" ".join([work.title, " ".join(work.keywords), work.journal]), alternatives):
        return True
    return sum(mentions(work.abstract, (alt,)) for alt in alternatives) >= ABSTRACT_MIN_TERMS


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

    def due_users(self, cutoff: datetime, limit: int) -> list[str]:
        """Contas com interesses cuja ultima verificacao e anterior ao corte (as nunca verificadas primeiro)."""
        rows = self._db.query(
            "SELECT user_email FROM interest_prefs WHERE last_checked IS NULL OR last_checked < ? ORDER BY COALESCE(last_checked, '') ASC LIMIT ?",
            (_iso(cutoff), limit),
        )
        return [row[0] for row in rows]

    def delete_user_data(self, user: str) -> None:
        with self._db.transaction() as tx:
            for table in ("interest_prefs", "interest_baselines", "alert_seen", "alerts"):
                tx.execute(f"DELETE FROM {table} WHERE user_email = ?", (user,))  # noqa: S608 - nomes fixos acima

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
        result.sort(key=lambda a: (a.created_at, a.work.published), reverse=True)  # mesmo lote: o mais recente primeiro
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
    alternatives: tuple[str, ...]  # o resultado so conta se o titulo ou resumo tratar do tema


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
                searches.append(_Search(topic.label, _search_key(topic.key, language), SearchQuery(q=topic.query(language), language=language, **base), topic.alternatives(language)))  # type: ignore[arg-type]
        for term in prefs.terms:
            for language in languages:
                searches.append(_Search(f"“{term}”", _search_key("termo", language, term), SearchQuery(q=term, language=language, **base), (term,)))  # type: ignore[arg-type]
        return searches[:MAX_SEARCHES]

    def check_all(self, *, max_users: int = MAX_USERS_PER_RUN) -> dict[str, int]:
        """Verificacao agendada (sem o usuario no site): as contas vencidas, da mais antiga para a mais nova."""
        now = self._clock()
        summary = {"due": 0, "ran": 0, "new": 0, "failed": 0}
        for user in self._store.due_users(now - AUTO_INTERVAL, max_users):
            summary["due"] += 1
            try:
                result = self.check(user)
            except Exception:  # noqa: BLE001 - uma conta com problema nao pode parar as demais
                summary["failed"] += 1
                continue
            summary["ran"] += int(result.ran)
            summary["new"] += result.new
        return summary

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
        silent: dict[str, None] = {}  # vistos sem avisar: linha de base, artigos antigos e excedentes
        for item, works in done:
            usable = [w for w in works if not w.retracted and w.title.strip() and on_topic(w, item.alternatives)]
            if item.key not in baselined:
                fresh_baselines.append(item.key)
                silent.update({work_key(w): None for w in usable})
                continue
            for work in usable:
                if eligible(work, now):
                    candidates.setdefault(work_key(work), (work, item.topic))
                else:
                    silent[work_key(work)] = None
        known = self._store.seen(user, list(candidates))
        fresh = [(w, topic) for key, (w, topic) in candidates.items() if key not in known and key not in silent]
        fresh.sort(key=lambda pair: (pair[0].published, pair[0].cited_by), reverse=True)
        novos: list[tuple[Work, str]] = []
        per_topic: dict[str, int] = {}
        for work, topic in fresh:
            if per_topic.get(topic, 0) < PER_TOPIC_NEW and len(novos) < MAX_NEW_PER_CHECK:
                per_topic[topic] = per_topic.get(topic, 0) + 1
                novos.append((work, topic))
            else:
                silent[work_key(work)] = None  # tema amplo: mostramos so os mais recentes e nao deixamos fila acumulada
        created = self._store.add_alerts(user, novos) if novos else 0
        self._store.mark_seen(user, list(silent) + [work_key(w) for w, _ in novos])
        if fresh_baselines:
            self._store.add_baselines(user, fresh_baselines)
        self._store.touch_checked(user, now)
        return CheckResult(True, new=created, baseline=bool(fresh_baselines) and not created, notes=tuple(dict.fromkeys(notes)))
