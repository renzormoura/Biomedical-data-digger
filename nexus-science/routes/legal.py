"""Rotas: textos legais (Termos de Uso e Politica de Privacidade), publicos."""

from __future__ import annotations

from fastapi import FastAPI

import legal
from config import Settings


def register_legal_routes(app: FastAPI, settings: Settings) -> None:
    @app.get("/api/legal/{doc}")
    def legal_document(doc: str) -> dict[str, str]:
        """Documento legal vigente, com a versao (o aceite da conta guarda essa versao)."""
        return legal.render(doc, settings)
