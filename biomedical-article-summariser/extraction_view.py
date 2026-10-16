"""Monta o markdown das respostas sem IA (extracao, trechos e bloqueios)."""

from __future__ import annotations

from europepmc import EuropePmcRecord
from extraction import (
    extract_findings,
    extract_passages,
    split_sections,
    study_type_labels,
)

# Nome do tema em portugues, para mensagens ("o resumo nao traz informacao sobre ...").
TOPIC_NAMES = {
    "dose": "doses ou posologia",
    "conduta": "condutas, protocolos ou recomendações",
    "interacoes": "interações medicamentosas",
    "reacoes": "reações adversas ou segurança",
    "populacoes": "populações especiais (idosos, crianças, gestantes, função renal ou hepática)",
    "alertas": "riscos, segurança ou contraindicações",
}
PASSAGE_KINDS = ("dose", "conduta", "interacoes", "reacoes")

NO_AI_NOTE = "nenhum texto foi gerado ou interpretado por IA; os trechos abaixo foram copiados do artigo"
KEYWORD_SELECTION_NOTE = (
    "> A seleção é feita por palavras-chave e **pode omitir frases relevantes** ou incluir frases pouco "
    "relevantes. Confira sempre o resumo original e o artigo completo."
)


def _header(title_line: str) -> str:
    return f"---\n> **{title_line}**  ·  {NO_AI_NOTE}\n\n---\n"


def overview_markdown(title: str, abstract: str, record: EuropePmcRecord | None) -> str:
    lines = [_header("Extraído do artigo (sem IA)"), f"## Título do Artigo: {title}", ""]

    lines.append("### Tipo de estudo (rótulo do registro oficial)")
    if record is None:
        lines.append("- Registro oficial indisponível para este identificador (só PMID, PMCID e DOI são consultados).")
    else:
        types = study_type_labels(list(record.pub_types))
        lines.append("- " + (" · ".join(types) if types else "O registro não informa um tipo de estudo específico."))
    lines.append("")

    lines.append("### Resumo organizado (texto original)")
    sections = split_sections(abstract)
    if sections:
        for section in sections:
            label = f" *(rótulo original: {section.label})*" if section.label and section.label != section.heading else ""
            lines.extend([f"**{section.heading}**{label}", section.text, ""])
    else:
        lines.extend(["O resumo não tem seções rotuladas; texto original completo:", "", abstract, ""])

    lines.append("### Números e dados estatísticos (com a frase de origem)")
    findings = extract_findings(abstract)
    if findings:
        for finding in findings:
            lines.append(f"- *{' · '.join(finding.tags)}* — {finding.sentence}")
    else:
        lines.append("- Nenhum dado estatístico foi encontrado no resumo.")
    lines.append("")

    if record is not None:
        lines.append("### Metadados do registro")
        facts = [f"Revista: {record.journal}" + (f" ({record.year})" if record.year else "")] if record.journal else []
        if record.open_access is not None:
            facts.append("Acesso aberto: " + ("sim" if record.open_access else "não"))
        if record.cited_by is not None:
            facts.append(f"Citações: {record.cited_by}")
        if record.language:
            facts.append(f"Idioma: {record.language}")
        if facts:
            lines.append("- " + " · ".join(facts))
        if record.keywords:
            lines.append("- Palavras-chave: " + ", ".join(record.keywords))
        if record.mesh_terms:
            lines.append("- Termos MeSH: " + ", ".join(record.mesh_terms))
        if record.funders:
            lines.append("- Financiamento (agências): " + ", ".join(record.funders))
        lines.append("")

    lines.append("> Lido apenas o título e o resumo; o texto completo do artigo não foi consultado.")
    return "\n".join(lines)


def passages_markdown(label: str, kind: str, title: str, abstract: str) -> str:
    topic = TOPIC_NAMES[kind]
    lines = [_header(f"{label} — trechos do resumo (sem IA)"), f"## Título do Artigo: {title}", ""]
    passages = extract_passages(abstract, kind)
    if passages:
        lines.append(f"### Trechos do resumo sobre {topic}")
        lines.extend(f"- {passage}" for passage in passages)
        lines.extend(["", KEYWORD_SELECTION_NOTE])
    else:
        lines.append(
            f"> **Nada encontrado:** o resumo deste artigo não traz informação sobre {topic}. "
            "Nenhuma análise foi gerada, para evitar que lacunas sejam preenchidas por inferência."
        )
    return "\n".join(lines)


def blocked_markdown(label: str, kind: str, title: str) -> str:
    return (
        f"---\n> **{label}**\n\n---\n## Título do Artigo: {title}\n\n"
        f"> ⛔ **Análise não gerada:** o resumo deste artigo não traz informação sobre {TOPIC_NAMES[kind]}. "
        "Para evitar que a IA preencha lacunas, nenhum texto foi gerado (nenhum token gasto)."
    )
