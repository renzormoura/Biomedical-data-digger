"""Texto de apresentacao independente de framework web."""

from __future__ import annotations

from collections.abc import Sequence

import contexto_brasil


def verification_annex_md(source_keys: Sequence[str]) -> str:
    """Anexo que informa se o site oficial de cada fonte respondeu agora.

    ATENCAO: isso so mostra que a fonte esta no ar. Nao confirma nenhuma afirmacao da analise.
    Falha de rede vira alerta explicito, nunca afirmacao silenciosa.
    """
    catalog = contexto_brasil.VERIFICATION_SOURCES
    urls = [catalog[k]["catalog_url"] for k in source_keys if k in catalog]
    by_url = {v["catalog_url"]: v for v in catalog.values()}
    results = contexto_brasil.get_verificacao().verificar_fontes(urls)
    lines = [
        "\n\n---",
        "> **Fontes oficiais de referência** — o site de cada órgão está no ar? "
        "(isso **não confirma** o conteúdo da análise):",
    ]
    for result in results:
        source = by_url.get(result.get("url", ""), {})
        name = source.get("name", result.get("url", ""))
        if result.get("status") == "ok":
            lines.append(f"> - **{name}** — site respondeu · {result.get('url', '')}")
        else:
            lines.append(
                f"> - **{name}** — **sem resposta** ({result.get('motivo', 'erro')}) · {result.get('url', '')}"
            )
    lines.append(
        "> Para qualquer afirmação sobre disponibilidade, registro ou regulação no Brasil, confira diretamente "
        "na fonte oficial. O que não estiver no resumo do artigo deve ser tratado como **não verificado**."
    )
    return "\n".join(lines)


UNVERIFIABLE_FALLBACK = (
    "\n\n---\n> **Verificação externa indisponível no momento.** "
    "Trate qualquer afirmação contextual como **não verificável**."
)
