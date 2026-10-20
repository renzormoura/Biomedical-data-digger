"""Tempo em um so lugar: relogio UTC e formato ISO usados por todos os armazens e servicos.

Antes cada modulo tinha a sua copia de `_now`/`_iso`, e uma delas lia a hora da maquina onde o servico deveria usar o
relogio injetado (bug da reconferencia de retratacao). Centralizar deixa um unico ponto para trocar o relogio nos testes
e garante o mesmo formato (`AAAA-MM-DDTHH:MM:SS+00:00`) em toda a base.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

Clock = Callable[[], datetime]
"""Relogio injetavel: devolve o instante atual (com fuso)."""


def utcnow() -> datetime:
    """Instante atual em UTC, com fuso."""
    return datetime.now(timezone.utc)


def utcnow_iso() -> str:
    """Instante atual em UTC como texto ISO 8601, ate os segundos."""
    return iso(utcnow())


def iso(moment: datetime) -> str:
    """`moment` como texto ISO 8601 ate os segundos, sem converter o fuso."""
    return moment.isoformat(timespec="seconds")


def iso_utc(moment: datetime) -> str:
    """Como `iso`, mas convertendo antes para UTC (uso do feed, onde as datas vem de fontes com fusos variados)."""
    return moment.astimezone(timezone.utc).isoformat(timespec="seconds")
