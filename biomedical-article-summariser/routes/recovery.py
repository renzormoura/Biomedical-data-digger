"""Rotas: recuperacao de senha e confirmacao de e-mail (links de uso unico enviados por e-mail).

- `POST /api/auth/forgot`: pede o link de redefinicao. A resposta e **sempre a mesma** (exista ou nao a conta), para nao
  revelar quais e-mails estao cadastrados; so um link por minuto por e-mail.
- `POST /api/auth/reset`: troca a senha com o token do link (valido por 1 hora, uso unico).
- `POST /api/auth/verify`: confirma o e-mail com o token do link (valido por 48 horas).
- `POST /api/account/resend-verification`: reenvia a confirmacao (exige conta).

Os links usam `APP_BASE_URL` (nunca o cabecalho Host, para nao permitir envenenamento de links) e levam o token no
fragmento da URL (`#/redefinir?token=...`), que o navegador nao envia ao servidor nem a terceiros via Referer.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Request
from loguru import logger
from pydantic import BaseModel, Field

from account_store import AccountStore, AccountStoreError, InvalidCredentialsFormat, validate_credentials
from account_tokens import RESET, VERIFY, AccountTokens
from domain import AuthRequiredError, DiggerError, SourceUnavailableError
from mailer import EmailMessage, Mailer, MailError

RESEND_COOLDOWN = timedelta(seconds=60)
GENERIC_FORGOT = "Se este e-mail tiver uma conta, enviamos um link para redefinir a senha. Ele vale por 1 hora."


class ForgotIn(BaseModel):
    email: str = Field(max_length=320)


class ResetIn(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(max_length=200)


class TokenIn(BaseModel):
    token: str = Field(max_length=200)


@dataclass
class RecoveryContext:
    account_store_factory: Callable[[], AccountStore]
    tokens: AccountTokens
    mailer: Mailer | None
    base_url: str
    throttle_auth: Callable[[Request], None]
    current_user: Callable[[Request], str | None]

    @property
    def enabled(self) -> bool:
        return self.mailer is not None

    def _link(self, route: str, token: str) -> str:
        return f"{self.base_url.rstrip('/')}/#/{route}?token={quote(token, safe='')}"

    def _recently_sent(self, email: str, purpose: str) -> bool:
        last = self.tokens.last_issued(email, purpose)
        return last is not None and self.tokens.now() - last < RESEND_COOLDOWN

    def _send(self, message: EmailMessage) -> bool:
        if self.mailer is None:
            return False
        try:
            self.mailer.send(message)
        except MailError as error:
            logger.warning("Falha ao enviar e-mail de conta: {}", error)
            return False
        return True

    def send_verification(self, email: str) -> bool:
        """Envia (se houver provedor) o link de confirmacao; falhas nunca derrubam quem chamou."""
        if self.mailer is None or self._recently_sent(email, VERIFY):
            return False
        token = self.tokens.issue(email, VERIFY)
        return self._send(EmailMessage(
            email, "Confirme seu e-mail no Biomedical Data Digger",
            "Olá!\n\nConfirme seu e-mail para ativar os avisos por e-mail e proteger sua conta:\n\n"
            f"{self._link('confirmar', token)}\n\nO link vale por 48 horas. Se você não criou esta conta, ignore esta mensagem.\n",
        ))

    def send_reset(self, email: str) -> bool:
        if self.mailer is None or self._recently_sent(email, RESET):
            return False
        token = self.tokens.issue(email, RESET)
        return self._send(EmailMessage(
            email, "Redefinir sua senha no Biomedical Data Digger",
            "Olá!\n\nRecebemos um pedido para redefinir a sua senha. Para escolher uma nova, abra:\n\n"
            f"{self._link('redefinir', token)}\n\nO link vale por 1 hora e só pode ser usado uma vez. "
            "Se você não pediu isso, ignore esta mensagem: sua senha continua a mesma.\n",
        ))


def register_recovery_routes(app: FastAPI, rc: RecoveryContext) -> None:
    @app.post("/api/auth/forgot")
    def forgot_password(body: ForgotIn, request: Request) -> dict[str, Any]:
        rc.throttle_auth(request)
        if not rc.enabled:
            raise SourceUnavailableError("A recuperação de senha por e-mail não está disponível agora. Fale com o suporte.")
        email = (body.email or "").strip().lower()
        try:
            known = bool(email) and rc.account_store_factory().exists(email)
        except AccountStoreError as error:
            raise DiggerError(str(error)) from error
        if known:
            rc.send_reset(email)
        return {"ok": True, "message": GENERIC_FORGOT}

    @app.post("/api/auth/reset")
    def reset_password(body: ResetIn, request: Request) -> dict[str, Any]:
        rc.throttle_auth(request)
        email = rc.tokens.peek(body.token, RESET)
        if email is None:
            raise DiggerError("Este link é inválido ou expirou. Peça um novo link de redefinição.")
        try:
            _, password = validate_credentials(email, body.password)
        except InvalidCredentialsFormat as error:
            raise DiggerError(str(error)) from error
        try:
            changed = rc.account_store_factory().change_password(email, password)
        except AccountStoreError as error:
            raise DiggerError(str(error)) from error
        if not changed:
            raise DiggerError("Este link é inválido ou expirou. Peça um novo link de redefinição.")
        rc.tokens.clear(email, RESET)
        rc.tokens.mark_verified(email)  # quem abriu o link controla a caixa de e-mail
        return {"ok": True}

    @app.post("/api/auth/verify")
    def verify_email(body: TokenIn, request: Request) -> dict[str, Any]:
        rc.throttle_auth(request)
        email = rc.tokens.consume(body.token, VERIFY)
        if email is None:
            raise DiggerError("Este link de confirmação é inválido ou expirou. Peça um novo na sua conta.")
        rc.tokens.mark_verified(email)
        return {"verified": True, "email": email}

    @app.post("/api/account/resend-verification")
    def resend_verification(request: Request) -> dict[str, Any]:
        user = rc.current_user(request)
        if user is None:
            raise AuthRequiredError("Entre na sua conta para confirmar o e-mail.")
        rc.throttle_auth(request)
        if not rc.enabled:
            raise SourceUnavailableError("O envio de e-mails não está disponível agora.")
        if rc.tokens.is_verified(user):
            return {"alreadyVerified": True}
        if rc._recently_sent(user, VERIFY):  # noqa: SLF001 - mesma unidade (contexto de recuperacao)
            return {"sent": False, "reason": "wait"}
        if not rc.send_verification(user):
            raise DiggerError("Não foi possível enviar o e-mail agora. Tente novamente em instantes.")
        return {"sent": True}
