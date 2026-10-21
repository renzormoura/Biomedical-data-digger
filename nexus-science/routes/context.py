"""Dependencias compartilhadas pelas rotas, em um unico objeto (injecao explicita em vez de variaveis de fechamento)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Request

import plans
from account_flags import AccountFlags
from admin_service import AdminService
from alerts import AlertService
from billing import BillingStore
from brasil import anvisa, conitec, rename, sigtap
from config import Settings
from discovery import DiscoveryService
from domain import AuthRequiredError, LimitReachedError, RateLimitedError, SourceUnavailableError
from feed import FeedService
from library_store import LibraryStore
from mailer import Mailer
from notifications import NotificationService
from profiles import ProfileStore
from ratelimit import RateLimitExceeded, SlidingWindowLimiter
from reports import ReportStore
from routes.payloads import anvisa_meta, conitec_meta, rename_meta, sigtap_meta

Bases = tuple[anvisa.Instantaneo, conitec.Instantaneo, rename.Instantaneo]
SusBases = tuple[anvisa.Instantaneo, conitec.Instantaneo, rename.Instantaneo, sigtap.Instantaneo]


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
    billing: BillingStore | None = None
    settings: Settings | None = None
    admin_token: str = ""
    mailer: Mailer | None = None
    account_exists: Callable[[str], bool] = lambda email: False  # noqa: E731
    admin: AdminService | None = None
    flags: AccountFlags | None = None
    email_verified: Callable[[str], bool] = lambda email: False  # noqa: E731
    mark_verified: Callable[[str], None] = lambda email: None  # noqa: E731
    purge_account: Callable[[str], None] = lambda email: None  # noqa: E731
    send_reset: Callable[[str], bool] = lambda email: False  # noqa: E731
    session_changed: Callable[[str, bool], None] = lambda email, allowed: None  # noqa: E731
    usage_snapshot: Callable[[], dict[str, object]] = dict  # noqa: E731
    admin_limiter: SlidingWindowLimiter = field(default_factory=lambda: SlidingWindowLimiter(60, window=60.0))
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

    def sus_bases(self, request: Request) -> SusBases:
        """As bases do pacote Brasil mais a Tabela SIGTAP (disponibilidade no SUS)."""
        anvisa_data, conitec_data, rename_data = self.brasil_bases(request)
        try:
            return anvisa_data, conitec_data, rename_data, sigtap.carregar()
        except (OSError, ValueError, KeyError) as error:
            raise SourceUnavailableError("A Tabela SIGTAP não está disponível agora.") from error

    @staticmethod
    def sus_meta(bases: SusBases) -> dict[str, object]:
        return {"anvisa": anvisa_meta(bases[0]), "conitec": conitec_meta(bases[1]), "rename": rename_meta(bases[2]), "sigtap": sigtap_meta(bases[3])}

    def brasil_meta(self, bases: Bases) -> dict[str, object]:
        return {"anvisa": anvisa_meta(bases[0]), "conitec": conitec_meta(bases[1]), "rename": rename_meta(bases[2])}

    @staticmethod
    def money(cents: int) -> str:
        return plans.money(cents)

    def plan_for(self, user: str) -> plans.Plan:
        """Plano em vigor da conta. Sem cobranca ativa (`BILLING_ENFORCED`), todas as contas tem os limites do Pro (os tecnicos atuais)."""
        catalog = plans.catalog(self.settings or Settings())
        if self.billing is None or self.settings is None or not self.settings.billing_enforced:
            return catalog[plans.PRO_KEY]
        return catalog.get(self.billing.plan_key(user), catalog[plans.FREE_KEY])

    def usage_for(self, user: str) -> dict[str, int]:
        return {
            "library": len(self.library.items(user)), "lists": len(self.library.lists(user)),
            "reports": len(self.reports.summaries(user)) if self.reports is not None else 0,
        }

    def check_limit(self, user: str, kind: str, current: int) -> None:
        """Levanta `LimitReachedError` (409) se a conta ja usou todo o limite `kind` do plano."""
        plan = self.plan_for(user)
        allowed = getattr(plan, kind)
        if current >= allowed:
            names = {"library": "artigos na biblioteca", "lists": "listas de leitura", "reports": "relatórios"}
            raise LimitReachedError(f"O plano {plan.name} permite até {allowed} {names[kind]}. Veja os planos em #/planos para ampliar.")

    def require_user(self, request: Request) -> str:
        user = self.current_user(request)
        if user is None:
            raise AuthRequiredError("Entre na sua conta para usar a biblioteca e as listas.")
        return user
