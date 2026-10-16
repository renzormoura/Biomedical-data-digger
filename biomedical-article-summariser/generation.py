"""Opcoes de geracao (temperatura, esforco de raciocinio, teto de saida) e a politica que as escolhe.

O teto de saida e uma protecao contra respostas descontroladas, nao um orcamento apertado:
em modelos de raciocinio os tokens de raciocinio contam como saida, entao tetos baixos
demais deixam o modelo sem espaco para a resposta (detectado como `truncated`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

VALID_REASONING_EFFORTS = ("low", "medium", "high")

DEFAULT_MAX_TOKENS_BY_DETAIL: dict[str, int] = {
    "Resumido": 1500,
    "Completo": 3000,
    "Ultra-detalhado": 4500,
}
DEFAULT_MAX_TOKENS = 2200


@dataclass(frozen=True)
class GenerationOptions:
    temperature: float | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None  # so e aplicado a modelos que o aceitam


@dataclass(frozen=True)
class GenerationPolicy:
    temperature: float | None = 0.2
    reasoning_effort: str | None = None
    default_max_tokens: int = DEFAULT_MAX_TOKENS
    max_tokens_by_detail: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_MAX_TOKENS_BY_DETAIL))

    def __post_init__(self) -> None:
        if self.reasoning_effort is not None and self.reasoning_effort not in VALID_REASONING_EFFORTS:
            raise ValueError(f"reasoning_effort deve ser um de {VALID_REASONING_EFFORTS}.")
        if self.temperature is not None and not 0 <= self.temperature <= 2:
            raise ValueError("temperature deve estar entre 0 e 2.")
        if self.default_max_tokens < 256:
            raise ValueError("default_max_tokens deve ser >= 256.")

    def for_detail(self, detail: str = "", reasoning_effort: str | None = None) -> GenerationOptions:
        """Opcoes para um nivel de detalhe; `reasoning_effort` sobrepoe o padrao da politica."""
        effort = reasoning_effort or self.reasoning_effort
        if effort is not None and effort not in VALID_REASONING_EFFORTS:
            raise ValueError(f"reasoning_effort deve ser um de {VALID_REASONING_EFFORTS}.")
        return GenerationOptions(
            temperature=self.temperature,
            max_output_tokens=self.max_tokens_by_detail.get(detail, self.default_max_tokens),
            reasoning_effort=effort,
        )
