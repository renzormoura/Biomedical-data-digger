"""Atualiza `nexus-science/dados_brasil/sigtap.json` a partir da Tabela Unificada oficial do DATASUS (SIGTAP).

Uso (na raiz do repositorio):  python scripts/atualizar_sigtap.py

Revise o diff antes de commitar: o instantaneo e a unica fonte que o servidor consulta.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "nexus-science"))

from brasil import sigtap_build  # noqa: E402


def main() -> int:
    try:
        snapshot = sigtap_build.atualizar()
    except sigtap_build.SigtapError as error:
        print(f"Falha na atualizacao: {error}", file=sys.stderr)
        return 1
    meta = snapshot["meta"]
    print(f"Instantaneo gravado em {sigtap_build.SNAPSHOT_PATH}")
    print(f"  arquivo: {meta['arquivo_url']} (competencia {meta['competencia']})")  # type: ignore[index]
    print(f"  procedimentos: {meta['procedimentos']}")  # type: ignore[index]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
