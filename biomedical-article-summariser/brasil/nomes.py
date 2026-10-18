"""Nomes de substancias: normalizacao, remocao de sais e formas, e ligacao ingles-portugues.

Compartilhado pelas bases do Brasil (Conitec, ANVISA...). A ligacao de um texto em ingles a nomes em portugues
usa, nesta ordem: (1) tabela curada de sinonimos e (2) cognatos por regras de sufixo e de grafia (ph/f, y/i, th/t, ll/l).
Toda ligacao e apenas uma *possivel correspondencia*. A forma aproximada (distancia de edicao) foi REMOVIDA: ela
casava "valganciclovir" com "valaciclovir", que sao medicamentos diferentes; preferimos perder recall a errar a substancia.
"""

from __future__ import annotations

import itertools
import json
import re
import unicodedata
from dataclasses import dataclass
from functools import cache, lru_cache
from pathlib import Path

ALIASES_PATH = Path(__file__).resolve().parent.parent / "dados_brasil" / "aliases_en_pt.json"
MAX_FORMS = 40

# (terminacao em portugues, terminacao em ingles): cognatos de nomes de substancias (DCB x INN)
_SUFFIXES = (
    ("ina", "ine"), ("ina", "in"), ("ida", "ide"), ("ona", "one"), ("ato", "ate"), ("ico", "ic"), ("ila", "yl"),
    ("ano", "ane"), ("eno", "ene"), ("ito", "ite"), ("ose", "ose"), ("abe", "ab"), ("ibe", "ib"), ("ol", "ol"),
    ("ia", "y"), ("ica", "ic"), ("ila", "il"), ("ase", "ase"),
)
_FORMAS = {
    "granulado", "injetavel", "adesivo", "transdermico", "oral", "comprimido", "comprimidos", "solucao", "capsula",
    "xarope", "pomada", "colirio", "inalatoria", "topico", "topica", "monoidratado", "monoidratada", "diidratado",
    "diidratada", "hexaidratado", "hexaidratada", "anidro", "anidra", "micronizado", "micronizada", "calcica", "calcico",
    "sodica", "sodico", "potassica", "potassico", "magnesica", "magnesico", "base", "liberacao", "prolongada",
}
_SAIS = (
    "cloridrato|bromidrato|sulfato|fosfato|acetato|succinato|maleato|tartarato|mesilato|besilato|fumarato|citrato|nitrato|"
    "carbonato|oxalato|valerato|propionato|dipropionato|benzoato|lactato|gluconato|tosilato|estearato|palmitato|pamoato|"
    "cipionato|enantato|decanoato|hemifumarato|hemitartarato|cloreto|brometo|iodeto|hidroxido|oxido"
)
_SAL = re.compile(rf"^(?:di|tri|mono|hemi)?(?:{_SAIS})\sde\s", re.IGNORECASE)
_ELEMENTOS = {"sodio", "potassio", "calcio", "magnesio", "zinco", "ferro", "litio", "aluminio", "cobre", "prata", "amonio", "bario", "cobalto"}
# termos que em artigos aparecem como exame, elemento ou palavra comum, nao como medicamento: nunca viram candidatos
AMBIGUOS = frozenset({
    "glicose", "glucose", "alanina", "tirosina", "fosforo", "enxofre", "sulfato", "dimetila", "oxigenio", "nitrogenio", "agua",
    "sodio", "potassio", "calcio", "ferro", "zinco", "cobre", "magnesio", "colesterol", "creatinina", "ureia", "albumina",
    "lactato", "acetato", "citrato", "carbonato", "haemolyticus", "hemoglobina", "glicina", "glutamina", "lisina", "serina",
    "phosphorus", "sulphur", "sulfur", "sulphate", "oxygen", "nitrogen", "water",
})


def normalizar(texto: str) -> str:
    """Minusculas, sem acento, so letras e numeros separados por um espaco."""
    base = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", base).strip()


def dobrar(texto: str) -> str:
    """Dobra grafias equivalentes entre ingles e portugues (ph/f, th/t, ll/l, y/i, ck/c, k/c) para comparar cognatos."""
    return re.sub(r"ph", "f", texto).replace("th", "t").replace("ll", "l").replace("ck", "c").replace("y", "i").replace("k", "c")


def limpar_substancia(nome: str) -> str:
    """Tira sal ('cloridrato de'), forma farmaceutica ('injetavel') e adjetivos de sal ('calcica'); preserva 'cloreto de sodio'."""
    nome = nome.strip()
    sem_sal = _SAL.sub("", nome)
    if sem_sal != nome and normalizar(sem_sal) not in _ELEMENTOS:
        nome = sem_sal
    palavras = nome.split()
    while len(palavras) > 1 and normalizar(palavras[-1]) in _FORMAS:
        palavras.pop()
    return " ".join(palavras)


@lru_cache(maxsize=1)
def aliases(caminho: str = str(ALIASES_PATH)) -> dict[str, str]:
    raw = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return {normalizar(k): normalizar(v) for k, v in raw.items() if not k.startswith("_")}


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


@cache
def _formas(termo: str) -> tuple[str, ...]:
    """Formas inglesas de um nome (ordenadas); em cache, pois o vocabulario e o mesmo a cada texto analisado."""
    return tuple(sorted(formas_inglesas(termo)))


@cache
def _formas_dobradas(termo: str) -> tuple[str, ...]:
    return tuple(sorted(formas_inglesas(dobrar(termo))))


@dataclass(frozen=True)
class Candidato:
    pt: str  # nome em portugues, como aparece nos dados
    en: str  # trecho do texto que originou a ligacao
    metodo: str  # "sinonimo" ou "cognato"
    termo: str  # nome normalizado (chave de busca)


def encontrar(texto: str, vocabulario: dict[str, str], *, limite: int) -> list[Candidato]:
    """Substancias do vocabulario (termo normalizado -> nome de exibicao) que o texto em ingles parece citar."""
    normalizado = f" {normalizar(texto)} "
    if len(normalizado) < 10:
        return []
    dobrado = f" {dobrar(normalizado.strip())} "
    sinonimos = aliases()
    por_termo: dict[str, list[str]] = {}
    for en, pt in sinonimos.items():
        if f" {en} " in normalizado:
            por_termo.setdefault(pt, []).append(en)
    achados: dict[str, Candidato] = {}
    for termo, exibicao in vocabulario.items():
        if termo in AMBIGUOS:
            continue
        if termo in por_termo:
            achados[termo] = Candidato(exibicao, por_termo[termo][0], "sinonimo", termo)
            continue
        casou = next((f for f in _formas(termo) if f" {f} " in normalizado), None)
        if casou is None:
            casou_dobrado = next((f for f in _formas_dobradas(termo) if f" {f} " in dobrado), None)
            casou = next((w for w in normalizado.split() if dobrar(w) == casou_dobrado), None) if casou_dobrado and " " not in casou_dobrado else casou_dobrado
        if casou:
            achados[termo] = Candidato(exibicao, casou, "cognato", termo)
            continue
    ordenados = sorted(achados.values(), key=lambda c: (-normalizado.count(f" {c.en} "), c.pt))
    return ordenados[:limite]
