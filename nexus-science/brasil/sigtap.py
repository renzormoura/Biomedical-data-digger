"""Consulta ao instantaneo da Tabela SIGTAP (procedimentos, medicamentos e OPM do SUS), sem IA e sem rede.

Constar na SIGTAP significa que o SUS tem um codigo para o procedimento (e, portanto, pode pagar e registrar a sua
execucao nos servicos habilitados). NAO significa que a unidade de saude do usuario o oferece: a interface diz isso.

- `buscar`: procedimentos cujo nome contem todas as palavras do termo (em portugues, sem acento);
- `candidatos`: procedimentos e tecnicas que um texto em INGLES parece citar, por tabela curada de sinonimos e por
  cognatos de sufixo (-ectomy/-ectomia...). Toda ligacao e apenas uma *possivel correspondencia*.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from brasil.nomes import normalizar

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "dados_brasil" / "sigtap.json"
ALIASES_PATH = Path(__file__).resolve().parent.parent / "dados_brasil" / "aliases_procedimentos.json"
STALE_AFTER_DAYS = 120  # a tabela e publicada todo mes; os procedimentos mudam pouco, entao o aviso e mais folgado
MIN_TERM_CHARS = 4
MAX_CANDIDATES = 10
MAX_DIFERENCA = 2  # letras a mais na raiz portuguesa (appendectomy ~ apendicectomia), para nao ligar mast- a mastoid-
MAX_SHOWN = 8
COMPLEXIDADE = {"0": "não se aplica", "1": "atenção básica", "2": "média complexidade", "3": "alta complexidade"}
_STOP = {"de", "da", "do", "das", "dos", "em", "com", "sem", "por", "para", "e", "a", "o", "as", "os", "no", "na", "nos", "nas", "ou"}

# terminacao em ingles (singular e plural) -> terminacao em portugues: tecnicas cujo nome e cognato
_FINAIS = {
    "ectomy": "ectomia", "ectomies": "ectomia", "otomy": "otomia", "otomies": "otomia", "ostomy": "ostomia", "ostomies": "ostomia",
    "plasty": "plastia", "plasties": "plastia", "scopy": "scopia", "scopies": "scopia", "graphy": "grafia", "graphies": "grafia",
    "pexy": "pexia", "pexies": "pexia", "rrhaphy": "rafia", "rrhaphies": "rafia", "centesis": "centese", "tripsy": "tripsia",
}
_PALAVRA_EN = re.compile(r"\b([a-z]{3,}?)(" + "|".join(sorted(_FINAIS, key=len, reverse=True)) + r")\b")


@dataclass(frozen=True)
class Procedimento:
    codigo: str
    nome: str
    complexidade: str
    grupo: str
    subgrupo: str
    chave: str  # nome normalizado, para o casamento

    @property
    def complexidade_texto(self) -> str:
        return COMPLEXIDADE.get(self.complexidade, "")


@dataclass(frozen=True)
class Instantaneo:
    meta: dict[str, object]
    procedimentos: tuple[Procedimento, ...]
    palavras: frozenset[str]  # palavras (normalizadas) dos nomes, para ligar cognatos


@dataclass(frozen=True)
class Candidato:
    termo: str  # termo em portugues a buscar na tabela
    en: str  # trecho do texto que originou a ligacao
    metodo: str  # "sinonimo" ou "cognato"
    verificavel: bool  # so os sinonimos podem ser dados como "nao consta" (o cognato so nasce se a tabela tem a palavra)


@dataclass(frozen=True)
class Resultado:
    total: int
    itens: tuple[Procedimento, ...]  # os primeiros, ja ordenados


@lru_cache(maxsize=4)
def carregar(caminho: str = str(SNAPSHOT_PATH)) -> Instantaneo:
    raw = json.loads(Path(caminho).read_text(encoding="utf-8"))
    grupos, subgrupos = raw.get("grupos", {}), raw.get("subgrupos", {})
    procedimentos = tuple(
        Procedimento(
            codigo=codigo, nome=nome, complexidade=complexidade, grupo=str(grupos.get(codigo[:2], "")),
            subgrupo=str(subgrupos.get(codigo[:4], "")), chave=normalizar(nome),
        )
        for codigo, nome, complexidade in raw["procedimentos"]
    )
    palavras = frozenset(w for p in procedimentos for w in p.chave.split() if len(w) >= MIN_TERM_CHARS)
    return Instantaneo(meta=raw["meta"], procedimentos=procedimentos, palavras=palavras)


def dias_desde_extracao(instantaneo: Instantaneo, hoje: date | None = None) -> int | None:
    try:
        return ((hoje or date.today()) - date.fromisoformat(str(instantaneo.meta.get("extraido_em", "")))).days
    except ValueError:
        return None


def _casa(palavra: str, token: str) -> bool:
    """A palavra do nome casa com o token da busca: prefixo, ou plural/flexao curta ('operacoes' acha 'operacao')."""
    if palavra.startswith(token):
        return True
    if len(palavra) < 6:
        return False
    comum = 0
    for a, b in zip(palavra, token, strict=False):
        if a != b:
            break
        comum += 1
    return comum >= max(5, len(palavra) - 2) and len(token) - comum <= 3


def buscar(termo: str, *, instantaneo: Instantaneo | None = None, limite: int = MAX_SHOWN) -> Resultado:
    """Procedimentos cujo nome tem todas as palavras do termo; o nome exato e os mais curtos primeiro."""
    data = instantaneo or carregar()
    consulta = normalizar(termo)
    tokens = [t for t in consulta.split() if t not in _STOP]
    if not tokens or len(consulta) < MIN_TERM_CHARS:
        return Resultado(0, ())
    achados: list[tuple[tuple[int, int, str], Procedimento]] = []
    for item in data.procedimentos:
        palavras = item.chave.split()
        if all(any(_casa(p, t) for p in palavras) for t in tokens):
            exato = 0 if item.chave == consulta else 1 if item.chave.startswith(consulta) else 2
            achados.append(((exato, len(item.chave), item.codigo), item))
    achados.sort(key=lambda par: par[0])
    return Resultado(len(achados), tuple(item for _chave, item in achados[:limite]))


@lru_cache(maxsize=1)
def _sinonimos(caminho: str = str(ALIASES_PATH)) -> dict[str, str]:
    raw = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {normalizar(k): v for k, v in raw.items() if not k.startswith("_")}


def _colapsar(texto: str) -> str:
    """Letras repetidas viram uma so (appendectomy ~ apendicectomia)."""
    return re.sub(r"(.)\1+", r"\1", texto)


def _dobrar_en(texto: str) -> str:
    """Aproxima a grafia inglesa da portuguesa (ph/f, th/t, ch/c, y/i, k/c, ae-oe/e e letras dobradas)."""
    texto = texto.replace("ph", "f").replace("th", "t").replace("ch", "c").replace("ae", "e").replace("oe", "e").replace("y", "i").replace("k", "c")
    return _colapsar(texto)


def _cognatos(texto: str, palavras: frozenset[str]) -> list[Candidato]:
    por_sufixo: dict[str, list[str]] = {}
    for palavra in palavras:
        for pt in set(_FINAIS.values()):
            if palavra.endswith(pt):
                por_sufixo.setdefault(pt, []).append(palavra)
    achados: dict[str, Candidato] = {}
    for casou in _PALAVRA_EN.finditer(normalizar(texto)):
        base = _dobrar_en(casou.group(1))
        for palavra in sorted(por_sufixo.get(_FINAIS[casou.group(2)], ())):
            raiz = _colapsar(palavra)[: -len(_FINAIS[casou.group(2)])]
            if raiz.startswith(base) and len(raiz) - len(base) <= MAX_DIFERENCA:
                achados.setdefault(palavra, Candidato(palavra, casou.group(0), "cognato", False))
    return list(achados.values())


def candidatos(texto: str, *, instantaneo: Instantaneo | None = None) -> list[Candidato]:
    """Procedimentos e tecnicas que o texto (em ingles) parece citar. Os por sinonimo vem primeiro."""
    data = instantaneo or carregar()
    normalizado = f" {normalizar(texto)} "
    if len(normalizado) < 10:
        return []
    vistos: set[str] = set()
    saida: list[Candidato] = []
    for en, pt in _sinonimos().items():
        if f" {en} " in normalizado and pt not in vistos:
            vistos.add(pt)
            saida.append(Candidato(pt, en, "sinonimo", True))
    for item in _cognatos(texto, data.palavras):
        if item.termo not in vistos:
            vistos.add(item.termo)
            saida.append(item)
    return saida[:MAX_CANDIDATES]
