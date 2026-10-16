"""Rotas JSON do navegador de artigos: descoberta, biblioteca, listas e exportacao.

Registradas por `web.create_app`. Descoberta e leitura publica nao exigem conta; salvar,
etiquetar, listar e exportar exigem sessao. Nada aqui chama IA nem gasta token.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

import reliability
from catalog import SearchQuery, Work
from discovery import DiscoveryService
from domain import AuthRequiredError, DiggerError, NotFoundError, RateLimitedError
from exports import EXPORT_FORMATS
from library_store import LibraryStore, ReadingList
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


class ListIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ListItemIn(BaseModel):
    ref: str = Field(min_length=1, max_length=MAX_REF)
    source: str | None = Field(None, max_length=40)


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
) -> None:
    shared_limiter = SlidingWindowLimiter(60, window=60.0)

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
        result = discovery.search(query, source=source, client_id=identity(request))
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
            "similar": [work_card(w) for w in detail.similar],
        }

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
