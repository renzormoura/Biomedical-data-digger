"""Renderizador de Markdown minimo e seguro (sem dependencias).

Cobre o que as respostas do LLM e os textos do app usam: titulos, negrito, italico,
codigo, listas, citacoes, linhas horizontais e links http(s). Todo texto e escapado
ANTES de qualquer marcacao ser aplicada, entao HTML injetado (por um abstract hostil
ou pela propria resposta do modelo) nunca chega ao navegador como marcacao.
"""

from __future__ import annotations

import html
import re

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_HR = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_UL = re.compile(r"^\s*[-*+]\s+(.*)$")
_OL = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_QUOTE = re.compile(r"^\s*>\s?(.*)$")
_FENCE = re.compile(r"^\s*```")

_CODE = re.compile(r"`([^`\n]+)`")
_BOLD = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*|__(?=\S)(.+?)(?<=\S)__")
_ITALIC = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])|(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])")
_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")


def _inline(text: str) -> str:
    escaped = html.escape(text, quote=True)
    placeholders: list[str] = []

    def stash(fragment: str) -> str:
        placeholders.append(fragment)
        return f"\x00{len(placeholders) - 1}\x00"

    escaped = _CODE.sub(lambda m: stash(f"<code>{m.group(1)}</code>"), escaped)
    escaped = _LINK.sub(
        lambda m: stash(f'<a href="{m.group(2)}" target="_blank" rel="noopener noreferrer">{m.group(1)}</a>'),
        escaped,
    )
    escaped = _BOLD.sub(lambda m: f"<strong>{m.group(1) or m.group(2)}</strong>", escaped)
    escaped = _ITALIC.sub(lambda m: f"<em>{m.group(1) or m.group(2)}</em>", escaped)
    return re.sub(r"\x00(\d+)\x00", lambda m: placeholders[int(m.group(1))], escaped)


def render(markdown: str) -> str:
    """Converte `markdown` em HTML seguro."""
    lines = (markdown or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    paragraph: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            out.append("<p>" + "<br>".join(_inline(line) for line in paragraph) + "</p>")
            paragraph.clear()

    while index < len(lines):
        line = lines[index]

        if _FENCE.match(line):
            flush_paragraph()
            block: list[str] = []
            index += 1
            while index < len(lines) and not _FENCE.match(lines[index]):
                block.append(lines[index])
                index += 1
            out.append("<pre><code>" + html.escape("\n".join(block)) + "</code></pre>")
            index += 1
            continue

        if not line.strip():
            flush_paragraph()
            index += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            out.append(f"<h{level}>{_inline(heading.group(2).strip())}</h{level}>")
            index += 1
            continue

        if _HR.match(line):
            flush_paragraph()
            out.append("<hr>")
            index += 1
            continue

        if _QUOTE.match(line):
            flush_paragraph()
            quoted: list[str] = []
            while index < len(lines) and _QUOTE.match(lines[index]):
                quoted.append(_QUOTE.match(lines[index]).group(1))  # type: ignore[union-attr]
                index += 1
            out.append("<blockquote>" + render("\n".join(quoted)) + "</blockquote>")
            continue

        for pattern, tag in ((_UL, "ul"), (_OL, "ol")):
            if pattern.match(line):
                flush_paragraph()
                items: list[str] = []
                while index < len(lines) and pattern.match(lines[index]):
                    items.append("<li>" + _inline(pattern.match(lines[index]).group(1)) + "</li>")  # type: ignore[union-attr]
                    index += 1
                out.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
                break
        else:
            paragraph.append(line)
            index += 1
            continue

    flush_paragraph()
    return "\n".join(out)
