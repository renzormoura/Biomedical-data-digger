"""Atualiza `biomedical-article-summariser/dados_brasil/anvisa.json` a partir dos dados abertos da ANVISA.

Uso (na raiz do repositorio):  python scripts/atualizar_anvisa.py

Baixa ~46 MB; revise o diff antes de commitar: o instantaneo e a unica fonte que o servidor consulta.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "biomedical-article-summariser"))

from brasil import anvisa_build  # noqa: E402


def main() -> int:
    try:
        snapshot = anvisa_build.atualizar()
    except anvisa_build.AnvisaError as error:
        print(f"Falha na atualizacao: {error}", file=sys.stderr)
        return 1
    meta = snapshot["meta"]
    print(f"Instantaneo gravado em {anvisa_build.SNAPSHOT_PATH}")
    print(f"  arquivo modificado em {meta['arquivo_modificado']}: {meta['linhas_csv']} linhas")  # type: ignore[index]
    print(f"  {meta['substancias']} substancias; {meta['registros_ativos']} registros ativos")  # type: ignore[index]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
