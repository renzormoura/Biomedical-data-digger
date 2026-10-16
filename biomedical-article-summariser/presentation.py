"""Texto de apresentacao independente de framework web."""

from __future__ import annotations

from collections.abc import Sequence

import contexto_brasil


def verification_annex_md(source_keys: Sequence[str]) -> str:
    """Anexo com status de alcancabilidade das fontes oficiais citadas.

    Falha de rede vira alerta explicito, nunca afirmacao silenciosa.
    """
    catalog = contexto_brasil.VERIFICATION_SOURCES
    urls = [catalog[k]["catalog_url"] for k in source_keys if k in catalog]
    by_url = {v["catalog_url"]: v for v in catalog.values()}
    results = contexto_brasil.get_verificacao().verificar_fontes(urls)
    lines = [
        "\n\n---",
        "> **Anexo de verificação externa** — status das fontes oficiais de contexto:",
    ]
    for result in results:
        source = by_url.get(result.get("url", ""), {})
        name = source.get("name", result.get("url", ""))
        revised = source.get("updated", "—")
        if result.get("status") == "ok":
            lines.append(f"> - 🟢 **{name}** — acessível · revisão {revised} · {result.get('url', '')}")
        else:
            lines.append(
                f"> - 🔴 **{name}** — **não verificável** ({result.get('motivo', 'erro')}) · {result.get('url', '')}"
            )
    lines.append(
        "> ⚠️ Afirmações contextuais sobre uma fonte 🔴 devem ser tratadas como "
        "**não verificáveis** até a fonte voltar a responder."
    )
    return "\n".join(lines)


UNVERIFIABLE_FALLBACK = (
    "\n\n---\n> ⚠️ **Verificação externa indisponível no momento.** "
    "Trate qualquer afirmação contextual como **não verificável**."
)
