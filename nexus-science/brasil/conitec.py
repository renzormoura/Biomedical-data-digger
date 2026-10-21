"""Consulta ao instantaneo da CONITEC (recomendacoes sobre medicamentos), sem IA e sem rede.

- `buscar`: decisoes da Conitec para uma substancia em portugues (casamento por palavra inteira, sem acento);
- `candidatos`: substancias que um texto em INGLES parece citar (ligacao em `brasil.nomes`; sempre a confirmar).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from brasil.nomes import Candidato, aliases, encontrar, formas_inglesas, limpar_substancia, normalizar

__all__ = ["Candidato", "Instantaneo", "Registro", "aliases", "buscar", "candidatos", "carregar", "dias_desde_extracao",
           "formas_inglesas", "normalizar"]

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "dados_brasil" / "conitec.json"
STALE_AFTER_DAYS = 60
MIN_TERM_CHARS = 5
MAX_CANDIDATES = 8

# trechos que encerram o nome da substancia dentro do texto da tecnologia ("X para tratamento de Y")
_CUTS = re.compile(r"\s(?:para|em|como|no|na|nos|nas|versus|ou|via|associad[oa]s?|conforme|segundo)\s|\s\(|\s-\s|:", re.IGNORECASE)
_SPLITS = re.compile(r"(?<!\d),(?!\d)|;|\s\+\s|\se\s(?:o|a|os|as)?\s?|\scom\s|\sem\scombina[cç][aã]o\scom\s", re.IGNORECASE)
_UNITS = {"mg", "g", "ml", "mcg", "ui", "kg", "dose", "doses", "mg/ml", "comprimido", "comprimidos", "injetavel", "oral", "solucao"}
_ARTICLES = {"o", "a", "os", "as", "de", "do", "da"}


@dataclass(frozen=True)
class Registro:
    ano: int | None
    tecnologia: str
    indicacao: str
    recomendacao: str
    decisao_ms: str
    portaria: str
    data_publicacao: str
    relatorio_tecnico: str
    relatorio_sociedade: str
    chave: str  # tecnologia normalizada, para o casamento


@dataclass(frozen=True)
class Instantaneo:
    meta: dict[str, object]
    registros: tuple[Registro, ...]
    vocabulario: dict[str, str]  # termo normalizado -> nome de exibicao


def _termos(tecnologia: str) -> list[str]:
    """Nomes de substancias contidos no texto da tecnologia (original, com acentos)."""
    sem_parenteses = re.sub(r"\([^)]*\)", " ", tecnologia)  # "(DMSA, succimer)" e afins
    nomes: list[str] = []
    for pedaco in _SPLITS.split(sem_parenteses.strip()):
        nome = _CUTS.split(pedaco.strip(), maxsplit=1)[0].strip(" .")
        palavras = [w for w in nome.split() if not re.fullmatch(r"[\d.,%/]+", w) and w.lower() not in _UNITS]
        while palavras and palavras[0].lower() in _ARTICLES:
            palavras.pop(0)
        nome = limpar_substancia(" ".join(palavras))
        if nome and nome[0].isalpha() and len(nome) >= MIN_TERM_CHARS and len(nome.split()) <= 4 and ")" not in nome:
            nomes.append(nome)
    return nomes


@lru_cache(maxsize=4)
def carregar(caminho: str = str(SNAPSHOT_PATH)) -> Instantaneo:
    raw = json.loads(Path(caminho).read_text(encoding="utf-8"))
    registros = tuple(
        Registro(
            ano=item.get("ano"), tecnologia=item["tecnologia"], indicacao=item.get("indicacao", ""),
            recomendacao=item.get("recomendacao", ""), decisao_ms=item.get("decisao_ms", ""), portaria=item.get("portaria", ""),
            data_publicacao=item.get("data_publicacao", ""), relatorio_tecnico=item.get("relatorio_tecnico", ""),
            relatorio_sociedade=item.get("relatorio_sociedade", ""), chave=normalizar(item["tecnologia"]),
        )
        for item in raw["registros"]
    )
    vocabulario: dict[str, str] = {}
    for item in raw["registros"]:
        for nome in _termos(item["tecnologia"]):
            vocabulario.setdefault(normalizar(nome), nome[:1].upper() + nome[1:])
    return Instantaneo(meta=raw["meta"], registros=registros, vocabulario=vocabulario)


def dias_desde_extracao(instantaneo: Instantaneo, hoje: date | None = None) -> int | None:
    try:
        return ((hoje or date.today()) - date.fromisoformat(str(instantaneo.meta.get("extraido_em", "")))).days
    except ValueError:
        return None


def buscar(substancia: str, *, instantaneo: Instantaneo | None = None, limite: int = 40) -> list[Registro]:
    """Decisoes da Conitec cuja tecnologia cita a substancia (palavra inteira, sem acento), mais recentes primeiro."""
    data = instantaneo or carregar()
    consulta = normalizar(substancia)
    if len(consulta) < 3:
        return []
    alvo = f" {consulta} "
    achados = [r for r in data.registros if alvo in f" {r.chave} "]
    achados.sort(key=lambda r: (r.data_publicacao, r.tecnologia), reverse=True)
    return achados[:limite]


def candidatos(texto: str, *, instantaneo: Instantaneo | None = None) -> list[Candidato]:
    """Substancias do vocabulario da Conitec que o texto (em ingles) parece citar, com o metodo da ligacao."""
    return encontrar(texto, (instantaneo or carregar()).vocabulario, limite=MAX_CANDIDATES)
