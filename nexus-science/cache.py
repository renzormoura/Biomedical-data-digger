"""Cache LRU com TTL, thread-safe e com relogio injetavel."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Generic, Optional, TypeVar

V = TypeVar("V")


class TTLCache(Generic[V]):
    def __init__(
        self,
        max_size: int = 128,
        ttl: float = 3600.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_size < 1 or ttl <= 0:
            raise ValueError("max_size >= 1 e ttl > 0 sao obrigatorios.")
        self._max_size = max_size
        self._ttl = ttl
        self._clock = clock
        self._items: OrderedDict[str, tuple[float, V]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[V]:
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            stored_at, value = entry
            if self._clock() - stored_at >= self._ttl:
                del self._items[key]
                return None
            self._items.move_to_end(key)
            return value

    def set(self, key: str, value: V) -> None:
        with self._lock:
            self._items[key] = (self._clock(), value)
            self._items.move_to_end(key)
            while len(self._items) > self._max_size:
                self._items.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


class SingleFlight(Generic[V]):
    """Deduplica execucoes simultaneas da mesma chave (so uma roda, as outras esperam).

    Util para nao pagar duas vezes por uma analise identica pedida ao mesmo tempo.
    O resultado e entregue a todos; um erro tambem e propagado a todos.
    """

    def __init__(self, timeout: float = 180.0) -> None:
        self._timeout = timeout
        self._calls: dict[str, _Call] = {}
        self._lock = threading.Lock()

    def do(self, key: str, fn: Callable[[], V]) -> tuple[V, bool]:
        """Executa `fn` uma vez por chave em voo. Retorna (resultado, foi_o_lider)."""
        with self._lock:
            call = self._calls.get(key)
            leader = call is None
            if call is None:
                call = self._calls[key] = _Call()
        if leader:
            try:
                call.result = fn()
            except BaseException as error:
                call.error = error
            finally:
                with self._lock:
                    del self._calls[key]
                call.event.set()
        elif not call.event.wait(self._timeout):
            raise TimeoutError(f"Execução idêntica excedeu {self._timeout:.0f}s.")
        if call.error is not None:
            raise call.error
        return call.result, leader


class _Call:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.result: Any = None
        self.error: BaseException | None = None
