"""Ponto de entrada: monta as dependencias e sobe o servidor web."""

from __future__ import annotations

import os

import uvicorn

from config import Settings
from llm_service import get_router
from ratelimit import SlidingWindowLimiter
from web import create_app as create_web_app
from workflow import AnalysisService, ArticleRepository


def create_app():  # type: ignore[no-untyped-def]
    settings = Settings.from_env()
    repository = ArticleRepository()
    service = AnalysisService(
        repository=repository,
        generator=get_router(),
        limiter=SlidingWindowLimiter(settings.llm_calls_per_minute, window=60.0),
    )
    return create_web_app(service, repository, settings)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    # Render exige bind em todas as interfaces.
    uvicorn.run(create_app(), host="0.0.0.0", port=port, log_level="info")  # noqa: S104
