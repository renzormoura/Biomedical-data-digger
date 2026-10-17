"""Consulta unificada das bases do Brasil (ANVISA + CONITEC) por substancia, sem IA e sem rede."""

from __future__ import annotations

from dataclasses import dataclass

from brasil import anvisa, conitec
from brasil.nomes import Candidato, encontrar, normalizar

MAX_CANDIDATES = 8


@dataclass(frozen=True)
class Situacao:
    candidato: Candidato | None  # None na busca manual
    termo: str  # nome buscado, normalizado
    anvisa: tuple[anvisa.Substancia, ...]
    conitec: tuple[conitec.Registro, ...]


def normalizar_termo(texto: str) -> str:
    """Termo de busca manual normalizado (sem acento, minusculas)."""
    return normalizar(texto)


def vocabulario(anvisa_data: anvisa.Instantaneo, conitec_data: conitec.Instantaneo) -> dict[str, str]:
    """Uniao dos nomes das duas bases (termo normalizado -> exibicao)."""
    uniao = dict(anvisa_data.vocabulario)
    for termo, nome in conitec_data.vocabulario.items():
        uniao.setdefault(termo, nome)
    return uniao


def situacao(termo: str, anvisa_data: anvisa.Instantaneo, conitec_data: conitec.Instantaneo, candidato: Candidato | None = None) -> Situacao:
    return Situacao(
        candidato=candidato, termo=termo,
        anvisa=tuple(anvisa.buscar(termo, instantaneo=anvisa_data)),
        conitec=tuple(conitec.buscar(termo, instantaneo=conitec_data)),
    )


def situacoes_do_texto(texto: str, anvisa_data: anvisa.Instantaneo, conitec_data: conitec.Instantaneo) -> list[Situacao]:
    """Substancias que o texto em ingles parece citar, com o que cada base diz (cada uma a confirmar)."""
    achados = encontrar(texto, vocabulario(anvisa_data, conitec_data), limite=MAX_CANDIDATES)
    return [situacao(c.termo, anvisa_data, conitec_data, c) for c in achados]
