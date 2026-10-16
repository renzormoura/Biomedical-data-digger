"""Configuracao lida do ambiente, validada em um unico lugar."""

from __future__ import annotations

import os
from dataclasses import dataclass


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

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            llm_calls_per_minute=_int_env("RATE_LIMIT_PER_MINUTE", 8, minimum=1),
            login_attempts_per_minute=_int_env("LOGIN_ATTEMPTS_PER_MINUTE", 5, minimum=1),
            trusted_proxy_hops=_int_env("TRUSTED_PROXY_HOPS", 1, minimum=0),
        )
