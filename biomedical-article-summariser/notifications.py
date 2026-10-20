"""Notificacoes do sininho alem dos artigos novos por interesse: retratacao, mudanca regulatoria e novidades dos relatorios.

Tipos e prioridade (o canal por enquanto e so o sininho do site; e-mail e outros virao depois):

| tipo              | prioridade | quando avisa                                                                           |
|-------------------|------------|----------------------------------------------------------------------------------------|
| `retratacao`      | alta       | um artigo da sua biblioteca, de uma lista ou de um relatorio passou a constar como retratado |
| `regulatorio`     | alta       | uma substancia que voce confirmou em um relatorio teve mudanca na ANVISA, na Conitec ou na Rename |
| `relatorio-lista` | media      | entraram artigos novos na lista de origem de um relatorio                              |
| `novo-artigo`     | media      | artigo novo nos seus interesses (fica em `alerts.py`)                                  |

Tudo e calculado por codigo; nenhum aviso e escrito por IA. As verificacoes rodam com o site aberto (e pela rota agendada) e
respeitam um intervalo minimo. Retratacao so e detectada quando a fonte do registro informa (Europe PMC, PubMed e OpenAlex);
correcoes (errata) nao sao detectadas.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from brasil import anvisa, conitec, consulta, rename
from catalog import Work
from db import Database
from domain import DiggerError, RateLimitedError
from library_store import LibraryStore
from report_brasil import display_name
from reports import ReportStore
from timeutil import iso as _iso
from timeutil import utcnow as _now

AUTO_INTERVAL = timedelta(hours=6)
MANUAL_INTERVAL = timedelta(minutes=15)
RETRACTION_RECHECK = timedelta(days=7)  # cada artigo e reconferido, no maximo, uma vez por semana
USER_REFRESH_BUDGET = 15  # artigos conferidos por verificacao de uma conta
GLOBAL_REFRESH_BUDGET = 40  # artigos conferidos por execucao agendada (todas as contas)
MAX_NOTIFICATIONS = 200
MAX_USERS_PER_RUN = 40
LIST_TITLES_SHOWN = 3
CONITEC_SHOWN = 3
INDICATION_CHARS = 110

# tipo -> (prioridade, rotulo na tela de preferencias, descricao)
KINDS: dict[str, tuple[int, str, str]] = {
    "retratacao": (2, "Artigo retratado", "Um artigo da sua biblioteca, de uma lista ou de um relatório passou a constar como retratado na fonte."),
    "regulatorio": (2, "Mudança regulatória", "Uma substância confirmada em um relatório mudou na ANVISA, na Conitec ou na Rename."),
    "relatorio-lista": (1, "Novidades dos relatórios", "Entraram artigos novos na lista de origem de um relatório."),
    "novo-artigo": (1, "Artigos novos nos interesses", "Artigos novos sobre as áreas, os subtemas e as palavras-chave que você acompanha."),
}

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY, user_email TEXT NOT NULL, kind TEXT NOT NULL, priority INTEGER NOT NULL, dedupe_key TEXT NOT NULL,
        group_key TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, link TEXT NOT NULL, data TEXT NOT NULL,
        created_at TEXT NOT NULL, read_at TEXT, UNIQUE (user_email, dedupe_key))""",
    "CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications (user_email, created_at)",
    "CREATE TABLE IF NOT EXISTS retraction_status (ref TEXT PRIMARY KEY, retracted INTEGER NOT NULL, checked_at TEXT NOT NULL)",
    """CREATE TABLE IF NOT EXISTS regulatory_state (
        user_email TEXT NOT NULL, term TEXT NOT NULL, fingerprint TEXT NOT NULL, checked_at TEXT NOT NULL, PRIMARY KEY (user_email, term))""",
    "CREATE TABLE IF NOT EXISTS watch_state (user_email TEXT PRIMARY KEY, last_run TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS notification_prefs (user_email TEXT PRIMARY KEY, data TEXT NOT NULL)",
)

Bases = tuple[anvisa.Instantaneo, conitec.Instantaneo, rename.Instantaneo]


@dataclass(frozen=True)
class Notification:
    id: str
    kind: str
    priority: int
    title: str
    body: str
    link: str  # endereco dentro do site (#/...)
    created_at: str
    read: bool
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NewNotification:
    kind: str
    dedupe_key: str
    title: str
    body: str
    link: str
    group_key: str = ""  # um aviso novo do mesmo grupo substitui o anterior ainda nao lido
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WatchResult:
    ran: bool
    reason: str = ""  # "intervalo" quando ainda nao passou o tempo minimo
    created: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.created.values())




def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


class NotificationStore:
    def __init__(self, database: Database | None = None) -> None:
        self._db = database or Database()

    def initialize(self) -> None:
        with self._db.transaction() as tx:
            for statement in _SCHEMA:
                tx.execute(statement)

    # ------------------------------------------------------------------ caixa
    def add(self, user: str, item: NewNotification) -> bool:
        """Cria o aviso; False se ja existia um com a mesma chave. Substitui o aviso nao lido do mesmo grupo."""
        with self._db.transaction() as tx:
            if tx.query("SELECT 1 FROM notifications WHERE user_email = ? AND dedupe_key = ?", (user, item.dedupe_key)):
                return False
            if item.group_key:
                tx.execute("DELETE FROM notifications WHERE user_email = ? AND group_key = ? AND read_at IS NULL", (user, item.group_key))
            tx.execute(
                "INSERT INTO notifications (id, user_email, kind, priority, dedupe_key, group_key, title, body, link, data, created_at, read_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                (uuid.uuid4().hex, user, item.kind, KINDS[item.kind][0], item.dedupe_key, item.group_key, item.title, item.body, item.link,
                 json.dumps(item.data, ensure_ascii=False), _iso(_now())),
            )
            tx.execute(
                "DELETE FROM notifications WHERE user_email = ? AND id NOT IN "
                "(SELECT id FROM notifications WHERE user_email = ? ORDER BY created_at DESC LIMIT ?)",
                (user, user, MAX_NOTIFICATIONS),
            )
        return True

    def notifications(self, user: str, limit: int = 100) -> list[Notification]:
        rows = self._db.query(
            "SELECT id, kind, priority, title, body, link, data, created_at, read_at FROM notifications "
            "WHERE user_email = ? ORDER BY created_at DESC, id LIMIT ?", (user, limit),
        )
        result = []
        for nid, kind, priority, title, body, link, raw, created, read_at in rows:
            try:
                data = json.loads(raw)
            except ValueError:
                data = {}
            result.append(Notification(nid, kind, int(priority), title, body, link, created, read_at is not None, data if isinstance(data, dict) else {}))
        return result

    def unread(self, user: str) -> int:
        return int(self._db.query("SELECT COUNT(*) FROM notifications WHERE user_email = ? AND read_at IS NULL", (user,))[0][0])

    def mark_read(self, user: str, notification_id: str | None = None) -> bool:
        """Marca um aviso (ou todos) como lido; devolve se algum aviso foi encontrado."""
        now = _iso(_now())
        if notification_id is None:
            self._db.execute("UPDATE notifications SET read_at = ? WHERE user_email = ? AND read_at IS NULL", (now, user))
            return True
        return self._db.execute("UPDATE notifications SET read_at = COALESCE(read_at, ?) WHERE user_email = ? AND id = ?", (now, user, notification_id)) > 0

    def dismiss(self, user: str, notification_id: str) -> None:
        self._db.execute("DELETE FROM notifications WHERE user_email = ? AND id = ?", (user, notification_id))

    def delete_user_data(self, user: str) -> None:
        with self._db.transaction() as tx:
            for table in ("notifications", "regulatory_state", "watch_state", "notification_prefs"):
                tx.execute(f"DELETE FROM {table} WHERE user_email = ?", (user,))  # noqa: S608 - nomes fixos acima

    # ------------------------------------------------------------------ preferencias
    def prefs(self, user: str) -> dict[str, bool]:
        rows = self._db.query("SELECT data FROM notification_prefs WHERE user_email = ?", (user,))
        try:
            raw = json.loads(rows[0][0]) if rows else {}
        except ValueError:
            raw = {}
        raw = raw if isinstance(raw, dict) else {}
        return {kind: raw.get(kind) is not False for kind in KINDS}  # tudo ligado por padrao

    def set_prefs(self, user: str, choices: dict[str, bool]) -> dict[str, bool]:
        current = self.prefs(user)
        current.update({kind: bool(value) for kind, value in choices.items() if kind in KINDS})
        self._db.execute(
            "INSERT INTO notification_prefs (user_email, data) VALUES (?, ?) ON CONFLICT (user_email) DO UPDATE SET data = excluded.data",
            (user, json.dumps(current)),
        )
        return current

    # ------------------------------------------------------------------ retratacao
    def retraction_status(self, refs: list[str]) -> dict[str, tuple[bool, str]]:
        found: dict[str, tuple[bool, str]] = {}
        for start in range(0, len(refs), 200):
            chunk = refs[start:start + 200]
            marks = ", ".join("?" for _ in chunk)
            rows = self._db.query(f"SELECT ref, retracted, checked_at FROM retraction_status WHERE ref IN ({marks})", tuple(chunk))  # noqa: S608 - so marcadores
            found.update({ref: (bool(retracted), checked) for ref, retracted, checked in rows})
        return found

    def set_retraction(self, ref: str, retracted: bool, checked_at: datetime | None = None) -> None:
        """Grava o estado de retratacao; `checked_at` e o relogio do servico (a hora da conferencia), padrao: agora."""
        self._db.execute(
            "INSERT INTO retraction_status (ref, retracted, checked_at) VALUES (?, ?, ?) "
            "ON CONFLICT (ref) DO UPDATE SET retracted = excluded.retracted, checked_at = excluded.checked_at",
            (ref, 1 if retracted else 0, _iso(checked_at or _now())),
        )

    # ------------------------------------------------------------------ regulatorio
    def regulatory_fingerprint(self, user: str, term: str) -> str | None:
        rows = self._db.query("SELECT fingerprint FROM regulatory_state WHERE user_email = ? AND term = ?", (user, term))
        return str(rows[0][0]) if rows else None

    def set_regulatory_fingerprint(self, user: str, term: str, fingerprint: str) -> None:
        self._db.execute(
            "INSERT INTO regulatory_state (user_email, term, fingerprint, checked_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (user_email, term) DO UPDATE SET fingerprint = excluded.fingerprint, checked_at = excluded.checked_at",
            (user, term, fingerprint, _iso(_now())),
        )

    # ------------------------------------------------------------------ agendamento
    def last_run(self, user: str) -> datetime | None:
        rows = self._db.query("SELECT last_run FROM watch_state WHERE user_email = ?", (user,))
        if not rows:
            return None
        try:
            return datetime.fromisoformat(rows[0][0])
        except ValueError:
            return None

    def touch(self, user: str, moment: datetime) -> None:
        self._db.execute(
            "INSERT INTO watch_state (user_email, last_run) VALUES (?, ?) ON CONFLICT (user_email) DO UPDATE SET last_run = excluded.last_run",
            (user, _iso(moment)),
        )

    def due_users(self, cutoff: datetime, limit: int) -> list[str]:
        """Contas cuja ultima verificacao e anterior ao corte (as nunca verificadas primeiro)."""
        try:
            rows = self._db.query(
                "SELECT u.email FROM users u LEFT JOIN watch_state w ON w.user_email = u.email "
                "WHERE w.last_run IS NULL OR w.last_run < ? ORDER BY COALESCE(w.last_run, '') ASC LIMIT ?", (_iso(cutoff), limit),
            )
        except Exception:  # noqa: BLE001 - sem a tabela de contas neste banco (testes isolados), nao ha o que verificar
            return []
        return [str(row[0]) for row in rows]


# ---------------------------------------------------------------------- regulatorio (puro)
def regulatory_fingerprint(item: consulta.Situacao) -> dict[str, Any]:
    """Estado regulatorio resumido de uma substancia, comparavel entre dois instantaneos das bases."""
    exact_rename = next((r for r in item.rename if r.chave == item.termo), item.rename[0] if item.rename else None)
    exact_anvisa = next((a for a in item.anvisa if a.chave == item.termo), item.anvisa[0] if item.anvisa else None)
    return {
        "conitec": sorted(f"{r.ano}|{r.recomendacao}|{r.indicacao}|{r.portaria}" for r in item.conitec),
        "rename": sorted(exact_rename.componentes) if exact_rename else [],
        "anvisa_ativo": bool(exact_anvisa and exact_anvisa.ativos > 0),
    }


def describe_regulatory_change(old: dict[str, Any], new: dict[str, Any], item: consulta.Situacao) -> list[str]:
    """Frases curtas sobre o que mudou entre o estado guardado e o atual (vazio quando nada relevante mudou)."""
    lines: list[str] = []
    fresh = [key for key in new.get("conitec", []) if key not in set(old.get("conitec", []))]
    by_key = {f"{r.ano}|{r.recomendacao}|{r.indicacao}|{r.portaria}": r for r in item.conitec}
    for key in fresh[:CONITEC_SHOWN]:
        record = by_key[key]
        indication = record.indicacao if len(record.indicacao) <= INDICATION_CHARS else record.indicacao[: INDICATION_CHARS - 1] + "…"
        lines.append(f"Conitec: nova decisão ({record.ano or 's.d.'}, {record.recomendacao or 'sem recomendação informada'})" + (f" para {indication}" if indication else ""))
    if len(fresh) > CONITEC_SHOWN:
        lines.append(f"Conitec: mais {len(fresh) - CONITEC_SHOWN} decisões novas")
    removed = [key for key in old.get("conitec", []) if key not in set(new.get("conitec", []))]
    if removed:
        lines.append(f"Conitec: {len(removed)} {'decisão não consta' if len(removed) == 1 else 'decisões não constam'} mais na base")
    if not old.get("rename") and new.get("rename"):
        lines.append(f"Rename: passou a constar (componente {', '.join(new['rename']).lower()})")
    elif old.get("rename") and not new.get("rename"):
        lines.append("Rename: deixou de constar")
    elif old.get("rename") != new.get("rename"):
        lines.append(f"Rename: componente alterado para {', '.join(new['rename']).lower()}")
    if not old.get("anvisa_ativo") and new.get("anvisa_ativo"):
        lines.append("ANVISA: passou a ter registro ativo")
    elif old.get("anvisa_ativo") and not new.get("anvisa_ativo"):
        lines.append("ANVISA: não tem mais registro ativo")
    return lines


# ---------------------------------------------------------------------- servico
class NotificationService:
    def __init__(
        self,
        store: NotificationStore,
        *,
        fetch_work: Callable[[str], Work | None],
        library: LibraryStore,
        reports: ReportStore,
        bases: Callable[[], Bases | None],
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._store = store
        self._fetch = fetch_work
        self._library = library
        self._reports = reports
        self._bases = bases
        self._clock = clock

    @property
    def store(self) -> NotificationStore:
        return self._store

    # ------------------------------------------------------------------ retratacao
    def _watched(self, user: str) -> dict[str, tuple[Work, list[str]]]:
        """Artigos que a conta guarda (biblioteca, listas e relatorios), com onde cada um esta."""
        watched: dict[str, tuple[Work, list[str]]] = {}
        for place, work in [*self._library.watched_works(user), *self._reports.watched_works(user)]:
            entry = watched.setdefault(work.ref, (work, []))
            if place not in entry[1]:
                entry[1].append(place)
        return watched

    def refresh_retractions(self, refs: set[str], budget: int) -> int:
        """Reconfere na fonte os artigos nunca vistos ou vistos ha mais de uma semana (ate `budget`); devolve quantos conferiu."""
        now = self._clock()
        status = self._store.retraction_status(sorted(refs))
        cutoff = _iso(now - RETRACTION_RECHECK)
        stale = sorted((ref for ref in refs if ref not in status or status[ref][1] < cutoff), key=lambda ref: status.get(ref, (False, ""))[1])
        checked = 0
        for ref in stale[:budget]:
            try:
                work = self._fetch(ref)
            except RateLimitedError:
                break
            except DiggerError:
                continue
            if work is not None:
                self._store.set_retraction(ref, work.retracted, now)
                checked += 1
        return checked

    def _retractions(self, user: str, budget: int) -> int:
        watched = self._watched(user)
        for ref, (work, _places) in watched.items():
            if work.retracted:  # ja estava marcado quando foi guardado
                self._store.set_retraction(ref, True, self._clock())
        self.refresh_retractions(set(watched), budget)
        created = 0
        for ref, (retracted, _checked) in self._store.retraction_status(sorted(watched)).items():
            if not retracted:
                continue
            work, places = watched[ref]
            where = " e ".join(places) if len(places) <= 2 else ", ".join(places[:-1]) + f" e {places[-1]}"
            created += self._store.add(user, NewNotification(
                "retratacao", f"retratacao:{ref}", f"Artigo retratado: {work.title}",
                f"A fonte marca este artigo como retratado. Ele está {where}. Confira o aviso de retratação na fonte antes de citá-lo.",
                f"#/artigo?ref={ref}", data={"ref": ref},
            ))
        return created

    # ------------------------------------------------------------------ regulatorio
    def _regulatory(self, user: str) -> int:
        terms = self._reports.substance_terms(user)
        if not terms:
            return 0
        bases = self._bases()
        if bases is None:
            return 0
        created = 0
        for term, report_id, _report_title in terms:
            item = consulta.situacao(term, bases[0], bases[1], rename_data=bases[2])
            fingerprint = regulatory_fingerprint(item)
            stored = self._store.regulatory_fingerprint(user, term)
            self._store.set_regulatory_fingerprint(user, term, json.dumps(fingerprint, ensure_ascii=False, sort_keys=True))
            if stored is None:
                continue  # primeira vez: so memoriza o estado atual
            try:
                old = json.loads(stored)
            except ValueError:
                continue
            lines = describe_regulatory_change(old if isinstance(old, dict) else {}, fingerprint, item)
            if not lines:
                continue
            name = display_name(item)
            created += self._store.add(user, NewNotification(
                "regulatorio", f"regulatorio:{term}:{_digest(fingerprint)}", f"Mudança regulatória: {name}",
                "; ".join(lines) + ". Constar na Rename ou ter registro não significa disponibilidade na unidade de saúde.",
                f"#/relatorio/{report_id}", group_key=f"regulatorio:{term}", data={"term": term, "reportId": report_id},
            ))
        return created

    # ------------------------------------------------------------------ novidades dos relatorios
    def _report_lists(self, user: str) -> int:
        sources = self._reports.sources(user)
        if not sources:
            return 0
        lists = {item.id: item for item in self._library.lists(user)}
        created = 0
        for report_id, title, list_id, present in sources:
            source = lists.get(list_id)
            if source is None:
                continue
            fresh = [work for work in source.works if work.ref not in present]
            if not fresh:
                continue
            count = len(fresh)
            shown = "; ".join(w.title for w in fresh[:LIST_TITLES_SHOWN]) + (f" e mais {count - LIST_TITLES_SHOWN}" if count > LIST_TITLES_SHOWN else "")
            created += self._store.add(user, NewNotification(
                "relatorio-lista", f"relatorio-lista:{report_id}:{_digest(sorted(w.ref for w in fresh))}",
                f"“{title}”: {count} {'artigo novo' if count == 1 else 'artigos novos'} na lista de origem",
                f"Entraram na lista “{source.name}” depois do relatório: {shown}.", f"#/relatorio/{report_id}",
                group_key=f"relatorio-lista:{report_id}", data={"reportId": report_id},
            ))
        return created

    # ------------------------------------------------------------------ orquestracao
    def run(self, user: str, *, force: bool = False, refresh_budget: int = USER_REFRESH_BUDGET) -> WatchResult:
        now = self._clock()
        last = self._store.last_run(user)
        if last is not None and now - last < (MANUAL_INTERVAL if force else AUTO_INTERVAL):
            return WatchResult(False, "intervalo")
        prefs = self._store.prefs(user)
        created: dict[str, int] = {}
        if prefs["retratacao"]:
            created["retratacao"] = self._retractions(user, refresh_budget)
        if prefs["regulatorio"]:
            created["regulatorio"] = self._regulatory(user)
        if prefs["relatorio-lista"]:
            created["relatorio-lista"] = self._report_lists(user)
        self._store.touch(user, now)
        return WatchResult(True, "", {kind: n for kind, n in created.items() if n})

    def run_all(self, *, max_users: int = MAX_USERS_PER_RUN) -> dict[str, int]:
        """Execucao agendada: confere um lote de artigos de todas as contas e depois verifica as contas vencidas."""
        refs = self._library.all_watched_refs() | self._reports.all_watched_refs()
        refreshed = self.refresh_retractions(refs, GLOBAL_REFRESH_BUDGET)
        summary = {"due": 0, "ran": 0, "notified": 0, "failed": 0, "refreshed": refreshed}
        for user in self._store.due_users(self._clock() - AUTO_INTERVAL, max_users):
            summary["due"] += 1
            try:
                result = self.run(user, refresh_budget=0)  # o lote global ja reconferiu os artigos
            except Exception:  # noqa: BLE001 - uma conta com problema nao pode parar as demais
                summary["failed"] += 1
                continue
            summary["ran"] += int(result.ran)
            summary["notified"] += result.total
        return summary
