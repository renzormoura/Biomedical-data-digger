"""Consulta ao instantaneo da CONITEC (recomendacoes sobre medicamentos), sem IA e sem rede.

Duas operacoes:
- `buscar`: decisoes da Conitec para uma substancia em portugues (casamento por palavra inteira, sem acento);
- `candidatos`: substancias que um texto em INGLES parece citar, ligando o nome em ingles ao nome em portugues
  por (1) tabela curada de sinonimos, (2) regras de cognatos de sufixo (-ine/-ina, -ide/-ida...) e (3) forma
  aproximada em palavras longas. Toda ligacao e apenas uma *possivel correspondencia*: a interface sempre pede
  confirmacao e mostra o metodo usado.
"""

from __future__ import annotations

import difflib
import itertools
import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "dados_brasil" / "conitec.json"
ALIASES_PATH = Path(__file__).resolve().parent.parent / "dados_brasil" / "aliases_en_pt.json"
STALE_AFTER_DAYS = 60
MIN_TERM_CHARS = 5
FUZZY_MIN_CHARS = 9
FUZZY_CUTOFF = 0.9
MAX_CANDIDATES = 8
MAX_FORMS = 40

# trechos que encerram o nome da substancia dentro do texto da tecnologia ("X para tratamento de Y")
_CUTS = re.compile(r"\s(?:para|em|como|no|na|nos|nas|versus|ou|via|associad[oa]s?|conforme|segundo)\s|\s\(|\s-\s|:", re.IGNORECASE)
_SPLITS = re.compile(r"(?<!\d),(?!\d)|;|\s\+\s|\se\s(?:o|a|os|as)?\s?|\scom\s|\sem\scombina[cç][aã]o\scom\s", re.IGNORECASE)
_UNITS = {"mg", "g", "ml", "mcg", "ui", "kg", "dose", "doses", "mg/ml", "comprimido", "comprimidos", "injetavel", "oral", "solucao"}
_ARTICLES = {"o", "a", "os", "as", "de", "do", "da"}
# (terminacao em portugues, terminacao em ingles): regras de cognatos de nomes de substancias (DCB x INN)
_SUFFIXES = (
    ("ina", "ine"), ("ina", "in"), ("ida", "ide"), ("ona", "one"), ("ato", "ate"), ("ico", "ic"), ("ila", "yl"),
    ("ano", "ane"), ("eno", "ene"), ("ito", "ite"), ("ose", "ose"), ("abe", "ab"), ("ibe", "ib"), ("ol", "ol"),
    ("ia", "y"), ("ica", "ic"), ("ila", "il"), ("ase", "ase"),
)


def normalizar(texto: str) -> str:
    """Minusculas, sem acento, so letras e numeros separados por um espaco."""
    base = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", base).strip()


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
class Candidato:
    pt: str  # nome em portugues, como aparece nos dados
    en: str  # trecho do texto que originou a ligacao
    metodo: str  # "sinonimo", "cognato" ou "aproximado"
    termo: str  # nome normalizado (chave de busca)


@dataclass(frozen=True)
class Instantaneo:
    meta: dict[str, object]
    registros: tuple[Registro, ...]
    vocabulario: dict[str, str]  # termo normalizado -> nome de exibicao


_FORMAS = {"granulado", "injetavel", "adesivo", "transdermico", "oral", "comprimido", "comprimidos", "solucao", "capsula", "xarope", "pomada", "colirio", "inalatoria", "topico", "topica"}
_SAL = re.compile(r"^(?:di|tri)?(?:cloridrato|bromidrato|sulfato|fosfato|acetato|succinato|maleato|tartarato|mesilato|besilato|fumarato|citrato|nitrato|carbonato)\sde\s", re.IGNORECASE)


def _limpo(nome: str) -> str:
    """Tira sal ('dicloridrato de') e forma farmaceutica ('injetavel', 'granulado') do nome da substancia."""
    nome = _SAL.sub("", nome.strip())
    palavras = nome.split()
    while len(palavras) > 1 and normalizar(palavras[-1]) in _FORMAS:
        palavras.pop()
    return " ".join(palavras)


def _termos(tecnologia: str) -> list[str]:
    """Nomes de substancias contidos no texto da tecnologia (original, com acentos)."""
    sem_parenteses = re.sub(r"\([^)]*\)", " ", tecnologia)  # "(DMSA, succimer)" e afins
    nomes: list[str] = []
    for pedaco in _SPLITS.split(sem_parenteses.strip()):
        nome = _CUTS.split(pedaco.strip(), maxsplit=1)[0].strip(" .")
        palavras = [w for w in nome.split() if not re.fullmatch(r"[\d.,%/]+", w) and w.lower() not in _UNITS]
        while palavras and palavras[0].lower() in _ARTICLES:
            palavras.pop(0)
        nome = _limpo(" ".join(palavras))
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


@lru_cache(maxsize=1)
def aliases(caminho: str = str(ALIASES_PATH)) -> dict[str, str]:
    raw = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {normalizar(k): normalizar(v) for k, v in raw.items() if not k.startswith("_")}


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


def formas_inglesas(termo: str) -> set[str]:
    """Formas em ingles plausiveis para um nome em portugues (ja normalizado), por regras de cognatos."""
    palavras = termo.split()
    opcoes: list[list[str]] = []
    prefixo_acido = palavras[0] == "acido" and len(palavras) > 1
    for palavra in palavras[1:] if prefixo_acido else palavras:
        formas = {palavra}
        for pt, en in _SUFFIXES:
            if palavra.endswith(pt) and len(palavra) > len(pt) + 2:
                formas.add(palavra[: -len(pt)] + en)
        if len(palavra) > 5 and palavra[-1] in "aeo":
            formas.add(palavra[:-1])
        opcoes.append(sorted(formas))
    resultado: set[str] = set()
    for combinacao in itertools.islice(itertools.product(*opcoes), MAX_FORMS):
        frase = " ".join(combinacao)
        resultado.add(f"{frase} acid" if prefixo_acido else frase)
    return resultado


def candidatos(texto: str, *, instantaneo: Instantaneo | None = None) -> list[Candidato]:
    """Substancias do vocabulario da Conitec que o texto (em ingles) parece citar, com o metodo da ligacao."""
    data = instantaneo or carregar()
    normalizado = f" {normalizar(texto)} "
    if len(normalizado) < 10:
        return []
    palavras_longas = sorted({w for w in normalizado.split() if len(w) >= FUZZY_MIN_CHARS})
    achados: dict[str, Candidato] = {}
    sinonimos = aliases()
    for termo, exibicao in data.vocabulario.items():
        if termo in achados:
            continue
        en_sinonimos = [en for en, pt in sinonimos.items() if pt == termo and f" {en} " in normalizado]
        if en_sinonimos:
            achados[termo] = Candidato(exibicao, en_sinonimos[0], "sinonimo", termo)
            continue
        casou = next((f for f in sorted(formas_inglesas(termo)) if f" {f} " in normalizado), None)
        if casou:
            achados[termo] = Candidato(exibicao, casou, "cognato", termo)
            continue
        if " " not in termo and len(termo) >= FUZZY_MIN_CHARS:
            proximas = [w for w in palavras_longas if w[:3] == termo[:3] and abs(len(w) - len(termo)) <= 2]
            perto = difflib.get_close_matches(termo, proximas, n=1, cutoff=FUZZY_CUTOFF)
            if perto:
                achados[termo] = Candidato(exibicao, perto[0], "aproximado", termo)
    ordenados = sorted(achados.values(), key=lambda c: (-normalizado.count(f" {c.en} "), c.pt))
    return ordenados[:MAX_CANDIDATES]
