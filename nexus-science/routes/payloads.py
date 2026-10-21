"""Montagem dos objetos JSON devolvidos pelas rotas (cartoes de artigo, notas, bases do Brasil...)."""

from __future__ import annotations

from typing import Any

from fastapi.responses import Response

import downloads
import markdown_lite
import reliability
from brasil import anvisa, conitec, consulta, rename
from catalog import Work
from domain import NexusError
from enrichment import Enrichment
from library_store import ReadingList, SavedAnalysis
from routes.schemas import SNIPPET_CHARS


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
        raise NexusError("Formato de download inválido.")
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
        "authorList": [{"family": a.family, "given": a.given} for a in work.authors], "published": work.published,
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

