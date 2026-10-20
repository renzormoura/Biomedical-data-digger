"""Configuracao lida do ambiente, validada em um unico lugar."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


class ConfigurationError(ValueError):
    """Variavel de ambiente ausente ou invalida (o servico nao deve subir assim)."""


def _int_env(name: str, default: int, minimum: int = 0) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as error:
        raise ConfigurationError(f"{name} deve ser um inteiro, recebido: {raw!r}") from error
    if value < minimum:
        raise ConfigurationError(f"{name} deve ser >= {minimum}, recebido: {value}")
    return value


def _float_env(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as error:
        raise ConfigurationError(f"{name} deve ser um numero, recebido: {raw!r}") from error
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{name} deve estar entre {minimum} e {maximum}, recebido: {value}")
    return value


@dataclass(frozen=True)
class Settings:
    llm_calls_per_minute: int = 8
    login_attempts_per_minute: int = 5
    trusted_proxy_hops: int = 1
    production: bool = False
    session_secret: str = field(default="", repr=False)
    admin_token: str = field(default="", repr=False)
    alerts_cron_token: str = field(default="", repr=False)
    llm_temperature: float = 0.2
    generative_clinical: bool = False
    discovery_calls_per_minute: int = 30
    openalex_api_key: str = field(default="", repr=False)
    openalex_mailto: str = ""
    ncbi_api_key: str = field(default="", repr=False)
    daily_token_budget_guest: int = 60_000
    daily_token_budget_user: int = 200_000
    app_base_url: str = "http://localhost:7860"  # base dos links enviados por e-mail (nunca vem do cabecalho Host)

    @classmethod
    def from_env(cls) -> Settings:
        production = os.environ.get("APP_ENV", "development").strip().lower() == "production"
        secret = os.environ.get("SESSION_SECRET", "").strip()
        if production and len(secret) < 32:
            raise ConfigurationError("SESSION_SECRET (>= 32 caracteres) e obrigatoria em producao.")
        admin_token = os.environ.get("ADMIN_TOKEN", "").strip()
        if admin_token and len(admin_token) < 24:
            raise ConfigurationError("ADMIN_TOKEN deve ter ao menos 24 caracteres (ou ficar vazio para desativar).")
        cron_token = os.environ.get("ALERTS_CRON_TOKEN", "").strip()
        if cron_token and len(cron_token) < 24:
            raise ConfigurationError("ALERTS_CRON_TOKEN deve ter ao menos 24 caracteres (ou ficar vazio para desativar).")
        base_url = os.environ.get("APP_BASE_URL", "").strip().rstrip("/")
        if production and os.environ.get("SMTP_HOST", "").strip() and not base_url.startswith("https://"):
            raise ConfigurationError("APP_BASE_URL (https://...) e obrigatoria em producao quando SMTP_HOST esta definido.")
        return cls(
            production=production,
            app_base_url=base_url or "http://localhost:7860",
            alerts_cron_token=cron_token,
            session_secret=secret,
            admin_token=admin_token,
            discovery_calls_per_minute=_int_env("DISCOVERY_CALLS_PER_MINUTE", 30, minimum=1),
            openalex_api_key=os.environ.get("OPENALEX_API_KEY", "").strip(),
            openalex_mailto=os.environ.get("OPENALEX_MAILTO", "").strip(),
            ncbi_api_key=os.environ.get("NCBI_API_KEY", "").strip(),
            generative_clinical=os.environ.get("ENABLE_GENERATIVE_CLINICAL", "").strip().lower()
            in ("1", "true", "yes", "on"),
            llm_temperature=_float_env("LLM_TEMPERATURE", 0.2, minimum=0.0, maximum=2.0),
            daily_token_budget_guest=_int_env("DAILY_TOKEN_BUDGET_GUEST", 60_000, minimum=0),
            daily_token_budget_user=_int_env("DAILY_TOKEN_BUDGET_USER", 200_000, minimum=0),
            llm_calls_per_minute=_int_env("RATE_LIMIT_PER_MINUTE", 8, minimum=1),
            login_attempts_per_minute=_int_env("LOGIN_ATTEMPTS_PER_MINUTE", 5, minimum=1),
            trusted_proxy_hops=_int_env("TRUSTED_PROXY_HOPS", 1, minimum=0),
        )
