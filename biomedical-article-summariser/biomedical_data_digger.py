"""Ponto de entrada: monta as dependencias e sobe a interface Gradio."""

from __future__ import annotations

import os

from config import Settings
from llm_service import get_router
from ratelimit import SlidingWindowLimiter
from ui import build_app
from workflow import AnalysisService, ArticleRepository


def create_app():
    settings = Settings.from_env()
    repository = ArticleRepository()
    service = AnalysisService(
        repository=repository,
        generator=get_router(),
        limiter=SlidingWindowLimiter(settings.llm_calls_per_minute, window=60.0),
    )
    return build_app(service, repository, settings)


gradio_ui = create_app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    # Render exige bind em todas as interfaces.
    create_app().launch(server_name="0.0.0.0", server_port=port)  # noqa: S104
