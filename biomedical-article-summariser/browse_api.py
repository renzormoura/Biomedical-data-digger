"""Rotas JSON do navegador de artigos: descoberta, biblioteca, listas e exportacao.

Registradas por `web.create_app`. Descoberta e leitura publica nao exigem conta; salvar,
etiquetar, listar e exportar exigem sessao. Nada aqui chama IA nem gasta token.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import FastAPI, Path, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

import downloads
import markdown_lite
import reliability
from alerts import Alert, AlertService
from brasil import anvisa, conitec, consulta, rename
from catalog import SearchQuery, Work
from discovery import DiscoveryService
from domain import AuthRequiredError, DiggerError, NotFoundError, RateLimitedError, SourceUnavailableError
from enrichment import Enrichment
from exports import EXPORT_FORMATS
from interests import catalogo, validar
from library_store import MAX_ANALYSIS_CHARS, LibraryStore, ReadingList, SavedAnalysis
from ratelimit import RateLimitExceeded, SlidingWindowLimiter

SNIPPET_CHARS = 300
LANGUAGES = [("", "Todos"), ("pt", "Português"), ("en", "Inglês"), ("es", "Espanhol")]
SORTS = [("relevance", "Relevância"), ("recent", "Mais recentes"), ("cited", "Mais citados")]
MAX_REF = 300


class RefIn(BaseModel):
    ref: str = Field(min_length=1, max_length=MAX_REF)
    source: str | None = Field(None, max_length=40)


class TagsIn(BaseModel):
    ref: str = Field(min_length=1, max_length=MAX_REF)
    tags: list[Annotated[str, Field(max_length=80)]] = Field(max_length=30)


class TopicIn(BaseModel):
    area: str = Field(min_length=1, max_length=40)
    subtopics: list[Annotated[str, Field(max_length=40)]] = Field(default_factory=list, max_length=40)


class InterestsIn(BaseModel):
    topics: list[TopicIn] = Field(default_factory=list, max_length=40)
    languages: list[Annotated[str, Field(max_length=8)]] = Field(default_factory=list, max_length=12)
    terms: list[Annotated[str, Field(max_length=200)]] = Field(default_factory=list, max_length=20)


class CheckIn(BaseModel):
    force: bool = False


class ReadIn(BaseModel):
    id: str | None = Field(None, max_length=64)  # sem id = todos


class ListIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ListItemIn(BaseModel):
    ref: str = Field(min_length=1, max_length=MAX_REF)
    source: str | None = Field(None, max_length=40)


class AnalysisIn(BaseModel):
    article_id: str = Field(min_length=1, max_length=2000)
    page: str = Field("", max_length=60)
    label: str = Field("Análise", max_length=200)
    markdown: str = Field(min_length=1, max_length=MAX_ANALYSIS_CHARS + 1000)


class ExportAnalysisIn(BaseModel):
    title: str = Field("", max_length=500)
    label: str = Field("Análise", max_length=200)
    markdown: str = Field(min_length=1, max_length=MAX_ANALYSIS_CHARS + 1000)
    format: str = Field("md", max_length=10)


def analysis_payload(item: SavedAnalysis, *, full: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": item.id, "ref": item.ref, "title": item.title, "page": item.page, "label": item.label, "createdAt": item.created_at,
    }
    if full:
        payload["markdown"] = item.markdown
        payload["html"] = markdown_lite.render(item.markdown)  # sanitizado no servidor
    return payload


def analysis_file(article_title: str, label: str, markdown: str, fmt: str) -> Response:
    if fmt not in downloads.TEXT_FORMATS:
        raise DiggerError("Formato de download inválido.")
    content, media = downloads.render(downloads.analysis_blocks(article_title, label, markdown), fmt)
    filename = downloads.analysis_filename(article_title, label, downloads.TEXT_FORMATS[fmt][2])
    return Response(content, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


def conitec_meta(snapshot: conitec.Instantaneo) -> dict[str, Any]:
    days = conitec.dias_desde_extracao(snapshot)
    meta = snapshot.meta
    return {
        "fonte": meta.get("fonte"), "paginaUrl": meta.get("pagina_url"), "arquivoUrl": meta.get("arquivo_url"),
        "extraidoEm": meta.get("extraido_em"), "medicamentos": meta.get("linhas_medicamento"), "dias": days,
        "defasado": days is None or days > conitec.STALE_AFTER_DAYS,
    }


def anvisa_meta(snapshot: anvisa.Instantaneo) -> dict[str, Any]:
    days = anvisa.dias_desde_extracao(snapshot)
    meta = snapshot.meta
    return {
        "fonte": meta.get("fonte"), "arquivoUrl": meta.get("arquivo_url"), "dicionarioUrl": meta.get("dicionario_url"),
        "arquivoModificado": meta.get("arquivo_modificado"), "extraidoEm": meta.get("extraido_em"),
        "substancias": meta.get("substancias"), "dias": days, "defasado": days is None or days > anvisa.STALE_AFTER_DAYS,
    }


def anvisa_substancia(item: anvisa.Substancia) -> dict[str, Any]:
    return {
        "name": item.nome, "key": item.chave, "active": item.ativos, "inactive": item.inativos, "activeAlone": item.ativos_isolado,
        "categories": item.categorias, "classes": list(item.classes), "companies": item.empresas, "validUntil": item.validade_max,
    }


def rename_meta(snapshot: rename.Instantaneo) -> dict[str, Any]:
    days = rename.dias_desde_extracao(snapshot)
    meta = snapshot.meta
    return {
        "fonte": meta.get("fonte"), "arquivoUrl": meta.get("url"), "licenca": meta.get("licenca"), "extraidoEm": meta.get("extraido_em"),
        "substancias": meta.get("substancias"), "dias": days, "defasado": days is None or days > rename.STALE_AFTER_DAYS,
    }


def rename_registro(item: rename.Registro) -> dict[str, Any]:
    return {
        "name": item.nome, "key": item.chave, "components": list(item.componentes), "atc": list(item.atc),
        "presentations": [{"text": a.texto, "component": a.componente, "atc": a.atc, "page": a.pagina} for a in item.apresentacoes[: rename.MAX_PRESENTATIONS]],
        "totalPresentations": len(item.apresentacoes),
    }


def situacao_payload(item: consulta.Situacao) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "anvisa": [anvisa_substancia(s) for s in item.anvisa], "conitec": [conitec_registro(r) for r in item.conitec],
        "rename": [rename_registro(r) for r in item.rename],
    }
    if item.candidato is not None:
        payload.update({"pt": item.candidato.pt, "en": item.candidato.en, "metodo": item.candidato.metodo})
    return payload


def conitec_registro(item: conitec.Registro) -> dict[str, Any]:
    return {
        "year": item.ano, "technology": item.tecnologia, "indication": item.indicacao, "recommendation": item.recomendacao,
        "decisionMs": item.decisao_ms, "ordinance": item.portaria, "publishedAt": item.data_publicacao,
        "technicalReport": item.relatorio_tecnico, "societyReport": item.relatorio_sociedade,
    }


def work_card(work: Work, saved: bool | None = None) -> dict[str, Any]:
    snippet = work.abstract[:SNIPPET_CHARS] + ("…" if len(work.abstract) > SNIPPET_CHARS else "")
    card: dict[str, Any] = {
        "ref": work.ref, "title": work.title, "authors": work.author_line, "journal": work.journal, "year": work.year,
        "doi": work.doi, "pmid": work.pmid, "studyTypes": list(work.study_types), "openAccess": work.open_access,
        "oaUrl": work.oa_url, "citedBy": work.cited_by, "language": work.language, "source": work.source,
        "snippet": snippet, "keywords": list(work.keywords),
    }
    if saved is not None:
        card["saved"] = saved
    return card


def work_full(work: Work, saved: bool | None = None) -> dict[str, Any]:
    full = work_card(work, saved)
    full.update({
        "abstract": work.abstract, "volume": work.volume, "issue": work.issue, "pages": work.pages, "pmcid": work.pmcid,
        "authorList": [{"family": a.family, "given": a.given} for a in work.authors],
    })
    return full


def reliability_payload(result: reliability.Reliability) -> dict[str, Any]:
    return {
        "score": result.score, "band": result.band, "coverage": result.coverage, "summary": result.summary,
        "warnings": list(result.warnings), "disclaimer": result.disclaimer,
        "criteria": [
            {"key": c.key, "name": c.name, "weight": c.weight, "status": c.status, "points": c.points,
             "detail": c.detail, "evidence": c.evidence, "how": c.how}
            for c in result.criteria
        ],
    }


def enrichment_payload(result: Enrichment) -> dict[str, Any]:
    return {
        "mentionedTrials": list(result.mentioned_trials),
        "trials": [
            {"nct": t.nct, "title": t.title, "status": t.status, "start": t.start, "hasResults": t.has_results, "url": t.url}
            for t in result.trials
        ],
        "citations": result.citations,
        "relatedData": [{"doi": d.doi, "title": d.title, "kind": d.kind, "publisher": d.publisher, "url": d.url} for d in result.related_data],
    }


def list_payload(reading_list: ReadingList) -> dict[str, Any]:
    return {
        "id": reading_list.id, "name": reading_list.name, "shareToken": reading_list.share_token,
        "createdAt": reading_list.created_at, "works": [work_card(w, saved=None) for w in reading_list.works],
    }


def register_browse_routes(
    app: FastAPI,
    *,
    discovery: DiscoveryService,
    library: LibraryStore,
    current_user: Callable[[Request], str | None],
    identity: Callable[[Request], str],
    alerts: AlertService | None = None,
) -> None:
    shared_limiter = SlidingWindowLimiter(60, window=60.0)
    brasil_limiter = SlidingWindowLimiter(120, window=60.0)

    def brasil_bases(request: Request) -> tuple[anvisa.Instantaneo, conitec.Instantaneo, rename.Instantaneo]:
        try:
            brasil_limiter.check(identity(request))
        except RateLimitExceeded as error:
            raise RateLimitedError(str(error)) from error
        try:
            return anvisa.carregar(), conitec.carregar(), rename.carregar()
        except (OSError, ValueError, KeyError) as error:
            raise SourceUnavailableError("Os dados oficiais do Brasil não estão disponíveis agora.") from error

    def brasil_meta(bases: tuple[anvisa.Instantaneo, conitec.Instantaneo, rename.Instantaneo]) -> dict[str, Any]:
        return {"anvisa": anvisa_meta(bases[0]), "conitec": conitec_meta(bases[1]), "rename": rename_meta(bases[2])}

    def require_user(request: Request) -> str:
        user = current_user(request)
        if user is None:
            raise AuthRequiredError("Entre na sua conta para usar a biblioteca e as listas.")
        return user

    # -- descoberta ------------------------------------------------------------
    @app.get("/api/discover/options")
    def options() -> dict[str, Any]:
        return {
            "sources": discovery.sources(),
            "languages": [{"id": i, "name": n} for i, n in LANGUAGES],
            "sorts": [{"id": i, "name": n} for i, n in SORTS],
        }

    @app.get("/api/discover/search")
    def search(
        request: Request,
        q: Annotated[str, Query(max_length=300)] = "",
        yf: Annotated[int | None, Query(ge=1800, le=2100)] = None,
        yt: Annotated[int | None, Query(ge=1800, le=2100)] = None,
        types: Annotated[str, Query(max_length=400)] = "",
        oa: bool = False,
        lang: Annotated[str, Query(max_length=8)] = "",
        sort: Annotated[str, Query(max_length=20)] = "relevance",
        page: Annotated[int, Query(ge=1, le=500)] = 1,
        per_page: Annotated[int, Query(ge=1, le=20)] = 10,
        source: Annotated[str | None, Query(max_length=40)] = None,
    ) -> dict[str, Any]:
        query = SearchQuery(
            q=q, year_from=yf, year_to=yt, study_types=tuple(t.strip() for t in types.split(",") if t.strip()),
            open_access=oa, language=lang, sort=sort, page=page, per_page=per_page,
        )
        result = discovery.search(query, source=source or discovery.search_default, client_id=identity(request))
        user = current_user(request)
        saved = library.saved_refs(user, [w.ref for w in result.works]) if user else None
        return {
            "works": [work_card(w, None if saved is None else w.ref in saved) for w in result.works],
            "total": result.total, "page": result.page, "pages": result.pages, "perPage": result.per_page,
            "source": result.source, "notes": list(result.notes),
        }

    @app.get("/api/discover/work")
    def work(
        request: Request,
        ref: Annotated[str, Query(min_length=1, max_length=MAX_REF)],
        source: Annotated[str | None, Query(max_length=40)] = None,
    ) -> dict[str, Any]:
        detail = discovery.detail(ref, source=source, client_id=identity(request))
        user = current_user(request)
        saved = library.saved_refs(user, [detail.work.ref]) if user else None
        return {
            "work": work_full(detail.work, None if saved is None else detail.work.ref in saved),
            "sections": [{"heading": s.heading, "label": s.label, "text": s.text} for s in detail.sections],
            "findings": [{"sentence": f.sentence, "tags": list(f.tags)} for f in detail.findings],
            "citations": dict(detail.citations),
            "reliability": reliability_payload(detail.reliability),
        }

    @app.get("/api/discover/brief")
    def brief(
        request: Request,
        ref: Annotated[str, Query(min_length=1, max_length=2000)],
    ) -> dict[str, Any]:
        """Cartao resumido do artigo (para o Laboratorio mostrar qual artigo esta carregado)."""
        detail = discovery.analysis(ref, client_id=identity(request))
        scored = detail.reliability
        return {
            "work": work_card(detail.work),
            "reliability": {"score": scored.score, "band": scored.band, "coverage": scored.coverage},
        }

    @app.get("/api/brasil/conitec")
    def brasil_conitec(request: Request, q: Annotated[str, Query(min_length=3, max_length=80)]) -> dict[str, Any]:
        """Decisoes da Conitec para um medicamento (nome em portugues). Instantaneo local, sem rede e sem IA."""
        bases = brasil_bases(request)
        return {"consulta": q, "registros": [conitec_registro(r) for r in conitec.buscar(q, instantaneo=bases[1])],
                "meta": conitec_meta(bases[1])}

    @app.get("/api/brasil/medicamento")
    def brasil_medicamento(request: Request, q: Annotated[str, Query(min_length=3, max_length=80)]) -> dict[str, Any]:
        """Registro na ANVISA e decisoes da Conitec para um medicamento (nome em portugues), sem IA e sem rede."""
        bases = brasil_bases(request)
        found = consulta.situacao(consulta.normalizar_termo(q), bases[0], bases[1], rename_data=bases[2])
        return {"consulta": q, **situacao_payload(found), "meta": brasil_meta(bases)}

    @app.get("/api/discover/brasil")
    def brasil_artigo(request: Request, ref: Annotated[str, Query(min_length=1, max_length=MAX_REF)]) -> dict[str, Any]:
        """Medicamentos que o resumo parece citar, com registro na ANVISA e decisoes da Conitec (a confirmar)."""
        bases = brasil_bases(request)
        work = discovery.work(ref, client_id=identity(request))
        found = consulta.situacoes_do_texto(f"{work.title}. {work.abstract}", bases[0], bases[1], bases[2])
        return {"candidatos": [situacao_payload(item) for item in found], "meta": brasil_meta(bases)}

    @app.get("/api/discover/similar")
    def similar_route(
        request: Request,
        ref: Annotated[str, Query(min_length=1, max_length=MAX_REF)],
    ) -> dict[str, Any]:
        client = identity(request)
        work = discovery.work(ref, client_id=client)
        found = discovery.similar(work, client_id=client)
        user = current_user(request)
        saved = library.saved_refs(user, [w.ref for w in found]) if user and found else None
        return {
            "terms": discovery.similar_terms(work),
            "works": [work_card(w, None if saved is None else w.ref in saved) for w in found],
        }

    @app.get("/api/discover/enrichment")
    def enrichment_route(
        request: Request,
        ref: Annotated[str, Query(min_length=1, max_length=MAX_REF)],
    ) -> dict[str, Any]:
        return enrichment_payload(discovery.enrich(ref, client_id=identity(request)))

    @app.get("/api/discover/downloads")
    def downloads_menu(
        request: Request,
        ref: Annotated[str, Query(min_length=1, max_length=MAX_REF)],
    ) -> dict[str, Any]:
        client = identity(request)
        work = discovery.work(ref, client_id=client)
        note = ""
        try:
            fulltext = discovery.fulltext(ref, client_id=client)
            if fulltext is None:
                note = "Sem texto completo aberto na Europe PMC para este artigo."
        except SourceUnavailableError as error:
            fulltext, note = None, str(error)
        return downloads.menu(work, fulltext, note)

    @app.get("/api/discover/download")
    def download(
        request: Request,
        ref: Annotated[str, Query(min_length=1, max_length=MAX_REF)],
        kind: Annotated[str, Query(max_length=20)] = "abstract",
        format: Annotated[str, Query(max_length=20)] = "txt",  # noqa: A002 - nome do parametro HTTP
    ) -> Response:
        client = identity(request)
        valid = downloads.CITATION_FORMATS if kind == "citation" else downloads.KIND_FORMATS.get(kind)
        if valid is None or format not in valid:
            raise DiggerError("Tipo ou formato de download inválido.")
        if kind == "citation":
            work = discovery.work(ref, client_id=client)
            ext = EXPORT_FORMATS[format][0].rsplit(".", 1)[-1]
            content, media = EXPORT_FORMATS[format][2]([work]).encode("utf-8"), f"{EXPORT_FORMATS[format][1]}; charset=utf-8"
            filename = downloads.safe_filename(work, f"referencia-{format}", ext)
        elif kind == "fulltext":
            work = discovery.work(ref, client_id=client)
            fulltext = discovery.fulltext(ref, client_id=client)
            if fulltext is None:
                raise NotFoundError("Este artigo não tem texto completo aberto disponível.")
            if format == "xml":
                content, media, ext = fulltext.xml, "application/xml", "xml"
            else:
                content, media = downloads.render(downloads.fulltext_blocks(work, fulltext), format)
                ext = format
            filename = downloads.safe_filename(work, "texto-completo", ext)
        else:
            detail = discovery.analysis(ref, client_id=client)
            work = detail.work
            sections = [(s.heading, s.text) for s in detail.sections]
            if kind == "abstract":
                blocks = downloads.abstract_blocks(work, sections)
                payload: dict[str, object] = {"work": work.to_dict(), "sections": [{"heading": h, "text": t} for h, t in sections]}
            else:
                cached = discovery.cached_enrichment(ref, client_id=client)
                extra = enrichment_payload(cached) if cached else None
                findings = [(", ".join(f.tags), f.sentence) for f in detail.findings]
                scored = reliability_payload(detail.reliability)
                blocks = downloads.sheet_blocks(work, sections, findings, scored, dict(detail.citations), extra)
                payload = {
                    "work": work.to_dict(), "sections": [{"heading": h, "text": t} for h, t in sections],
                    "findings": [{"tags": list(f.tags), "sentence": f.sentence} for f in detail.findings],
                    "reliability": scored, "citations": dict(detail.citations), "registryAndData": extra,
                }
            if format == "json":
                content, media, ext = downloads.to_json_bytes(payload), "application/json", "json"
            else:
                content, media = downloads.render(blocks, format)
                ext = format
            filename = downloads.safe_filename(work, "resumo" if kind == "abstract" else "ficha", ext)
        return Response(content, media_type=media, headers={
            "Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        })

    # -- analises do Laboratorio ----------------------------------------------------
    @app.post("/api/export/analysis")
    def export_analysis(body: ExportAnalysisIn, request: Request) -> Response:
        try:
            shared_limiter.check(identity(request))
        except RateLimitExceeded as error:
            raise RateLimitedError(str(error)) from error
        return analysis_file(body.title, body.label, body.markdown, body.format)

    @app.post("/api/analyses")
    def save_analysis(body: AnalysisIn, request: Request) -> dict[str, Any]:
        user = require_user(request)
        work = discovery.work(body.article_id, client_id=identity(request))
        return analysis_payload(library.save_analysis(user, work, body.page, body.label, body.markdown))

    @app.get("/api/analyses")
    def list_analyses(request: Request, ref: Annotated[str | None, Query(max_length=MAX_REF)] = None) -> dict[str, Any]:
        user = require_user(request)
        return {"analyses": [analysis_payload(a) for a in library.analyses(user, ref)]}

    @app.get("/api/analyses/{analysis_id}")
    def get_analysis(analysis_id: Annotated[str, Path(max_length=64)], request: Request) -> dict[str, Any]:
        return analysis_payload(library.get_analysis(require_user(request), analysis_id), full=True)

    @app.get("/api/analyses/{analysis_id}/download")
    def download_analysis(
        analysis_id: Annotated[str, Path(max_length=64)], request: Request,
        format: Annotated[str, Query(max_length=10)] = "md",  # noqa: A002 - nome do parametro HTTP
    ) -> Response:
        item = library.get_analysis(require_user(request), analysis_id)
        return analysis_file(item.title, item.label, item.markdown, format)

    @app.delete("/api/analyses/{analysis_id}")
    def delete_analysis(analysis_id: Annotated[str, Path(max_length=64)], request: Request) -> dict[str, bool]:
        library.delete_analysis(require_user(request), analysis_id)
        return {"ok": True}

    # -- interesses e alertas -------------------------------------------------------
    if alerts is not None:
        alert_service = alerts

        def alert_payload(item: Alert) -> dict[str, Any]:
            return {"id": item.id, "topic": item.topic, "createdAt": item.created_at, "read": item.read, "work": work_card(item.work)}

        def box(user: str) -> dict[str, Any]:
            return {"unread": alert_service.store.unread(user), "alerts": [alert_payload(a) for a in alert_service.store.alerts(user)]}

        @app.get("/api/interests/options")
        def interest_options() -> dict[str, Any]:
            return catalogo()

        @app.get("/api/interests")
        def get_interests(request: Request) -> dict[str, Any]:
            prefs, checked = alert_service.store.preferences(require_user(request))
            return {**prefs.to_dict(), "lastChecked": checked.isoformat(timespec="seconds") if checked else None}

        @app.put("/api/interests")
        def put_interests(body: InterestsIn, request: Request) -> dict[str, Any]:
            user = require_user(request)
            prefs = validar([t.model_dump() for t in body.topics], body.languages, body.terms)
            alert_service.store.set_preferences(user, prefs)
            return prefs.to_dict()

        @app.get("/api/alerts")
        def get_alerts(request: Request) -> dict[str, Any]:
            return box(require_user(request))

        @app.post("/api/alerts/check")
        def check_alerts(body: CheckIn, request: Request) -> dict[str, Any]:
            user = require_user(request)
            result = alert_service.check(user, force=body.force)
            return {
                "ran": result.ran, "new": result.new, "reason": result.reason, "baseline": result.baseline,
                "notes": list(result.notes), **box(user),
            }

        @app.post("/api/alerts/read")
        def read_alerts(body: ReadIn, request: Request) -> dict[str, Any]:
            user = require_user(request)
            alert_service.store.mark_read(user, body.id)
            return box(user)

        @app.delete("/api/alerts")
        def dismiss_alert(request: Request, id: Annotated[str, Query(min_length=1, max_length=64)]) -> dict[str, Any]:  # noqa: A002
            user = require_user(request)
            alert_service.store.dismiss(user, id)
            return box(user)

    # -- biblioteca ---------------------------------------------------------------
    @app.get("/api/library")
    def get_library(request: Request) -> dict[str, Any]:
        user = require_user(request)
        return {
            "items": [
                {**work_card(item.work, saved=True), "tags": list(item.tags), "savedAt": item.saved_at}
                for item in library.items(user)
            ],
            "lists": [list_payload(item) for item in library.lists(user)],
        }

    @app.post("/api/library")
    def save_to_library(body: RefIn, request: Request) -> dict[str, Any]:
        user = require_user(request)
        library.save(user, discovery.work(body.ref, source=body.source, client_id=identity(request)))
        return {"saved": True}

    @app.delete("/api/library")
    def remove_from_library(
        request: Request, ref: Annotated[str, Query(min_length=1, max_length=MAX_REF)]
    ) -> dict[str, Any]:
        library.remove(require_user(request), ref)
        return {"saved": False}

    @app.put("/api/library/tags")
    def set_tags(body: TagsIn, request: Request) -> dict[str, Any]:
        return {"tags": list(library.set_tags(require_user(request), body.ref, body.tags))}

    @app.get("/api/library/export")
    def export(
        request: Request,
        format: Annotated[str, Query(max_length=20)] = "bibtex",  # noqa: A002 - nome do parametro HTTP
        list_id: Annotated[str | None, Query(max_length=64)] = None,
    ) -> Response:
        user = require_user(request)
        if format not in EXPORT_FORMATS:
            raise DiggerError("Formato de exportação inválido.")
        if list_id:
            chosen = next((item for item in library.lists(user) if item.id == list_id), None)
            if chosen is None:
                raise NotFoundError("Lista não encontrada.")
            works = list(chosen.works)
        else:
            works = [item.work for item in library.items(user)]
        filename, media_type, build = EXPORT_FORMATS[format]
        return Response(
            build(works), media_type=f"{media_type}; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"', "Cache-Control": "no-store"},
        )

    # -- listas -----------------------------------------------------------------------
    @app.get("/api/lists")
    def get_lists(request: Request) -> dict[str, Any]:
        return {"lists": [list_payload(item) for item in library.lists(require_user(request))]}

    @app.post("/api/lists")
    def create_list(body: ListIn, request: Request) -> dict[str, Any]:
        return list_payload(library.create_list(require_user(request), body.name))

    @app.delete("/api/lists/{list_id}")
    def delete_list(list_id: str, request: Request) -> dict[str, Any]:
        library.delete_list(require_user(request), list_id)
        return {"deleted": True}

    @app.post("/api/lists/{list_id}/items")
    def add_to_list(list_id: str, body: ListItemIn, request: Request) -> dict[str, Any]:
        user = require_user(request)
        library.add_to_list(user, list_id, discovery.work(body.ref, source=body.source, client_id=identity(request)))
        return {"added": True}

    @app.delete("/api/lists/{list_id}/items")
    def remove_from_list(
        list_id: str, request: Request, ref: Annotated[str, Query(min_length=1, max_length=MAX_REF)]
    ) -> dict[str, Any]:
        library.remove_from_list(require_user(request), list_id, ref)
        return {"removed": True}

    @app.post("/api/lists/{list_id}/share")
    def share_list(list_id: str, request: Request) -> dict[str, Any]:
        token = library.share(require_user(request), list_id)
        return {"token": token, "path": f"/#/lista/{token}"}

    @app.delete("/api/lists/{list_id}/share")
    def unshare_list(list_id: str, request: Request) -> dict[str, Any]:
        library.unshare(require_user(request), list_id)
        return {"shared": False}

    @app.get("/api/shared/{token}")
    def shared(token: str, request: Request) -> dict[str, Any]:
        """Lista publica somente leitura. Limite por identidade contra tentativa de adivinhar tokens."""
        try:
            shared_limiter.check(identity(request))
        except RateLimitExceeded as error:
            raise RateLimitedError(str(error)) from error
        found = library.shared(token)
        if found is None:
            raise NotFoundError("Lista não encontrada ou o link foi desativado.")
        return {"name": found.name, "works": [work_card(w) for w in found.works]}
