"""Termos de Uso e Politica de Privacidade servidos pelo produto, com a versao vigente e os dados do controlador.

Os textos ficam em `legal_texts/*.md` (Markdown simples) e usam marcadores `{{versao}}`, `{{controlador}}`, `{{contato}}` e
`{{foro}}`, preenchidos com as variaveis LEGAL_CONTROLLER, LEGAL_CONTACT e LEGAL_FORUM. Os textos sao **rascunhos** que
precisam de revisao juridica antes do lancamento; `VERSION` muda sempre que o conteudo mudar, e o aceite de cada conta
guarda a versao aceita.
"""

from __future__ import annotations

import re
from pathlib import Path

import markdown_lite
from config import Settings
from domain import NotFoundError

VERSION = "2026-10-20"
TEXTS_DIR = Path(__file__).resolve().parent / "legal_texts"
DOCS: dict[str, tuple[str, str]] = {
    "termos": ("Termos de Uso", "termos-de-uso.md"),
    "privacidade": ("Política de Privacidade", "politica-de-privacidade.md"),
}
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")
_INTERNAL_LINK = re.compile(r"\[([^\]\n]+)\]\((/#/[a-z]+)\)")  # so caminhos internos fixos; o resto passa pelo escape do markdown_lite
MISSING = "[a definir]"


def values(settings: Settings) -> dict[str, str]:
    return {
        "versao": VERSION,
        "controlador": settings.legal_controller or MISSING,
        "contato": settings.legal_contact or MISSING,
        "foro": settings.legal_forum or "domicílio do controlador",
    }


def is_complete(settings: Settings) -> bool:
    """Controlador e contato definidos (sem isso o texto publicado mostraria `[a definir]`)."""
    return bool(settings.legal_controller and settings.legal_contact)


def render(doc: str, settings: Settings) -> dict[str, str]:
    """Titulo, versao e HTML (ja escapado pelo `markdown_lite`) do documento `doc`."""
    if doc not in DOCS:
        raise NotFoundError("Documento não encontrado.")
    title, filename = DOCS[doc]
    replacements = values(settings)
    text = _PLACEHOLDER.sub(lambda m: replacements.get(m.group(1), m.group(0)), (TEXTS_DIR / filename).read_text(encoding="utf-8"))
    html = _INTERNAL_LINK.sub(r'<a href="\2">\1</a>', markdown_lite.render(text))
    return {"title": title, "version": VERSION, "html": html}
