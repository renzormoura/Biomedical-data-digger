"""Rotas: Biblioteca, listas de leitura e listas compartilhadas."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import FastAPI, Query, Request
from fastapi.responses import Response

from domain import DiggerError, NotFoundError, RateLimitedError
from exports import EXPORT_FORMATS
from ratelimit import RateLimitExceeded
from routes.context import ApiContext
from routes.payloads import (
    list_payload,
    work_card,
)
from routes.schemas import (
    MAX_REF,
    ListIn,
    ListItemIn,
    RefIn,
    TagsIn,
)


def register_library_routes(app: FastAPI, ctx: ApiContext) -> None:
    discovery = ctx.discovery
    library = ctx.library
    identity = ctx.identity
    shared_limiter = ctx.shared_limiter
    require_user = ctx.require_user

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
