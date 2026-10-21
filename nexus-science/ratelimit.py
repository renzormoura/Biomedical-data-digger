"""Limitador de taxa por janela deslizante, thread-safe e sem dependencias."""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from typing import Optional


class RateLimitExceeded(RuntimeError):
    def __init__(self, retry_after: float) -> None:
        self.retry_after = retry_after
        super().__init__(f"Limite de requisicoes excedido. Tente novamente em {int(retry_after) + 1}s.")


class SlidingWindowLimiter:
    """Permite no maximo `limit` eventos por chave a cada `window` segundos."""

    def __init__(
        self,
        limit: int,
        window: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        if limit < 1 or window <= 0:
            raise ValueError("limit >= 1 e window > 0 sao obrigatorios.")
        self._limit = limit
        self._window = window
        self._clock = clock
        self._max_keys = max_keys
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str) -> None:
        """Registra um evento ou levanta `RateLimitExceeded`."""
        now = self._clock()
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and now - events[0] >= self._window:
                events.popleft()
            if len(events) >= self._limit:
                raise RateLimitExceeded(self._window - (now - events[0]))
            events.append(now)
            if len(self._events) > self._max_keys:
                self._evict(now)

    def _evict(self, now: float) -> None:
        stale = [k for k, ev in self._events.items() if not ev or now - ev[-1] >= self._window]
        for key in stale:
            del self._events[key]


def client_key(headers: Optional[Mapping[str, str]], peer: Optional[str], trusted_hops: int = 1) -> str:
    """Identifica o cliente atras de proxies confiaveis.

    Com `trusted_hops` proxies na frente, o IP real e a entrada de
    X-Forwarded-For anexada pelo proxy mais externo confiavel (contando do fim);
    entradas a esquerda sao controladas pelo cliente e nao devem ser usadas.
    """
    if headers and trusted_hops > 0:
        forwarded = headers.get("x-forwarded-for", "")
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if len(parts) >= trusted_hops:
            return parts[-trusted_hops]
    return peer or "unknown"
