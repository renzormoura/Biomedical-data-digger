import pytest
from hypothesis import given
from hypothesis import strategies as st

from markdown_lite import render


def test_headings_lists_and_emphasis():
    html = render("## Titulo\n\n- um\n- **dois**\n\n1. a\n2. b\n\ntexto *itálico* e `codigo`")
    assert "<h2>Titulo</h2>" in html
    assert "<ul><li>um</li><li><strong>dois</strong></li></ul>" in html
    assert "<ol><li>a</li><li>b</li></ol>" in html
    assert "<em>itálico</em>" in html and "<code>codigo</code>" in html


def test_blockquote_hr_and_paragraph_breaks():
    html = render("---\n> **Sumário**  ·  Filtros: *Padrão*\n\n---\ntexto")
    assert html.count("<hr>") == 2
    assert "<blockquote>" in html and "<strong>Sumário</strong>" in html
    assert render("linha 1\nlinha 2") == "<p>linha 1<br>linha 2</p>"


def test_fenced_code_is_escaped_and_not_interpreted():
    html = render("```\n<b>x</b> **y**\n```")
    assert "&lt;b&gt;x&lt;/b&gt; **y**" in html and "<strong>" not in html


@pytest.mark.parametrize(
    "hostile",
    [
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "**<b onmouseover=alert(1)>x</b>**",
        "[clique](javascript:alert(1))",
        "[clique](data:text/html;base64,AAAA)",
        "`<script>`",
        "> <iframe src=//evil></iframe>",
        "# <svg onload=alert(1)>",
        "- <a href='x' onclick='y'>l</a>",
    ],
)
def test_no_html_or_script_ever_survives(hostile):
    import re

    html = render(hostile)
    allowed = {"p", "br", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "ul", "ol", "li", "blockquote", "pre", "code", "strong", "em", "a"}
    assert set(re.findall(r"</?([a-zA-Z0-9]+)", html)) <= allowed
    assert 'href="javascript' not in html and 'href="data' not in html
    assert not re.search(r"<[a-z]+ [^>]*\bon\w+=", html)


def test_only_http_links_become_anchors_with_safe_rel():
    html = render("[ok](https://example.com/a?b=1) e [ruim](javascript:alert(1))")
    assert '<a href="https://example.com/a?b=1" target="_blank" rel="noopener noreferrer">ok</a>' in html
    assert "href=\"javascript" not in html


def test_quotes_in_link_text_cannot_break_attributes():
    html = render('[x" onclick="evil](https://example.com)')
    assert 'onclick="evil' not in html


def test_empty_input():
    assert render("") == "" and render(None) == ""  # type: ignore[arg-type]


@given(st.text(max_size=400))
def test_output_never_contains_raw_user_angle_brackets(text):
    html = render(text)
    # qualquer "<" no resultado pertence a uma tag da lista permitida
    import re

    allowed = {"p", "br", "h1", "h2", "h3", "h4", "h5", "h6", "hr", "ul", "ol", "li", "blockquote", "pre", "code", "strong", "em", "a"}
    tags = set(re.findall(r"</?([a-zA-Z0-9]+)", html))
    assert tags <= allowed
    assert not re.search(r"<a [^>]*on\w+=", html)


def test_nul_characters_cannot_forge_internal_placeholders():
    # regressao: "\x000\x00" casava com o marcador interno e levantava IndexError
    for hostile in ("\x000\x00", "a\x001\x00b `x`", "\x00\x00\x00 **\x0099\x00**", "[l](https://a.b) \x005\x00"):
        html = render(hostile)
        assert "\x00" not in html
