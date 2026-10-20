"""Dependencias compartilhadas pelas rotas, em um unico objeto (injecao explicita em vez de variaveis de fechamento)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Request

from alerts import AlertService
from brasil import anvisa, conitec, rename
from discovery import DiscoveryService
from domain import AuthRequiredError, RateLimitedError, SourceUnavailableError
from feed import FeedService
from library_store import LibraryStore
from notifications import NotificationService
from profiles import ProfileStore
from ratelimit import RateLimitExceeded, SlidingWindowLimiter
from reports import ReportStore
from routes.payloads import anvisa_meta, conitec_meta, rename_meta

Bases = tuple[anvisa.Instantaneo, conitec.Instantaneo, rename.Instantaneo]


@dataclass
class ApiContext:
    """Servicos e funcoes de identidade que as rotas usam. Servicos opcionais ficam `None` quando o recurso nao existe."""

    discovery: DiscoveryService
    library: LibraryStore
    current_user: Callable[[Request], str | None]
    identity: Callable[[Request], str]
    alerts: AlertService | None = None
    cron_token: str = ""
    reports: ReportStore | None = None
    profiles: ProfileStore | None = None
    notifications: NotificationService | None = None
    feed: FeedService | None = None
    shared_limiter: SlidingWindowLimiter = field(default_factory=lambda: SlidingWindowLimiter(60, window=60.0))
    brasil_limiter: SlidingWindowLimiter = field(default_factory=lambda: SlidingWindowLimiter(120, window=60.0))

    def brasil_bases(self, request: Request) -> Bases:
        try:
            self.brasil_limiter.check(self.identity(request))
        except RateLimitExceeded as error:
            raise RateLimitedError(str(error)) from error
        try:
            return anvisa.carregar(), conitec.carregar(), rename.carregar()
        except (OSError, ValueError, KeyError) as error:
            raise SourceUnavailableError("Os dados oficiais do Brasil não estão disponíveis agora.") from error

    def brasil_meta(self, bases: Bases) -> dict[str, object]:
        return {"anvisa": anvisa_meta(bases[0]), "conitec": conitec_meta(bases[1]), "rename": rename_meta(bases[2])}

    def require_user(self, request: Request) -> str:
        user = self.current_user(request)
        if user is None:
            raise AuthRequiredError("Entre na sua conta para usar a biblioteca e as listas.")
        return user
