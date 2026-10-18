"""Relatorio de tema: uma entrega pronta a partir de uma lista de leitura, sem IA.

O relatorio *congela* os estudos da lista no momento da criacao (como retrato dos metadados), o autor escolhe quais
entram, escreve uma nota por estudo e uma nota livre no metodo. Tudo o mais e calculado por codigo a partir do registro:
nota de confiabilidade com o detalhe, frases estatisticas copiadas do resumo, panorama (tipo de estudo, ano, idioma,
acesso aberto), referencias e o apendice de metodo. O documento nao conclui nem recomenda: nada foi inventado.
"""

from __future__ import annotations

import contextlib
import json
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from functools import lru_cache

import citations
import reliability
from catalog import Work
from db import Database, Transaction
from discovery import citation_metadata
from domain import LimitReachedError, NotFoundError
from downloads import Block
from extraction import Finding, extract_findings, split_sections

MAX_REPORTS = 30
MAX_ITEMS = 200
MAX_TITLE_CHARS = 200
MAX_QUESTION_CHARS = 2000
MAX_ITEM_NOTE_CHARS = 1000
MAX_METHOD_NOTE_CHARS = 3000
MAX_ABSTRACT_CHARS = 4000
FINDINGS_PER_STUDY = 3
REFERENCE_STYLES = ("ABNT", "APA", "Vancouver")
NO_TYPE = "Tipo de estudo não informado"
NO_LANGUAGE = "Idioma não informado"
LIMITS_NOTE = (
    "A nota de confiabilidade é calculada por código somente com o título, o resumo e os metadados do registro. "
    "Ela indica sinais verificáveis no registro e não substitui a leitura crítica do artigo."
)

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS reports (
        id TEXT PRIMARY KEY, owner_email TEXT NOT NULL, title TEXT NOT NULL, question TEXT NOT NULL,
        method_note TEXT NOT NULL, list_name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
        version INTEGER NOT NULL)""",
    "CREATE INDEX IF NOT EXISTS idx_reports_owner ON reports (owner_email, updated_at)",
    """CREATE TABLE IF NOT EXISTS report_items (
        report_id TEXT NOT NULL REFERENCES reports(id) ON DELETE CASCADE, ref TEXT NOT NULL, data TEXT NOT NULL,
        position INTEGER NOT NULL, included INTEGER NOT NULL, note TEXT NOT NULL, PRIMARY KEY (report_id, ref))""",
)


@dataclass(frozen=True)
class ReportItem:
    work: Work
    included: bool
    note: str


@dataclass(frozen=True)
class Report:
    id: str
    title: str
    question: str
    method_note: str
    list_name: str
    created_at: str
    updated_at: str
    version: int
    items: tuple[ReportItem, ...]

    @property
    def included(self) -> list[ReportItem]:
        return [item for item in self.items if item.included]


@dataclass(frozen=True)
class ReportSummary:
    id: str
    title: str
    list_name: str
    updated_at: str
    version: int
    included: int
    total: int


@dataclass(frozen=True)
class StudyAssessment:
    reliability: reliability.Reliability
    findings: tuple[Finding, ...]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean(text: str, limit: int) -> str:
    """Quebras de linha e paragrafos ficam; caracteres de controle somem."""
    kept = "".join(ch if ch.isprintable() or ch in "\n\t" else " " for ch in str(text))
    return "\n".join(line.rstrip() for line in kept.strip().splitlines())[:limit]


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


class ReportStore:
    def __init__(self, database: Database | None = None) -> None:
        self._db = database or Database()

    def initialize(self) -> None:
        with self._db.transaction() as tx:
            for statement in _SCHEMA:
                tx.execute(statement)

    def _owned(self, tx: Transaction, user: str, report_id: str) -> None:
        if not tx.query("SELECT 1 FROM reports WHERE id = ? AND owner_email = ?", (report_id, user)):
            raise NotFoundError("Relatório não encontrado.")

    def create(self, user: str, *, list_name: str, works: list[Work], title: str = "", question: str = "") -> Report:
        if not works:
            raise NotFoundError("A lista está vazia: adicione artigos antes de criar o relatório.")
        report_id, now = uuid.uuid4().hex, _now()
        clean_title = _clean(title, MAX_TITLE_CHARS) or f"Relatório: {list_name}"[:MAX_TITLE_CHARS]
        with self._db.transaction() as tx:
            if tx.query("SELECT COUNT(*) FROM reports WHERE owner_email = ?", (user,))[0][0] >= MAX_REPORTS:
                raise LimitReachedError(f"Você chegou ao limite de {MAX_REPORTS} relatórios.")
            tx.execute(
                "INSERT INTO reports (id, owner_email, title, question, method_note, list_name, created_at, updated_at, version) "
                "VALUES (?, ?, ?, ?, '', ?, ?, ?, 1)",
                (report_id, user, clean_title, _clean(question, MAX_QUESTION_CHARS), list_name, now, now),
            )
            for position, work in enumerate(works[:MAX_ITEMS]):
                tx.execute(
                    "INSERT INTO report_items (report_id, ref, data, position, included, note) VALUES (?, ?, ?, ?, 1, '') "
                    "ON CONFLICT (report_id, ref) DO NOTHING",
                    (report_id, work.ref, _snapshot(work), position),
                )
        return self.get(user, report_id)

    def get(self, user: str, report_id: str) -> Report:
        rows = self._db.query(
            "SELECT id, title, question, method_note, list_name, created_at, updated_at, version FROM reports "
            "WHERE id = ? AND owner_email = ?", (report_id, user),
        )
        if not rows:
            raise NotFoundError("Relatório não encontrado.")
        item_rows = self._db.query(
            "SELECT data, included, note FROM report_items WHERE report_id = ? ORDER BY position", (report_id,)
        )
        items = tuple(ReportItem(_work(data), bool(included), note) for data, included, note in item_rows)
        rid, title, question, method_note, list_name, created, updated, version = rows[0]
        return Report(rid, title, question, method_note, list_name, created, updated, int(version), items)

    def summaries(self, user: str) -> list[ReportSummary]:
        rows = self._db.query(
            "SELECT r.id, r.title, r.list_name, r.updated_at, r.version, "
            "(SELECT COUNT(*) FROM report_items i WHERE i.report_id = r.id AND i.included = 1), "
            "(SELECT COUNT(*) FROM report_items i WHERE i.report_id = r.id) "
            "FROM reports r WHERE r.owner_email = ? ORDER BY r.updated_at DESC, r.id", (user,),
        )
        return [ReportSummary(*row) for row in rows]

    def update(
        self, user: str, report_id: str, *, title: str, question: str, method_note: str,
        items: list[tuple[str, bool, str]],
    ) -> Report:
        clean_title = _clean(title, MAX_TITLE_CHARS)
        with self._db.transaction() as tx:
            self._owned(tx, user, report_id)
            current = tx.query("SELECT title FROM reports WHERE id = ?", (report_id,))[0][0]
            tx.execute(
                "UPDATE reports SET title = ?, question = ?, method_note = ?, updated_at = ?, version = version + 1 WHERE id = ?",
                (clean_title or current, _clean(question, MAX_QUESTION_CHARS), _clean(method_note, MAX_METHOD_NOTE_CHARS), _now(), report_id),
            )
            for ref, included, note in items:
                tx.execute(
                    "UPDATE report_items SET included = ?, note = ? WHERE report_id = ? AND ref = ?",
                    (1 if included else 0, _clean(note, MAX_ITEM_NOTE_CHARS), report_id, ref),
                )
        return self.get(user, report_id)

    def delete(self, user: str, report_id: str) -> None:
        with self._db.transaction() as tx:
            self._owned(tx, user, report_id)
            tx.execute("DELETE FROM report_items WHERE report_id = ?", (report_id,))
            tx.execute("DELETE FROM reports WHERE id = ?", (report_id,))


# ---------------------------------------------------------------------- calculo (puro, sem rede)
def assess_study(work: Work) -> StudyAssessment:
    sections = tuple(split_sections(work.abstract))
    findings = tuple(extract_findings(work.abstract))
    return StudyAssessment(reliability.assess(work, sections, findings), findings)


def _ranked(counter: Counter[str]) -> list[tuple[str, int]]:
    return sorted(counter.items(), key=lambda pair: (-pair[1], pair[0]))


def panorama(works: list[Work]) -> dict[str, object]:
    """Contagens por tipo de estudo, ano, idioma e fonte, e quantos tem acesso aberto ou foram retratados."""
    types: Counter[str] = Counter()
    for work in works:
        if work.study_types:
            types.update(work.study_types)
        else:
            types[NO_TYPE] += 1
    years = Counter(str(w.year) for w in works if w.year)
    languages = Counter((w.language or "").lower() or NO_LANGUAGE for w in works)
    sources = Counter(w.source or "Fonte não informada" for w in works)
    return {
        "total": len(works),
        "types": _ranked(types),
        "years": sorted(years.items(), reverse=True),
        "languages": _ranked(languages),
        "sources": _ranked(sources),
        "openAccess": sum(1 for w in works if w.open_access),
        "retracted": sum(1 for w in works if w.retracted),
        "withoutAbstract": sum(1 for w in works if not w.abstract),
    }


@lru_cache(maxsize=1)
def criteria_description() -> tuple[tuple[str, int, str], ...]:
    """(nome, peso, como e avaliado) dos criterios da nota de confiabilidade."""
    sample = reliability.assess(Work(ref="x", title="x"))
    return tuple((c.name, c.weight, c.how) for c in sample.criteria)


def method_paragraphs(report: Report, today: date | None = None) -> list[str]:
    """Texto automatico do apendice de metodo: o que foi feito, com contagens e limites, sem adjetivos."""
    today = today or date.today()
    total, included = len(report.items), len(report.included)
    excluded = total - included
    sources = Counter(item.work.source or "fonte não informada" for item in report.items)
    sources_text = ", ".join(f"{name} ({n})" for name, n in sorted(sources.items(), key=lambda pair: (-pair[1], pair[0])))
    created = report.created_at[:10]
    with contextlib.suppress(ValueError):
        created = date.fromisoformat(created).strftime("%d/%m/%Y")
    return [
        f"Os estudos foram reunidos manualmente pelo autor na lista de leitura “{report.list_name}” e congelados neste relatório "
        f"em {created}. As buscas usadas para encontrá-los não são registradas nesta versão do relatório.",
        f"Fontes dos registros: {sources_text}." if sources_text else "",
        f"Foram reunidos {total} estudos; {included} foram incluídos e {excluded} excluídos pelo autor, sem critério automático.",
        "Para cada estudo incluído, a nota de confiabilidade (0 a 100) soma os critérios abaixo, cada um com seu peso; "
        "critérios que não puderam ser verificados no registro ficam fora do cálculo e a cobertura é informada.",
        LIMITS_NOTE,
        "Os dados estatísticos são frases copiadas do resumo, escolhidas por palavras-chave. A seleção pode omitir frases e "
        "foi lido apenas o resumo, não o texto completo.",
        f"Relatório na versão {report.version}, gerado em {today:%d/%m/%Y} pelo Biomedical Data Digger. "
        "Nenhum texto deste relatório foi gerado por IA.",
    ]


def identity_lines(work: Work) -> list[str]:
    lines = [work.author_line]
    journal = ", ".join(p for p in [work.journal, f"v. {work.volume}" if work.volume else "",
                                    f"n. {work.issue}" if work.issue else "", f"p. {work.pages}" if work.pages else ""] if p)
    lines.append(" · ".join(p for p in [journal, str(work.year or "")] if p))
    ids = [f"DOI: https://doi.org/{work.doi}" if work.doi else "", f"PMID: {work.pmid}" if work.pmid else ""]
    lines.append(" · ".join(i for i in ids if i))
    if work.study_types:
        lines.append("Tipo de estudo: " + ", ".join(work.study_types))
    if work.source:
        lines.append(f"Fonte: {work.source}")
    return [line for line in lines if line]


def reliability_line(result: reliability.Reliability) -> str:
    if result.score is None:
        return f"Confiabilidade: {result.band}. {result.summary}"
    return f"Confiabilidade: {result.score}/100 ({result.band}), cobertura de {result.coverage}% dos critérios."


def report_blocks(report: Report, today: date | None = None) -> list[Block]:
    """Documento completo em blocos (vira HTML, DOCX, Markdown ou texto pelo gerador de downloads)."""
    chosen = report.included
    works = [item.work for item in chosen]
    blocks: list[Block] = [("title", report.title), ("meta", f"Relatório de tema · versão {report.version} · {len(chosen)} estudos incluídos")]
    if report.question:
        blocks += [("h1", "Pergunta ou tema"), *[("p", line) for line in report.question.splitlines() if line.strip()]]

    summary = panorama(works)
    blocks.append(("h1", "Panorama dos estudos incluídos"))
    blocks.append(("p", f"{summary['total']} estudos; {summary['openAccess']} com acesso aberto; "
                        f"{summary['retracted']} retratados; {summary['withoutAbstract']} sem resumo no registro."))
    for label, key in (("Tipo de estudo", "types"), ("Ano", "years"), ("Idioma", "languages"), ("Fonte", "sources")):
        pairs = summary[key]
        if pairs:
            blocks.append(("li", f"{label}: " + "; ".join(f"{name} ({n})" for name, n in pairs)))  # type: ignore[attr-defined]

    blocks.append(("h1", "Estudos incluídos"))
    if not chosen:
        blocks.append(("p", "Nenhum estudo foi incluído."))
    for number, item in enumerate(chosen, 1):
        assessment = assess_study(item.work)
        blocks.append(("h2", f"{number}. {item.work.title}"))
        blocks += [("meta", line) for line in identity_lines(item.work)]
        blocks.append(("p", reliability_line(assessment.reliability)))
        blocks += [("meta", warning) for warning in assessment.reliability.warnings]
        blocks += [("quote", f"{' · '.join(f.tags)}: {f.sentence}") for f in assessment.findings[:FINDINGS_PER_STUDY]]
        if item.note:
            blocks.append(("p", f"Nota do autor: {item.note}"))

    blocks.append(("h1", "Referências"))
    for style in REFERENCE_STYLES:
        blocks.append(("h2", style))
        blocks += [("li", citations.format_citation(citation_metadata(w), style)) for w in works] or [("p", "Sem estudos incluídos.")]

    blocks.append(("h1", "Apêndice: método"))
    blocks += [("p", paragraph) for paragraph in method_paragraphs(report, today) if paragraph]
    blocks.append(("h2", "Critérios da nota de confiabilidade"))
    blocks += [("li", f"{name} (peso {weight}): {how}") for name, weight, how in criteria_description()]
    excluded = [item for item in report.items if not item.included]
    if excluded:
        blocks.append(("h2", "Estudos reunidos e excluídos pelo autor"))
        blocks += [("li", f"{item.work.title} ({item.work.year or 's.d.'})" + (f" — {item.note}" if item.note else "")) for item in excluded]
    if report.method_note:
        blocks += [("h2", "Nota do autor sobre o método"), *[("p", line) for line in report.method_note.splitlines() if line.strip()]]
    return blocks
