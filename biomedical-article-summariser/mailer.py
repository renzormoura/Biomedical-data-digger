"""Envio de e-mail transacional (confirmacao de endereco e recuperacao de senha), sem depender de um provedor especifico.

`SmtpMailer` fala SMTP padrao (a maioria dos provedores oferece: Resend, Postmark, SES, Brevo, Mailgun, Google Workspace...).
`LogMailer` so escreve a mensagem no log e serve para desenvolvimento: **nunca** e usado em producao, porque o log
mostraria os links de redefinicao. Em producao, sem `SMTP_HOST` o envio fica desativado (`mailer_from_env` devolve `None`).

Variaveis: SMTP_HOST, SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM, SMTP_SECURITY (`starttls` padrao, `ssl` ou `none`).
"""

from __future__ import annotations

import os
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from email.utils import formatdate, make_msgid
from typing import Protocol

from loguru import logger

SMTP_TIMEOUT = 10


class MailError(RuntimeError):
    """Falha ao entregar a mensagem ao servidor de e-mail (a mensagem nunca traz credenciais)."""


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    text: str


class Mailer(Protocol):
    def send(self, message: EmailMessage) -> None:
        """Entrega a mensagem ou levanta `MailError`."""


class SmtpMailer:
    def __init__(
        self, host: str, port: int = 587, user: str = "", password: str = "", sender: str = "", security: str = "starttls",
    ) -> None:
        if security not in ("starttls", "ssl", "none"):
            raise ValueError("SMTP_SECURITY deve ser starttls, ssl ou none.")
        self._host, self._port, self._user, self._password = host, port, user, password
        self._sender, self._security = sender or user, security

    def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"], mime["To"], mime["Subject"] = self._sender, message.to, message.subject
        mime["Date"], mime["Message-ID"] = formatdate(localtime=False), make_msgid(domain=self._sender.rpartition("@")[2] or None)
        mime.set_content(message.text)
        try:
            context = ssl.create_default_context()
            if self._security == "ssl":
                server: smtplib.SMTP = smtplib.SMTP_SSL(self._host, self._port, timeout=SMTP_TIMEOUT, context=context)
            else:
                server = smtplib.SMTP(self._host, self._port, timeout=SMTP_TIMEOUT)
            with server:
                if self._security == "starttls":
                    server.starttls(context=context)
                if self._user:
                    server.login(self._user, self._password)
                server.send_message(mime)
        except (smtplib.SMTPException, OSError) as error:
            raise MailError(f"Nao foi possivel enviar o e-mail ({type(error).__name__}).") from error


class LogMailer:
    """Desenvolvimento: escreve a mensagem no log em vez de enviar."""

    def send(self, message: EmailMessage) -> None:
        logger.info("E-mail (modo desenvolvimento, nao enviado) para {}: {}\n{}", message.to, message.subject, message.text)


def mailer_from_env(production: bool) -> Mailer | None:
    """`SmtpMailer` se `SMTP_HOST` estiver definido; `LogMailer` em desenvolvimento; `None` em producao sem SMTP."""
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        return None if production else LogMailer()
    try:
        port = int(os.environ.get("SMTP_PORT", "587").strip() or "587")
    except ValueError as error:
        raise ValueError("SMTP_PORT deve ser um inteiro.") from error
    user = os.environ.get("SMTP_USER", "").strip()
    sender = os.environ.get("SMTP_FROM", "").strip() or user
    if not sender:
        raise ValueError("Defina SMTP_FROM (endereco remetente) ao configurar SMTP_HOST.")
    return SmtpMailer(host, port, user, os.environ.get("SMTP_PASSWORD", ""), sender, os.environ.get("SMTP_SECURITY", "starttls").strip().lower())
