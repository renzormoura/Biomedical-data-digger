"""Configuracao lida do ambiente, validada em um unico lugar."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{name} deve ser um inteiro, recebido: {raw!r}") from error
    if value < minimum:
        raise ValueError(f"{name} deve ser >= {minimum}, recebido: {value}")
    return value


@dataclass(frozen=True)
class Settings:
    llm_calls_per_minute: int = 8
    login_attempts_per_minute: int = 5
    trusted_proxy_hops: int = 1
    production: bool = False
    session_secret: str = field(default="", repr=False)
    admin_token: str = field(default="", repr=False)
    daily_token_budget_guest: int = 60_000
    daily_token_budget_user: int = 200_000

    @classmethod
    def from_env(cls) -> Settings:
        production = os.environ.get("APP_ENV", "development").strip().lower() == "production"
        secret = os.environ.get("SESSION_SECRET", "").strip()
        if production and len(secret) < 32:
            raise ValueError("SESSION_SECRET (>= 32 caracteres) e obrigatoria em producao.")
        admin_token = os.environ.get("ADMIN_TOKEN", "").strip()
        if admin_token and len(admin_token) < 24:
            raise ValueError("ADMIN_TOKEN deve ter ao menos 24 caracteres (ou ficar vazio para desativar).")
        return cls(
            production=production,
            session_secret=secret,
            admin_token=admin_token,
            daily_token_budget_guest=_int_env("DAILY_TOKEN_BUDGET_GUEST", 60_000, minimum=0),
            daily_token_budget_user=_int_env("DAILY_TOKEN_BUDGET_USER", 200_000, minimum=0),
            llm_calls_per_minute=_int_env("RATE_LIMIT_PER_MINUTE", 8, minimum=1),
            login_attempts_per_minute=_int_env("LOGIN_ATTEMPTS_PER_MINUTE", 5, minimum=1),
            trusted_proxy_hops=_int_env("TRUSTED_PROXY_HOPS", 1, minimum=0),
        )
