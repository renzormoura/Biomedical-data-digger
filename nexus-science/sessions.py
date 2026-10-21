"""Sessoes assinadas por HMAC, sem dependencias.

O cookie carrega `usuario.expiracao.assinatura`. A assinatura (HMAC-SHA256 com
segredo do servidor) impede adulteracao; a expiracao limita o tempo de vida.
Nenhum dado sensivel vai no cookie, apenas o e-mail ja normalizado.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from collections.abc import Callable

DEFAULT_TTL_SECONDS = 7 * 24 * 3600


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class SessionSigner:
    def __init__(
        self,
        secret: str,
        ttl: int = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if len(secret) < 16:
            raise ValueError("O segredo de sessao deve ter ao menos 16 caracteres.")
        self._key = secret.encode("utf-8")
        self._ttl = ttl
        self._clock = clock

    @staticmethod
    def generate_secret() -> str:
        return secrets.token_urlsafe(48)

    def _sign(self, payload: str) -> str:
        return _b64(hmac.new(self._key, payload.encode("utf-8"), hashlib.sha256).digest())

    def issue(self, user: str) -> str:
        payload = f"{_b64(user.encode('utf-8'))}.{int(self._clock()) + self._ttl}"
        return f"{payload}.{self._sign(payload)}"

    def verify(self, token: str | None) -> str | None:
        """Retorna o usuario se o token for valido e nao expirado; senao None."""
        if not token:
            return None
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = f"{parts[0]}.{parts[1]}"
        if not hmac.compare_digest(self._sign(payload), parts[2]):
            return None
        try:
            if int(parts[1]) <= self._clock():
                return None
            return _unb64(parts[0]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
