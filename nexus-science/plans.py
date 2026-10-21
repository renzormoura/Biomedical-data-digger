"""Planos e seus limites. Um plano e so uma tabela de limites; o preco vem da configuracao.

Hoje os limites valem para: artigos na biblioteca, listas de leitura e relatorios de tema. Com `BILLING_ENFORCED` desligado
(padrao) todas as contas tem os limites do Pro, que sao os limites tecnicos atuais do produto.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from config import Settings

FREE_KEY = "gratuito"
PRO_KEY = "pro"
PERIODS = (1, 3, 12)  # meses que a pessoa pode pagar de uma vez
DAYS_PER_MONTH = 30


@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    description: str
    library: int
    lists: int
    reports: int
    price_cents: int  # por mes


FREE = Plan(FREE_KEY, "Gratuito", "Para conhecer: busca, feed e nota de confiabilidade sem limite.", library=50, lists=3, reports=1, price_cents=0)
PRO = Plan(PRO_KEY, "Pro", "Biblioteca, listas e relatórios completos, avisos e exportações.", library=500, lists=50, reports=30, price_cents=2900)


def catalog(settings: Settings) -> dict[str, Plan]:
    """Os planos com o preco da configuracao (`PRO_PRICE_CENTS`)."""
    return {FREE_KEY: FREE, PRO_KEY: replace(PRO, price_cents=settings.pro_price_cents)}


def money(cents: int) -> str:
    """`2900` -> `R$ 29,00` (ponto nos milhares)."""
    return f"R$ {cents // 100:,}".replace(",", ".") + f",{cents % 100:02d}"


def amount_cents(plan: Plan, months: int) -> int:
    return plan.price_cents * months
