"""Rotas do Laboratorio de IA: analisar, auditar, comparar, extrair (sem IA), citar, busca simples e consumo."""

from __future__ import annotations

import hmac
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic import BaseModel, Field

import article_services
import markdown_lite
import pages
from config import Settings
from domain import (
    ArticleNotFoundError,
    NexusError,
)
from presentation import UNVERIFIABLE_FALLBACK, verification_annex_md
from usage import UsageLog
from workflow import MAX_AUDITED_CHARS, AnalysisService, ArticleRepository, Filters, Reply

MAX_ARTICLE_ID = 2000
MAX_PREVIOUS_RESPONSE = MAX_AUDITED_CHARS  # o que o cliente envia para auditar nao pode passar do que o servidor audita


class FiltersIn(BaseModel):
    publico: str = Field("", max_length=80)
    tom: str = Field("", max_length=80)
    idioma: str = Field("", max_length=80)
    detalhe: str = Field("", max_length=80)
    foco: str = Field("", max_length=80)


class AnalyzeIn(BaseModel):
    page: str = Field(max_length=40)
    button: str = Field(max_length=80)
    article_id: str = Field(max_length=MAX_ARTICLE_ID)
    model: str = Field(max_length=80)
    filters: FiltersIn = Field(default_factory=lambda: FiltersIn(publico="", tom="", idioma="", detalhe="", foco=""))


class AuditIn(BaseModel):
    article_id: str = Field(max_length=MAX_ARTICLE_ID)
    model: str = Field(max_length=80)
    previous: str = Field(max_length=MAX_PREVIOUS_RESPONSE)
    page: str = Field("", max_length=40)


class CompareIn(BaseModel):
    article_a: str = Field(max_length=MAX_ARTICLE_ID)
    article_b: str = Field(max_length=MAX_ARTICLE_ID)
    analysis: str = Field(max_length=80)
    model: str = Field(max_length=80)
    clinical: bool = False
    page: str = Field("", max_length=40)


class ExtractIn(BaseModel):
    page: str = Field(max_length=40)
    button: str = Field(max_length=80)
    article_id: str = Field(max_length=MAX_ARTICLE_ID)


class CiteIn(BaseModel):
    article_id: str = Field(max_length=MAX_ARTICLE_ID)
    style: str = Field(max_length=20)


class SearchIn(BaseModel):
    query: str = Field(max_length=200)
    area: str = Field("Todas", max_length=60)
    limit: int = Field(5, ge=1, le=10)


@dataclass
class LabContext:
    """Dependencias das rotas do Laboratorio."""

    service: AnalysisService
    repository: ArticleRepository
    settings: Settings
    usage_log: UsageLog | None
    page_by_key: dict[str, pages.PageSpec]
    identity: Callable[[Request], str]
    validated_model: Callable[[str], str]
    throttle_auth: Callable[[Request], None]
    search_fn: Callable[..., list[dict]]


def register_lab_routes(app: FastAPI, lab: LabContext) -> None:
    service = lab.service
    repository = lab.repository
    settings = lab.settings
    usage_log = lab.usage_log
    page_by_key = lab.page_by_key
    identity = lab.identity
    validated_model = lab.validated_model
    throttle_auth = lab.throttle_auth
    search_fn = lab.search_fn

    def result(markdown: str, article_id: str = "", reply: Reply | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"markdown": markdown, "html": markdown_lite.render(markdown)}
        if reply is not None:
            payload["meta"] = {
                "cached": reply.cached,
                "tokens": reply.tokens,
                "quota_remaining": reply.quota_remaining,
            }
        if article_id.strip():
            article = repository.peek(article_id)
            if article is not None:
                payload["title"] = article.title
                payload["article_id"] = article_id.strip()
        return payload

    @app.post("/api/analyze")
    def analyze(body: AnalyzeIn, request: Request) -> dict[str, Any]:
        spec = page_by_key.get(body.page)
        button = next((b for b in spec.buttons() if b.id == body.button), None) if spec else None
        if spec is None or button is None:
            raise ArticleNotFoundError("Análise desconhecida.")
        reply = service.analyze(
            body.article_id,
            validated_model(body.model),
            button.builder,
            button.heading,
            Filters(**body.filters.model_dump()),
            client_id=identity(request),
            clinical=spec.clinical,
            check_numbers=button.check_numbers,
            usage_key=f"{spec.key}/{button.id}",
            reasoning_effort=None if spec.clinical else button.reasoning_effort,
            requires=button.requires,
        )
        markdown = str(reply)
        if button.sources:
            try:
                markdown += verification_annex_md(button.sources)
            except Exception:
                logger.warning("Verificacao de fontes indisponivel para {}", button.id)
                markdown += UNVERIFIABLE_FALLBACK
        return result(markdown, body.article_id, reply)

    @app.post("/api/audit")
    def audit(body: AuditIn, request: Request) -> dict[str, Any]:
        reply = service.audit(
            body.article_id, validated_model(body.model), body.previous, client_id=identity(request),
            usage_key=f"{body.page}/audit" if body.page else "audit",
        )
        return result(str(reply), reply=reply)

    @app.post("/api/compare")
    def compare(body: CompareIn, request: Request) -> dict[str, Any]:
        if body.analysis not in pages.COMPARISON_TYPES:
            raise NexusError("Tipo de comparação inválido.")
        reply = service.compare(
            body.article_a, body.article_b, body.analysis, validated_model(body.model),
            medical_context=body.clinical, client_id=identity(request),
            usage_key=f"{body.page}/compare" if body.page else "compare",
        )
        return result(str(reply), reply=reply)

    @app.get("/api/admin/usage")
    def admin_usage(request: Request) -> JSONResponse:
        """Relatorio de consumo de tokens. Desativado (404) sem ADMIN_TOKEN."""
        if not settings.admin_token or usage_log is None:
            return JSONResponse({"error": "Não encontrado."}, status_code=404)
        throttle_auth(request)
        supplied = request.headers.get("authorization", "")
        if not hmac.compare_digest(supplied.encode(), f"Bearer {settings.admin_token}".encode()):
            return JSONResponse({"error": "Não autorizado."}, status_code=401)
        return JSONResponse(usage_log.snapshot())

    @app.post("/api/extract")
    def extract(body: ExtractIn, request: Request) -> dict[str, Any]:
        """Extracao SEM IA: nenhum token e gasto e nenhum texto e gerado."""
        spec = page_by_key.get(body.page)
        button = next((b for b in spec.extract_buttons() if b.id == body.button), None) if spec else None
        if spec is None or button is None:
            raise ArticleNotFoundError("Extração desconhecida.")
        reply = service.extract(
            body.article_id, button.kind, label=button.label, client_id=identity(request), clinical=spec.clinical
        )
        return result(str(reply), body.article_id, reply)

    @app.post("/api/cite")
    def cite(body: CiteIn, request: Request) -> dict[str, Any]:
        return result(service.cite(body.article_id, body.style, client_id=identity(request)))

    @app.post("/api/search")
    def search(body: SearchIn, request: Request) -> dict[str, Any]:
        if not body.query.strip():
            raise NexusError("Informe uma palavra-chave ou tema para buscar artigos relevantes.")
        if body.area not in article_services.AREA_KEYWORDS:
            raise NexusError("Área de foco inválida.")
        try:
            items = search_fn(body.query, limit=body.limit, area=body.area)
        except RuntimeError as error:
            raise NexusError(str(error)) from error
        if not items:
            raise ArticleNotFoundError(
                "Nenhum artigo foi encontrado para esta busca com o filtro selecionado. "
                "Tente outra palavra-chave ou área."
            )
        return {
            "results": [
                {
                    "title": item["title"],
                    "journal": item["journal"],
                    "year": str(item["year"]),
                    "pmid": item["pmid"],
                    "source": item["source"],
                    "url": item["url"] if str(item["url"]).startswith(("http://", "https://")) else "",
                    "doi": item.get("doi", ""),
                    "reliability": item["reliability"],
                    "score": item["reliability_score"],
                }
                for item in items
            ]
        }
