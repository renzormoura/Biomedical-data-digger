"""Confere cada fonte da lista curada do feed: responde, tem itens e os itens trazem titulo, link e data.

Uso (na raiz do repositorio):  python scripts/verificar_feeds.py

So le os feeds publicos (uma requisicao por fonte) e imprime um resumo; nao grava nada. Rode antes de acrescentar uma fonte nova
em `feed_sources.py` e de vez em quando para achar feeds que mudaram de endereco ou passaram a bloquear leitores automaticos.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "biomedical-article-summariser"))

from catalog import CatalogError  # noqa: E402
from feed import http_fetch, parse_feed  # noqa: E402
from feed_sources import SOURCES  # noqa: E402


def main() -> int:
    problems = 0
    for source in SOURCES:
        try:
            result = http_fetch(source.url)
            if result.status != 200:
                raise CatalogError(f"HTTP {result.status}")
            entries = parse_feed(result.content)
        except CatalogError as error:
            print(f"FALHA  {source.id:26} {error}")
            problems += 1
            continue
        dated = sum(1 for entry in entries if entry.published is not None)
        flag = "OK    " if entries and dated >= max(1, len(entries) // 2) else "ATENCAO"
        if flag != "OK    ":
            problems += 1
        print(f"{flag} {source.id:26} {len(entries):4} itens, {dated} com data")
    print(f"\n{len(SOURCES) - problems} de {len(SOURCES)} fontes sem problema.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
