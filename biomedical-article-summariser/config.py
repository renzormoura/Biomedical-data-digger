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

    @classmethod
    def from_env(cls) -> Settings:
        production = os.environ.get("APP_ENV", "development").strip().lower() == "production"
        secret = os.environ.get("SESSION_SECRET", "").strip()
        if production and len(secret) < 32:
            raise ValueError("SESSION_SECRET (>= 32 caracteres) e obrigatoria em producao.")
        return cls(
            production=production,
            session_secret=secret,
            llm_calls_per_minute=_int_env("RATE_LIMIT_PER_MINUTE", 8, minimum=1),
            login_attempts_per_minute=_int_env("LOGIN_ATTEMPTS_PER_MINUTE", 5, minimum=1),
            trusted_proxy_hops=_int_env("TRUSTED_PROXY_HOPS", 1, minimum=0),
        )
