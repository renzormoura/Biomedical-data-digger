"""Rotas: Descoberta: busca, artigo, semelhantes, enriquecimento, downloads e situacao no Brasil."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import Response

import downloads
import search_overview
from brasil import conitec, consulta
from catalog import SearchQuery, Work
from domain import DiggerError, NotFoundError, SourceUnavailableError
from exports import EXPORT_FORMATS
from routes.context import ApiContext
from routes.payloads import (
    conitec_meta,
    conitec_registro,
    enrichment_payload,
    reliability_payload,
    situacao_payload,
    work_card,
    work_full,
)
from routes.schemas import (
    LANGUAGES,
    MAX_REF,
    PANORAMA_PAGE,
    SORTS,
)


def register_discover_routes(app: FastAPI, ctx: ApiContext) -> None:
    discovery = ctx.discovery
    library = ctx.library
    current_user = ctx.current_user
    identity = ctx.identity
    brasil_bases = ctx.brasil_bases
    brasil_meta = ctx.brasil_meta

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

    @app.get("/api/discover/panorama")
    def search_panorama(
        request: Request,
        q: Annotated[str, Query(max_length=300)] = "",
        yf: Annotated[int | None, Query(ge=1800, le=2100)] = None,
        yt: Annotated[int | None, Query(ge=1800, le=2100)] = None,
        types: Annotated[str, Query(max_length=400)] = "",
        oa: bool = False,
        lang: Annotated[str, Query(max_length=8)] = "",
        sort: Annotated[str, Query(max_length=20)] = "relevance",
        source: Annotated[str | None, Query(max_length=40)] = None,
    ) -> dict[str, Any]:
        """Retrato visual dos primeiros resultados (ate 40) da mesma busca: tipos de estudo, anos, acesso aberto e o estudo de maior nota."""
        works: list[Work] = []
        total = 0
        for page in (1, 2):
            query = SearchQuery(
                q=q, year_from=yf, year_to=yt, study_types=tuple(t.strip() for t in types.split(",") if t.strip()),
                open_access=oa, language=lang, sort=sort, page=page, per_page=PANORAMA_PAGE,
            )
            result = discovery.search(query, source=source or discovery.search_default, client_id=identity(request))
            total = result.total
            works.extend(result.works)
            if page >= result.pages:
                break
        unique = list({(w.doi or w.ref): w for w in works}.values())
        return search_overview.build(unique, total)

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

    @app.get("/api/discover/cite")
    def cite_one(
        request: Request,
        ref: Annotated[str, Query(min_length=1, max_length=MAX_REF)],
        format: Annotated[str, Query(max_length=20)] = "ris",  # noqa: A002 - nome do parametro HTTP
    ) -> Response:
        """Referencia de UM artigo para importar no Zotero, Mendeley ou EndNote. Publica: nao exige conta."""
        if format not in EXPORT_FORMATS or format in ("csv", "json", "resumos"):
            raise DiggerError("Formato de referência inválido.")
        work = discovery.work(ref, client_id=identity(request))
        filename, media_type, build = EXPORT_FORMATS[format]
        return Response(
            build([work]), media_type=f"{media_type}; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="referencia.{filename.rsplit(".", 1)[-1]}"', "Cache-Control": "no-store"},
        )

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
