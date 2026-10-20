"""Rotas: Analises do Laboratorio salvas e exportacao."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import FastAPI, Path, Query, Request
from fastapi.responses import Response

from domain import RateLimitedError
from ratelimit import RateLimitExceeded
from routes.context import ApiContext
from routes.payloads import (
    analysis_file,
    analysis_payload,
)
from routes.schemas import (
    MAX_REF,
    AnalysisIn,
    ExportAnalysisIn,
)


def register_analyses_routes(app: FastAPI, ctx: ApiContext) -> None:
    discovery = ctx.discovery
    library = ctx.library
    identity = ctx.identity
    shared_limiter = ctx.shared_limiter
    require_user = ctx.require_user

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
