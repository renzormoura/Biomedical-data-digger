"""Modelos de entrada (Pydantic) e constantes compartilhadas das rotas."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from library_store import MAX_ANALYSIS_CHARS

PANORAMA_PAGE = 20
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


class ReportCreateIn(BaseModel):
    list_id: str = Field(min_length=1, max_length=64)
    title: str = Field("", max_length=300)
    question: str = Field("", max_length=4000)


class NotificationPrefsIn(BaseModel):
    kinds: dict[Annotated[str, Field(max_length=40)], bool] = Field(default_factory=dict, max_length=20)


class ProfileIn(BaseModel):
    profile: str = Field(min_length=1, max_length=40)
    health_pack: bool | None = Field(None, alias="healthPack")  # ausente = padrao do perfil

    model_config = {"populate_by_name": True}


class ReportSearchIn(BaseModel):
    query: str = Field(min_length=2, max_length=200)
    language: str = Field("", max_length=8)
    year_from: int | None = Field(None, ge=1800, le=2100, alias="yearFrom")

    model_config = {"populate_by_name": True}


class ReportAddIn(BaseModel):
    refs: list[Annotated[str, Field(min_length=1, max_length=MAX_REF)]] = Field(min_length=1, max_length=50)
    origin: str = Field(pattern="^(lista|busca)$")
    query: str = Field("", max_length=200)


class ReportRestoreIn(BaseModel):
    version: int = Field(ge=1, le=100000)


class ReportItemIn(BaseModel):
    ref: str = Field(min_length=1, max_length=MAX_REF)
    included: bool = True
    note: str = Field("", max_length=2000)


class ReportUpdateIn(BaseModel):
    title: str = Field("", max_length=300)
    question: str = Field("", max_length=4000)
    method_note: str = Field("", max_length=6000, alias="methodNote")
    items: list[ReportItemIn] = Field(default_factory=list, max_length=300)
    substances: list[Annotated[str, Field(max_length=120)]] | None = Field(None, max_length=30)

    model_config = {"populate_by_name": True}


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

