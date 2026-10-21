"""Cotas diarias de tokens por identidade.

Orcamento maior para contas (`u:...`) do que para visitantes (IP). Cache hits nao
consomem cota. Estado em memoria: reinicia com o processo e e por instancia.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from usage import client_kind


class QuotaExceeded(RuntimeError):
    def __init__(self, budget: int) -> None:
        self.budget = budget
        super().__init__(
            f"Cota diária de uso atingida ({budget:,} tokens). Ela renova à 00:00 UTC (21h em Brasília). "
            "Entrar com uma conta aumenta o limite.".replace(",", ".")
        )


class QuotaManager:
    """Orcamento diario de tokens por identidade (0 = sem limite)."""

    def __init__(self, guest_budget: int, user_budget: int, clock: Callable[[], float] = time.time) -> None:
        if guest_budget < 0 or user_budget < 0:
            raise ValueError("Os orcamentos nao podem ser negativos.")
        self._budgets = {"guest": guest_budget, "user": user_budget}
        self._clock = clock
        self._used: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()

    def _today(self) -> int:
        return int(self._clock() // 86400)

    def budget_for(self, client_id: str) -> int:
        return self._budgets[client_kind(client_id)]

    def _used_today(self, client_id: str) -> int:
        day, used = self._used.get(client_id, (self._today(), 0))
        return used if day == self._today() else 0

    def check(self, client_id: str) -> None:
        budget = self.budget_for(client_id)
        if budget == 0:
            return
        with self._lock:
            if self._used_today(client_id) >= budget:
                raise QuotaExceeded(budget)

    def charge(self, client_id: str, tokens: int) -> None:
        if self.budget_for(client_id) == 0 or tokens <= 0:
            return
        with self._lock:
            today = self._today()
            self._used[client_id] = (today, self._used_today(client_id) + tokens)
            if len(self._used) > 10_000:
                self._used = {k: v for k, v in self._used.items() if v[0] == today}

    def remaining(self, client_id: str) -> int | None:
        budget = self.budget_for(client_id)
        if budget == 0:
            return None
        with self._lock:
            return max(0, budget - self._used_today(client_id))
