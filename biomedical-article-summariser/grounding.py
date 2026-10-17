"""Verificacao deterministica de que numeros da resposta existem na fonte.

LLMs podem inventar valores numericos (doses, percentuais, p-values). Esta
checagem nao prova que a resposta esta correta, mas detecta o sintoma mais
perigoso de forma barata e sem outro LLM: numeros citados que nao aparecem no
titulo/abstract fornecidos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_NUMBER = r"\d+(?:[.,]\d+)?"
_UNITS = (
    r"%|mg/kg|mg/dl|mg/ml|mg|mcg|µg|ug|g/dl|g|kg|ml|mL|dl|UI|U|mmol|mEq|mmHg|"
    r"bpm|h|horas?|min|dias?|semanas?|meses|anos?|vezes"
)
# Decimais, percentuais e numeros com unidade: os que carregam informacao clinica.
_SIGNIFICANT = re.compile(
    rf"(?<![\w.])(?:{_NUMBER}\s?(?:{_UNITS})(?![A-Za-z])|\d+[.,]\d+)",
    re.IGNORECASE,
)
_ANY_NUMBER = re.compile(rf"(?<![\w.]){_NUMBER}")


def _canonical(token: str) -> str:
    return re.sub(r"\s+", "", token.lower()).replace(",", ".")


def _numeric_part(token: str) -> str:
    match = re.match(_NUMBER, _canonical(token))
    return match.group(0) if match else ""


@dataclass(frozen=True)
class GroundingReport:
    ungrounded: list[str]

    @property
    def ok(self) -> bool:
        return not self.ungrounded

    def to_markdown(self) -> str:
        if self.ok:
            return ""
        listed = ", ".join(f"`{item}`" for item in self.ungrounded[:12])
        return (
            "\n\n---\n> **Verificação automática de números:** os valores abaixo aparecem na "
            f"resposta mas **não foram encontrados** no título/resumo-fonte: {listed}. "
            "Confira no artigo original antes de usar."
        )


def check_numeric_grounding(response: str, source: str) -> GroundingReport:
    """Lista numeros relevantes da `response` ausentes de `source`."""
    source_numbers = {_numeric_part(m.group(0)) for m in _ANY_NUMBER.finditer(source)}
    seen: list[str] = []
    for match in _SIGNIFICANT.finditer(response):
        token = match.group(0).strip()
        if _numeric_part(token) not in source_numbers and token not in seen:
            seen.append(token)
    return GroundingReport(ungrounded=seen)
