"""Atualiza `nexus-science/dados_brasil/rename.json` a partir do PDF oficial da Rename.

Uso (na raiz do repositorio):  python scripts/atualizar_rename.py   (requer `pip install pypdf`)

Baixa ~5 MB. A extracao do PDF NAO e garantida: confira uma amostra de itens contra o PDF antes de commitar.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "nexus-science"))

from brasil import rename_build  # noqa: E402


def main() -> int:
    try:
        snapshot = rename_build.atualizar()
    except rename_build.RenameError as error:
        print(f"Falha na atualizacao: {error}", file=sys.stderr)
        return 1
    meta = snapshot["meta"]
    print(f"Instantaneo gravado em {rename_build.SNAPSHOT_PATH}")
    print(f"  {meta['itens']} itens; {meta['substancias']} substancias; {meta['paginas_pdf']} paginas")  # type: ignore[index]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
