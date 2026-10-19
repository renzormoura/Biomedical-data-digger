"""Panorama do tema: um retrato visual dos primeiros resultados de uma busca (tipos de estudo, anos, acesso aberto, fontes).

Sem IA e sem nova consulta: so conta o que o registro de cada artigo ja informa e escolhe o estudo de maior nota de confiabilidade.
Os numeros descrevem a **amostra** (os primeiros resultados por relevancia), nao o total da fonte; a tela diz isso.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from typing import Any

import reliability
from catalog import Work
from extraction import extract_findings, split_sections

MAX_YEARS = 20

# (chave, rotulo, tipos de estudo do registro que entram no grupo); o primeiro grupo que casar vence
GROUPS: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("preprint", "Preprints (sem revisão por pares)", frozenset({"Preprint"})),
    ("sistematica", "Revisões sistemáticas e meta-análises", frozenset({"Revisão sistemática", "Meta-análise"})),
    ("ensaio", "Ensaios clínicos", frozenset({"Ensaio clínico randomizado", "Ensaio clínico controlado", "Ensaio clínico"})),
    ("observacional", "Estudos observacionais e comparativos", frozenset({"Estudo observacional", "Estudo multicêntrico", "Estudo comparativo"})),
    ("revisao", "Revisões narrativas e diretrizes", frozenset({"Revisão", "Diretriz de prática clínica", "Diretriz"})),
    ("opiniao", "Relatos de caso e opinião", frozenset({"Relato de caso", "Carta", "Editorial", "Comentário"})),
)
UNKNOWN_KEY, UNKNOWN_LABEL = "desconhecido", "Tipo de estudo não informado"


def group_of(work: Work) -> str:
    types = set(work.study_types)
    for key, _, members in GROUPS:
        if types & members:
            return key
    return UNKNOWN_KEY


def _score(work: Work) -> reliability.Reliability:
    return reliability.assess(work, tuple(split_sections(work.abstract)), tuple(extract_findings(work.abstract)))


def build(works: Sequence[Work], total: int) -> dict[str, Any]:
    """Resumo visual de `works` (a amostra); `total` e o que a busca diz ter no todo."""
    sample = len(works)
    counts = Counter(group_of(work) for work in works)
    designs = [{"key": key, "label": label, "count": counts[key]} for key, label, _ in GROUPS if counts[key]]
    if counts[UNKNOWN_KEY]:
        designs.append({"key": UNKNOWN_KEY, "label": UNKNOWN_LABEL, "count": counts[UNKNOWN_KEY]})

    years = Counter(work.year for work in works if work.year)
    top_year = max(years) if years else 0
    timeline = [{"year": year, "count": years.get(year, 0)} for year in range(max(min(years, default=top_year), top_year - MAX_YEARS + 1), top_year + 1)] if years else []

    sources = Counter(work.source or "Outras" for work in works)
    scored = [(work, _score(work)) for work in works if not work.retracted and work.abstract]
    best_work, best = max(scored, key=lambda pair: (pair[1].score, pair[0].cited_by or 0), default=(None, None))
    strongest = None
    if best_work is not None and best is not None:
        strongest = {
            "ref": best_work.ref, "title": best_work.title, "authors": best_work.author_line, "journal": best_work.journal,
            "year": best_work.year, "score": best.score, "band": best.band, "source": best_work.source,
            "design": next((label for key, label, _ in GROUPS if key == group_of(best_work)), UNKNOWN_LABEL),
        }
    return {
        "sample": sample, "total": total, "designs": designs, "timeline": timeline,
        "openAccess": sum(1 for work in works if work.open_access),
        "sources": [{"name": name, "count": count} for name, count in sources.most_common()],
        "retracted": sum(1 for work in works if work.retracted), "strongest": strongest,
    }
