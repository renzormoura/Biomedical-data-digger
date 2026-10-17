"""Documentos para baixar: resumo, ficha de leitura, referencia e texto completo aberto.

Tudo parte de uma representacao simples em blocos (titulo, metadados, secoes, paragrafos, citacoes,
itens) que vira TXT, Markdown, HTML ou DOCX, sem dependencias externas. O texto vem do registro e,
no caso do texto completo, da Europe PMC (so artigos de acesso aberto); nada e gerado por IA e nada
e raspado de paginas de editoras. PDF de editora nao passa por aqui: a interface apenas leva o
usuario ao link aberto que a fonte informa.
"""

from __future__ import annotations

import io
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import date
from html import escape
from xml.etree.ElementTree import Element
from xml.sax.saxutils import escape as xml_escape

import requests
from loguru import logger

from catalog import CatalogError, Work
from xmlutil import parse_xml, text_of

Block = tuple[str, str]  # (tipo, texto); tipos: title, meta, h1, h2, h3, p, quote, li

FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
MAX_FULLTEXT_BYTES = 15_000_000
HTTP_TIMEOUT = 25
USER_AGENT = "BiomedicalDataDigger/1.0 (navegador de artigos)"
_PMC = re.compile(r"^PMC\d{1,10}$")
_XML_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")
_FILENAME_BAD = re.compile(r"[^a-z0-9]+")

TEXT_FORMATS = {
    "txt": ("Texto (.txt)", "text/plain", "txt"),
    "md": ("Markdown (.md)", "text/markdown", "md"),
    "html": ("Página web (.html)", "text/html", "html"),
    "docx": ("Word (.docx)", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx"),
}
KIND_FORMATS: dict[str, tuple[str, ...]] = {
    "abstract": ("txt", "md", "html", "docx", "json"),
    "sheet": ("txt", "md", "html", "docx", "json"),
    "fulltext": ("txt", "md", "html", "docx", "xml"),
}
CITATION_FORMATS = ("bibtex", "ris", "abnt", "apa", "vancouver")


# ------------------------------------------------------------------ nomes de arquivo
def safe_filename(work: Work, label: str, extension: str) -> str:
    base = unicodedata.normalize("NFKD", work.title).encode("ascii", "ignore").decode().lower()
    slug = _FILENAME_BAD.sub("-", base).strip("-")[:60].strip("-") or "artigo"
    year = f"-{work.year}" if work.year else ""
    return f"{slug}{year}-{label}.{extension}"


# ------------------------------------------------------------------ montagem dos blocos
def _identity_lines(work: Work) -> list[str]:
    lines = []
    if work.authors:
        lines.append(", ".join(f"{a.given} {a.family}".strip() for a in work.authors))
    journal = ", ".join(p for p in [work.journal, f"v. {work.volume}" if work.volume else "",
                                    f"n. {work.issue}" if work.issue else "", f"p. {work.pages}" if work.pages else ""] if p)
    lines.append(" · ".join(p for p in [journal, str(work.year or "")] if p))
    ids = [f"DOI: https://doi.org/{work.doi}" if work.doi else "", f"PMID: {work.pmid}" if work.pmid else "",
           f"PMCID: {work.pmcid}" if work.pmcid else ""]
    lines.append(" · ".join(i for i in ids if i))
    if work.study_types:
        lines.append("Tipo de estudo: " + ", ".join(work.study_types))
    lines.append(f"Fonte: {work.source}" if work.source else "")
    return [line for line in lines if line]


def _footer(work: Work, what: str) -> list[Block]:
    return [("meta", f"{what} gerado em {date.today():%d/%m/%Y} pelo Biomedical Data Digger a partir do registro "
                     f"{work.source or 'da fonte'}. O texto foi copiado do registro; nada foi gerado por IA.")]


def abstract_blocks(work: Work, sections: list[tuple[str, str]]) -> list[Block]:
    blocks: list[Block] = [("title", work.title), *[("meta", line) for line in _identity_lines(work)], ("h1", "Resumo")]
    if sections:
        for heading, text in sections:
            blocks += [("h2", heading), ("p", text)]
    else:
        blocks.append(("p", work.abstract or "Este registro não traz resumo."))
    return [*blocks, *_footer(work, "Documento")]


def sheet_blocks(
    work: Work, sections: list[tuple[str, str]], findings: list[tuple[str, str]],
    reliability: dict[str, object] | None, citations: dict[str, str], extra: dict[str, object] | None,
) -> list[Block]:
    blocks = abstract_blocks(work, sections)[:-1]
    blocks.append(("h1", "Números e dados estatísticos (com a frase de origem)"))
    blocks += [("quote", f"{tags}: {sentence}") for tags, sentence in findings] or [("p", "Nenhum dado estatístico foi encontrado no resumo.")]
    blocks.append(("meta", "Frases copiadas do resumo; a seleção é por palavras-chave e pode omitir frases."))
    if reliability:
        score = reliability.get("score")
        blocks.append(("h1", "Confiabilidade"))
        blocks.append(("p", f"{score if score is not None else '—'}/100 ({reliability.get('band')}), cobertura "
                            f"{reliability.get('coverage')}% dos critérios."))
        for c in reliability.get("criteria") or []:  # type: ignore[attr-defined]
            evidence = f" Evidência: {c['evidence']}" if c.get("evidence") else ""
            blocks.append(("li", f"{c['name']} ({c['status']}, {c['points']}/{c['weight']}): {c['detail']}{evidence}"))
        blocks.append(("meta", str(reliability.get("disclaimer") or "")))
    if extra:
        blocks += _extra_blocks(extra)
    blocks.append(("h1", "Como citar"))
    blocks += [("p", f"{style}: {text}") for style, text in citations.items()]
    return [*blocks, *_footer(work, "Ficha de leitura")]


def _extra_blocks(extra: dict[str, object]) -> list[Block]:
    out: list[Block] = []
    trials = extra.get("trials") or []
    data = extra.get("relatedData") or []
    citations = extra.get("citations")
    if trials or data or citations is not None:
        out.append(("h1", "Registro e dados"))
    for t in trials:  # type: ignore[attr-defined]
        out.append(("li", f"Ensaio {t['nct']} ({t['status']}): {t['title']} — {t['url']}"))
    if citations is not None:
        out.append(("p", f"Citações (OpenCitations): {citations}"))
    for d in data:  # type: ignore[attr-defined]
        out.append(("li", f"{d['kind']}: {d['title']} — {d['url']}"))
    return out


# ------------------------------------------------------------------ texto completo (JATS da Europe PMC)
@dataclass(frozen=True)
class FullText:
    pmcid: str
    xml: bytes
    blocks: tuple[Block, ...]
    license: str


def fetch_fulltext_xml(pmcid: str) -> bytes | None:
    """XML JATS do artigo de acesso aberto; None quando nao ha texto completo aberto para o PMCID."""
    if not _PMC.match(pmcid):
        return None
    try:
        response = requests.get(FULLTEXT_URL.format(pmcid=pmcid), headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
    except requests.RequestException as error:
        logger.warning("Texto completo indisponivel: {}", error)
        raise CatalogError("Não foi possível obter o texto completo agora. Tente novamente em instantes.") from error
    if response.status_code >= 400:
        return None
    if len(response.content) > MAX_FULLTEXT_BYTES:
        raise CatalogError("O texto completo deste artigo é grande demais para baixar por aqui.")
    return response.content


def _section(sec: Element, depth: int, out: list[Block]) -> None:
    title = text_of(sec.find("title"))
    if title:
        out.append((f"h{min(depth, 3)}", title))
    for child in sec:
        if child.tag == "p":
            if text_of(child):
                out.append(("p", text_of(child)))
        elif child.tag == "sec":
            _section(child, depth + 1, out)
        elif child.tag in {"fig", "table-wrap"}:
            label, caption = text_of(child.find("label")), text_of(child.find("caption"))
            if caption:
                out.append(("quote", f"{label}: {caption}" if label else caption))


def _reference_text(ref: Element) -> str:
    """Numero da referencia + texto da citacao (o `text_of` colaria os dois sem espaco)."""
    label = text_of(ref.find("label"))
    node = ref.find("mixed-citation")
    if node is None:
        node = ref.find("element-citation")
    body = text_of(node) if node is not None else text_of(ref).removeprefix(label).strip()
    return f"{label} {body}".strip()


def jats_to_fulltext(pmcid: str, xml: bytes) -> FullText:
    root = parse_xml(xml)
    blocks: list[Block] = []
    body = root.find(".//body")
    if body is None or not any(True for _ in body.iter("p")):
        raise CatalogError("Este artigo não traz texto completo aberto.")
    for child in body:
        if child.tag == "sec":
            _section(child, 2, blocks)
        elif child.tag == "p" and text_of(child):
            blocks.append(("p", text_of(child)))
    refs = [_reference_text(ref) for ref in root.iterfind(".//ref-list/ref") if text_of(ref)]
    if refs:
        blocks.append(("h1", "Referências"))
        blocks += [("li", ref) for ref in refs]
    license_node = root.find(".//permissions/license")
    return FullText(pmcid=pmcid, xml=xml, blocks=tuple(blocks), license=text_of(license_node)[:400])


def fulltext_blocks(work: Work, fulltext: FullText) -> list[Block]:
    head: list[Block] = [("title", work.title), *[("meta", line) for line in _identity_lines(work)]]
    if fulltext.license:
        head.append(("meta", f"Licença: {fulltext.license}"))
    return [*head, ("h1", "Texto completo"), *fulltext.blocks, *_footer(work, "Documento")]


# ------------------------------------------------------------------ renderizacao
def to_txt(blocks: list[Block]) -> str:
    out: list[str] = []
    for kind, text in blocks:
        if kind == "title":
            out += [text.upper(), "=" * min(len(text), 78), ""]
        elif kind == "meta":
            out.append(text)
        elif kind in {"h1", "h2", "h3"}:
            out += ["", text.upper() if kind == "h1" else text, "-" * min(len(text), 78) if kind == "h1" else ""]
        elif kind == "quote":
            out += [f"  “{text}”", ""]
        elif kind == "li":
            out.append(f"- {text}")
        else:
            out += [text, ""]
    return "\n".join(out).strip() + "\n"


def to_md(blocks: list[Block]) -> str:
    out: list[str] = []
    prefix = {"title": "# ", "h1": "## ", "h2": "### ", "h3": "#### "}
    for kind, text in blocks:
        if kind in prefix:
            out += ["", prefix[kind] + text, ""]
        elif kind == "meta":
            out.append(f"{text}  ")
        elif kind == "quote":
            out += [f"> {text}", ""]
        elif kind == "li":
            out.append(f"- {text}")
        else:
            out += ["", text, ""]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip() + "\n"


_HTML_STYLE = (
    "body{font:16px/1.6 system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif;max-width:46rem;margin:2rem auto;"
    "padding:0 1rem;color:#111}h1{font-size:1.7rem;line-height:1.25}h2{font-size:1.25rem;margin-top:2rem}"
    "h3{font-size:1.05rem}h4{font-size:1rem}.meta{color:#555;font-size:.9rem;margin:.2rem 0}"
    "blockquote{border-left:3px solid #ea580c;margin:1rem 0;padding:.1rem 1rem;color:#222}li{margin:.3rem 0}"
)


def to_html(blocks: list[Block]) -> str:
    title = next((t for k, t in blocks if k == "title"), "Artigo")
    body: list[str] = []
    in_list = False
    for kind, text in blocks:
        if kind != "li" and in_list:
            body.append("</ul>")
            in_list = False
        safe = escape(text)
        if kind == "title":
            body.append(f"<h1>{safe}</h1>")
        elif kind == "h1":
            body.append(f"<h2>{safe}</h2>")
        elif kind in {"h2", "h3"}:
            body.append(f"<h{3 if kind == 'h2' else 4}>{safe}</h{3 if kind == 'h2' else 4}>")
        elif kind == "meta":
            body.append(f'<p class="meta">{safe}</p>')
        elif kind == "quote":
            body.append(f"<blockquote>{safe}</blockquote>")
        elif kind == "li":
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{safe}</li>")
        else:
            body.append(f"<p>{safe}</p>")
    if in_list:
        body.append("</ul>")
    return (
        f'<!doctype html>\n<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{escape(title)}</title><style>{_HTML_STYLE}</style></head><body>\n" + "\n".join(body) + "\n</body></html>\n"
    )


_DOCX_STYLES = {
    "title": ("<w:b/><w:sz w:val=\"36\"/>", "", 120),
    "meta": ("<w:color w:val=\"555555\"/><w:sz w:val=\"20\"/>", "", 40),
    "h1": ("<w:b/><w:sz w:val=\"28\"/>", "", 80),
    "h2": ("<w:b/><w:sz w:val=\"24\"/>", "", 60),
    "h3": ("<w:b/><w:i/><w:sz w:val=\"22\"/>", "", 40),
    "p": ("<w:sz w:val=\"22\"/>", "", 120),
    "quote": ("<w:i/><w:sz w:val=\"22\"/>", "<w:ind w:left=\"360\"/>", 120),
    "li": ("<w:sz w:val=\"22\"/>", "<w:ind w:left=\"360\" w:hanging=\"220\"/>", 60),
}


def _docx_paragraph(kind: str, text: str) -> str:
    run_props, para_props, after = _DOCX_STYLES.get(kind, _DOCX_STYLES["p"])
    clean = xml_escape(_XML_BAD.sub("", f"• {text}" if kind == "li" else text))
    top = ' w:before="240"' if kind in {"h1", "h2"} else ""
    before = f'<w:spacing{top} w:after="{after}"/>'
    return f"<w:p><w:pPr>{before}{para_props}</w:pPr><w:r><w:rPr>{run_props}</w:rPr><w:t xml:space=\"preserve\">{clean}</w:t></w:r></w:p>"


def to_docx(blocks: list[Block]) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
        + "".join(_docx_paragraph(k, t) for k, t in blocks)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1417" w:right="1417" w:bottom="1417" w:left="1417"/></w:sectPr>'
        "</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
    return buffer.getvalue()


def render(blocks: list[Block], fmt: str) -> tuple[bytes, str]:
    """(conteudo, tipo de midia) para txt, md, html ou docx."""
    if fmt == "docx":
        return to_docx(blocks), TEXT_FORMATS["docx"][1]
    renderers = {"txt": to_txt, "md": to_md, "html": to_html}
    return renderers[fmt](blocks).encode("utf-8"), f"{TEXT_FORMATS[fmt][1]}; charset=utf-8"


def to_json_bytes(payload: dict[str, object]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


# ------------------------------------------------------------------ menu de opcoes para a interface
def _safe_link(url: str) -> str:
    return url if url.startswith(("https://", "http://")) else ""


def menu(work: Work, fulltext: FullText | None, fulltext_note: str = "") -> dict[str, object]:
    """Opcoes de download do artigo: o que existe, em que formatos, e os links abertos da fonte."""
    def formats(kind: str) -> list[dict[str, str]]:
        names = {"json": "Dados (.json)", "xml": "Original JATS (.xml)", **{k: v[0] for k, v in TEXT_FORMATS.items()}}
        return [{"id": f, "label": names[f]} for f in KIND_FORMATS[kind]]

    citation_names = {"bibtex": "BibTeX (.bib)", "ris": "RIS (.ris)", "abnt": "ABNT (.txt)", "apa": "APA (.txt)", "vancouver": "Vancouver (.txt)"}
    options: list[dict[str, object]] = [
        {"kind": "abstract", "label": "Apenas o resumo", "available": True, "formats": formats("abstract"),
         "description": "Título, autores, identificação e o resumo com as seções originais."},
        {"kind": "sheet", "label": "Ficha de leitura", "available": True, "formats": formats("sheet"),
         "description": "Resumo, números com a frase de origem, nota de confiabilidade explicada, registro e dados, e citações."},
        {"kind": "citation", "label": "Só a referência", "available": True,
         "formats": [{"id": f, "label": citation_names[f]} for f in CITATION_FORMATS],
         "description": "Referência pronta para o gerenciador de bibliografia ou para o trabalho."},
        {"kind": "fulltext", "label": "Texto completo (acesso aberto)", "available": fulltext is not None,
         "formats": formats("fulltext"),
         "description": ("Texto integral com seções e referências, da Europe PMC." + (f" Licença: {fulltext.license}" if fulltext and fulltext.license else ""))
         if fulltext else (fulltext_note or "Sem texto completo aberto na Europe PMC para este artigo.")},
    ]
    links: list[dict[str, str]] = []
    pmcid = fulltext.pmcid if fulltext else work.pmcid
    if _safe_link(work.oa_url):
        links.append({"label": "PDF ou versão aberta da fonte", "url": work.oa_url})
    if pmcid and _PMC.match(pmcid):
        links.append({"label": "PDF na Europe PMC", "url": f"https://europepmc.org/articles/{pmcid}?pdf=render"})
    if work.doi:
        links.append({"label": "Página do editor (DOI)", "url": f"https://doi.org/{work.doi}"})
    return {"options": options, "links": links, "note": "PDFs de editoras abrem no site de origem; só oferecemos o que a fonte informa como aberto."}
