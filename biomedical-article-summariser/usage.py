"""Registro de consumo de tokens.

`UsageLog` guarda estatisticas agregadas por botao (em memoria, limitadas) e emite
uma linha de log estruturada por chamada. Nenhum conteudo de artigo, resposta ou
identificador de pessoa e registrado: so contagens, modelo, chave do botao e o
tipo do cliente (`user` ou `guest`).

"""

from __future__ import annotations

import json
import math
import threading
import time
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

from loguru import logger

CHARS_PER_TOKEN = 3.6  # aproximacao para texto tecnico em portugues/ingles
MAX_SAMPLES = 500
USER_PREFIX = "u:"


def estimate_tokens(text: str) -> int:
    """Estimativa grosseira usada apenas quando o provedor nao informa o uso."""
    return math.ceil(len(text) / CHARS_PER_TOKEN) if text else 0


def estimate_messages_tokens(messages: Sequence[dict[str, str]]) -> int:
    return estimate_tokens("".join(m.get("content", "") for m in messages))


def client_kind(client_id: str) -> str:
    """`user` para identidades de conta (`u:...`), `guest` para o resto (IP)."""
    return "user" if client_id.startswith(USER_PREFIX) else "guest"


@dataclass(frozen=True)
class UsageRecord:
    key: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cached: bool
    estimated: bool
    latency_ms: int
    client_kind: str

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class _KeyStats:
    calls: int = 0
    cache_hits: int = 0
    estimated_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    samples: deque[int] = field(default_factory=lambda: deque(maxlen=MAX_SAMPLES))


def _p95(values: Sequence[int]) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


class UsageLog:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._since = clock()
        self._stats: dict[str, _KeyStats] = {}
        self._lock = threading.Lock()

    def record(self, record: UsageRecord) -> None:
        with self._lock:
            stats = self._stats.setdefault(record.key, _KeyStats())
            stats.calls += 1
            if record.cached:
                stats.cache_hits += 1
            else:
                stats.prompt_tokens += record.prompt_tokens
                stats.completion_tokens += record.completion_tokens
                stats.samples.append(record.total_tokens)
                if record.estimated:
                    stats.estimated_calls += 1
        logger.info("llm_usage {}", json.dumps(asdict(record), ensure_ascii=False))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            by_key: dict[str, Any] = {}
            totals = {"calls": 0, "cache_hits": 0, "prompt_tokens": 0, "completion_tokens": 0}
            for key, stats in sorted(self._stats.items()):
                paid = stats.calls - stats.cache_hits
                by_key[key] = {
                    "calls": stats.calls,
                    "cache_hits": stats.cache_hits,
                    "cache_hit_rate": round(stats.cache_hits / stats.calls, 3) if stats.calls else 0.0,
                    "prompt_tokens": stats.prompt_tokens,
                    "completion_tokens": stats.completion_tokens,
                    "avg_total_tokens": round((stats.prompt_tokens + stats.completion_tokens) / paid) if paid else 0,
                    "p95_total_tokens": _p95(stats.samples),
                    "estimated_calls": stats.estimated_calls,
                }
                totals["calls"] += stats.calls
                totals["cache_hits"] += stats.cache_hits
                totals["prompt_tokens"] += stats.prompt_tokens
                totals["completion_tokens"] += stats.completion_tokens
            totals["total_tokens"] = totals["prompt_tokens"] + totals["completion_tokens"]
            return {"since": int(self._since), "totals": totals, "by_key": by_key}
