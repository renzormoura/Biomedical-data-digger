"""Consulta ao instantaneo da RENAME 2024 (Relacao Nacional de Medicamentos Essenciais), sem IA e sem rede.

Constar na Rename significa que a substancia e um medicamento essencial da relacao nacional, com o componente de
financiamento indicado. NAO significa que ha estoque ou oferta na unidade de saude do usuario: a interface diz isso.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from brasil.nomes import Candidato, encontrar, normalizar

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "dados_brasil" / "rename.json"
STALE_AFTER_DAYS = 400  # a Rename e revista a cada 1-2 anos; so avisa muito depois da edicao
MIN_TERM_CHARS = 5
MAX_CANDIDATES = 8
MAX_PRESENTATIONS = 12


@dataclass(frozen=True)
class Apresentacao:
    texto: str  # concentracao e forma, como no PDF
    componente: str
    atc: str
    pagina: int


@dataclass(frozen=True)
class Registro:
    nome: str  # DCB como no PDF
    chave: str
    componentes: tuple[str, ...]
    atc: tuple[str, ...]
    apresentacoes: tuple[Apresentacao, ...]


@dataclass(frozen=True)
class Instantaneo:
    meta: dict[str, object]
    registros: dict[str, Registro]
    vocabulario: dict[str, str]


def _unicos(valores: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(valores))


@lru_cache(maxsize=4)
def carregar(caminho: str = str(SNAPSHOT_PATH)) -> Instantaneo:
    raw = json.loads(Path(caminho).read_text(encoding="utf-8"))
    agrupado: dict[str, list[dict[str, object]]] = {}
    for item in raw["itens"]:
        agrupado.setdefault(item["chave"], []).append(item)
    registros = {
        chave: Registro(
            nome=str(itens[0]["nome"]), chave=chave,
            componentes=_unicos([str(i["componente"]) for i in itens]), atc=_unicos([str(i["atc"]) for i in itens]),
            apresentacoes=tuple(Apresentacao(str(i["apresentacao"]), str(i["componente"]), str(i["atc"]), int(str(i["pagina"]))) for i in itens),
        )
        for chave, itens in agrupado.items()
    }
    vocabulario = {k: r.nome[:1].upper() + r.nome[1:] for k, r in registros.items() if len(k) >= MIN_TERM_CHARS}
    return Instantaneo(meta=raw["meta"], registros=registros, vocabulario=vocabulario)


def dias_desde_extracao(instantaneo: Instantaneo, hoje: date | None = None) -> int | None:
    try:
        return ((hoje or date.today()) - date.fromisoformat(str(instantaneo.meta.get("extraido_em", "")))).days
    except ValueError:
        return None


def buscar(substancia: str, *, instantaneo: Instantaneo | None = None, limite: int = 12) -> list[Registro]:
    """A substancia exata primeiro; depois as que a contem como palavra inteira (ex.: 'insulina' -> 'insulina humana')."""
    data = instantaneo or carregar()
    consulta = normalizar(substancia)
    if len(consulta) < 3:
        return []
    exata = data.registros.get(consulta)
    alvo = f" {consulta} "
    parecidas = sorted((r for k, r in data.registros.items() if k != consulta and alvo in f" {k} "), key=lambda r: r.chave)
    return ([exata] if exata else []) + parecidas[: limite - (1 if exata else 0)]


def candidatos(texto: str, *, instantaneo: Instantaneo | None = None) -> list[Candidato]:
    return encontrar(texto, (instantaneo or carregar()).vocabulario, limite=MAX_CANDIDATES)
