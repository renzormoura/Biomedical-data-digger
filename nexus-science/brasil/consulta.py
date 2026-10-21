"""Consulta unificada das bases do Brasil (ANVISA + CONITEC + RENAME) por substancia, sem IA e sem rede."""

from __future__ import annotations

from dataclasses import dataclass

from brasil import anvisa, conitec, rename
from brasil.nomes import Candidato, encontrar, normalizar

MAX_CANDIDATES = 8


@dataclass(frozen=True)
class Situacao:
    candidato: Candidato | None  # None na busca manual
    termo: str  # nome buscado, normalizado
    anvisa: tuple[anvisa.Substancia, ...]
    conitec: tuple[conitec.Registro, ...]
    rename: tuple[rename.Registro, ...] = ()


def normalizar_termo(texto: str) -> str:
    """Termo de busca manual normalizado (sem acento, minusculas)."""
    return normalizar(texto)


def vocabulario(
    anvisa_data: anvisa.Instantaneo, conitec_data: conitec.Instantaneo, rename_data: rename.Instantaneo | None = None,
) -> dict[str, str]:
    """Uniao dos nomes das bases (termo normalizado -> exibicao)."""
    uniao = dict(anvisa_data.vocabulario)
    for extra in (conitec_data.vocabulario, rename_data.vocabulario if rename_data else {}):
        for termo, nome in extra.items():
            uniao.setdefault(termo, nome)
    return uniao


def situacao(
    termo: str, anvisa_data: anvisa.Instantaneo, conitec_data: conitec.Instantaneo, candidato: Candidato | None = None,
    rename_data: rename.Instantaneo | None = None,
) -> Situacao:
    return Situacao(
        candidato=candidato, termo=termo,
        anvisa=tuple(anvisa.buscar(termo, instantaneo=anvisa_data)),
        conitec=tuple(conitec.buscar(termo, instantaneo=conitec_data)),
        rename=tuple(rename.buscar(termo, instantaneo=rename_data)) if rename_data else (),
    )


def situacoes_do_texto(
    texto: str, anvisa_data: anvisa.Instantaneo, conitec_data: conitec.Instantaneo, rename_data: rename.Instantaneo | None = None,
) -> list[Situacao]:
    """Substancias que o texto em ingles parece citar, com o que cada base diz (cada uma a confirmar)."""
    achados = encontrar(texto, vocabulario(anvisa_data, conitec_data, rename_data), limite=MAX_CANDIDATES)
    return [situacao(c.termo, anvisa_data, conitec_data, c, rename_data) for c in achados]
