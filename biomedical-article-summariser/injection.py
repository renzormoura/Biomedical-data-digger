"""Deteccao e neutralizacao de instrucoes escondidas no texto-fonte (prompt injection).

Defesa em codigo, complementar ao prompt: a avaliacao com o modelo real mostrou que so o
prompt falha em ~20% das tentativas. Aqui removemos, antes de chamar o modelo, as frases
que parecem ordens ao modelo e avisamos o usuario. Os padroes sao propositalmente
estreitos (exigem formato imperativo) para nao apagar frases cientificas legitimas, como
"patients respond with improvement".

Limite honesto: heuristica nao cobre todo ataque; a validacao de saida (tamanho minimo e
checagem de numeros) e o aviso ao usuario continuam necessarios.
"""

from __future__ import annotations

import re

_PATTERNS = [
    r"ignore\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above|earlier|preceding)\s+"
    r"(?:instructions?|prompts?|rules?|directions?)",
    r"disregard\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above|earlier)\s+(?:instructions?|rules?)",
    r"forget\s+(?:all\s+|everything\s+|your\s+)?(?:previous|prior|above)\s+(?:instructions?|rules?)",
    r"(?:^|\n)\s*(?:system|assistant|developer)\s*:",
    r"\byou\s+are\s+now\s+(?:a|an|the|in)\b",
    r"\b(?:reply|respond|answer|output|say)\s+only\s+with\b",
    r"\b(?:reply|respond|answer)\s+with\s+(?:only|just|exactly)\b",
    r"\b(?:reveal|print|show|repeat|leak)\s+(?:me\s+)?(?:the\s+|your\s+)?(?:system\s+|hidden\s+|initial\s+)?"
    r"(?:prompt|instructions)\b",
    r"<\s*/?\s*(?:system|instructions?)\s*>",
    r"\b(?:ignore|ignorar|desconsidere|esque[cç]a)\s+(?:todas\s+)?(?:as\s+)?(?:instru[cç][õo]es|regras)\s+"
    r"(?:anteriores|acima)",
    r"\bresponda\s+apenas\s+com\b",
    r"\b(?:revele|mostre)\s+(?:o\s+)?(?:seu\s+)?prompt\b",
]
_COMPILED = [re.compile(pattern, re.IGNORECASE) for pattern in _PATTERNS]
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")

REMOVED_MARKER = "[trecho removido]"


def _looks_like_instruction(sentence: str) -> bool:
    return any(pattern.search(sentence) for pattern in _COMPILED)


def find_injection_attempts(text: str) -> list[str]:
    """Frases do texto que parecem instrucoes ao modelo (no maximo 5)."""
    found = [s.strip() for s in _SENTENCE_SPLIT.split(text or "") if s and _looks_like_instruction(s)]
    return found[:5]


def neutralize(text: str) -> tuple[str, int]:
    """Remove as frases suspeitas. Retorna (texto_limpo, quantidade_removida)."""
    if not text:
        return text, 0
    kept: list[str] = []
    removed = 0
    for sentence in _SENTENCE_SPLIT.split(text):
        if not sentence:
            continue
        if _looks_like_instruction(sentence):
            removed += 1
        else:
            kept.append(sentence)
    if removed == 0:
        return text, 0
    return " ".join(kept).strip(), removed
