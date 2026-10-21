"""Consulta ao instantaneo da ANVISA (registros de medicamentos por substancia), sem IA e sem rede.

Registro ativo na ANVISA significa que o produto pode ser comercializado no pais. NAO significa que o SUS o
fornece, nem que haja estoque: a interface sempre diz isso.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from brasil.nomes import Candidato, encontrar, normalizar

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "dados_brasil" / "anvisa.json"
STALE_AFTER_DAYS = 60
MIN_TERM_CHARS = 5
MAX_CANDIDATES = 8


@dataclass(frozen=True)
class Substancia:
    nome: str
    chave: str
    ativos: int
    inativos: int
    ativos_isolado: int  # registros ativos em que a substancia e o unico principio ativo
    categorias: dict[str, int]  # categorias regulatorias entre os registros ativos
    classes: tuple[str, ...]
    empresas: int  # empresas com registro ativo
    validade_max: str  # AAAA-MM do registro ativo com validade mais distante


@dataclass(frozen=True)
class Instantaneo:
    meta: dict[str, object]
    substancias: dict[str, Substancia]
    vocabulario: dict[str, str]  # chave -> nome de exibicao (so nomes com tamanho minimo)


@lru_cache(maxsize=4)
def carregar(caminho: str = str(SNAPSHOT_PATH)) -> Instantaneo:
    raw = json.loads(Path(caminho).read_text(encoding="utf-8"))
    substancias = {
        item["chave"]: Substancia(
            nome=item["nome"], chave=item["chave"], ativos=item["ativos"], inativos=item["inativos"],
            ativos_isolado=item["ativos_isolado"], categorias=dict(item.get("categorias", {})),
            classes=tuple(item.get("classes", ())), empresas=item.get("empresas", 0), validade_max=item.get("validade_max", ""),
        )
        for item in raw["substancias"]
    }
    vocabulario = {k: s.nome[:1].upper() + s.nome[1:] for k, s in substancias.items() if len(k) >= MIN_TERM_CHARS}
    return Instantaneo(meta=raw["meta"], substancias=substancias, vocabulario=vocabulario)


def dias_desde_extracao(instantaneo: Instantaneo, hoje: date | None = None) -> int | None:
    try:
        return ((hoje or date.today()) - date.fromisoformat(str(instantaneo.meta.get("extraido_em", "")))).days
    except ValueError:
        return None


def buscar(substancia: str, *, instantaneo: Instantaneo | None = None, limite: int = 12) -> list[Substancia]:
    """A substancia exata primeiro; depois as que a contem como palavra inteira (ex.: 'insulina' -> 'insulina humana')."""
    data = instantaneo or carregar()
    consulta = normalizar(substancia)
    if len(consulta) < 3:
        return []
    exata = data.substancias.get(consulta)
    alvo = f" {consulta} "
    parecidas = sorted(
        (s for k, s in data.substancias.items() if k != consulta and alvo in f" {k} "),
        key=lambda s: (-s.ativos, s.chave),
    )
    return ([exata] if exata else []) + parecidas[: limite - (1 if exata else 0)]


def candidatos(texto: str, *, instantaneo: Instantaneo | None = None) -> list[Candidato]:
    return encontrar(texto, (instantaneo or carregar()).vocabulario, limite=MAX_CANDIDATES)
