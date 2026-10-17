"""Atualiza `biomedical-article-summariser/dados_brasil/conitec.json` a partir da planilha oficial da Conitec.

Uso (na raiz do repositorio):  python scripts/atualizar_conitec.py

Revise o diff antes de commitar: o instantaneo e a unica fonte que o servidor consulta.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "biomedical-article-summariser"))

from brasil import conitec_build  # noqa: E402


def main() -> int:
    try:
        snapshot = conitec_build.atualizar()
    except conitec_build.ConitecError as error:
        print(f"Falha na atualizacao: {error}", file=sys.stderr)
        return 1
    meta = snapshot["meta"]
    print(f"Instantaneo gravado em {conitec_build.SNAPSHOT_PATH}")
    print(f"  arquivo: {meta['arquivo_url']} ({meta['arquivo_data']})")  # type: ignore[index]
    print(f"  medicamentos: {meta['linhas_medicamento']} de {meta['linhas_planilha']} linhas")  # type: ignore[index]
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
