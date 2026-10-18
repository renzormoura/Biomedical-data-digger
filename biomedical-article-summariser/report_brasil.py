"""Secao "Situacao no Brasil" do relatorio de tema (pacote de saude): ANVISA, Conitec e Rename por substancia.

So aparece para as substancias que o AUTOR confirmou: o sistema apenas *sugere* nomes a partir dos resumos dos estudos
incluidos (sinonimos conhecidos e nomes parecidos), e uma sugestao automatica nunca entra no documento sozinha.
Tudo vem dos instantaneos oficiais versionados do repositorio, por codigo, sem IA e sem rede.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from brasil import anvisa, conitec, consulta, rename
from brasil.nomes import encontrar
from catalog import Work
from downloads import Block

Bases = tuple[anvisa.Instantaneo, conitec.Instantaneo, rename.Instantaneo]
MAX_SCAN = 120  # resumos analisados para sugerir nomes (cada um custa alguns milissegundos)
MAX_SUGGESTIONS = 12
CONITEC_PER_SUBSTANCE = 5
INDICATION_CHARS = 160
CATEGORY_PLURAL = {
    "Genérico": "genéricos", "Similar": "similares", "Novo": "novos", "Biológico": "biológicos", "Específico": "específicos",
    "Fitoterápico": "fitoterápicos", "Dinamizado": "dinamizados", "Radiofármaco": "radiofármacos",
}
CAUTION = (
    "Constar na Rename ou ter registro ativo na ANVISA não significa disponibilidade na unidade de saúde; "
    "a decisão da Conitec trata da incorporação ao SUS."
)
PENDING_REVIEW = "Os dados do Brasil ainda não foram revisados por farmacêutico ou médico: confira nas fontes antes de usar em decisão."


@dataclass(frozen=True)
class Suggestion:
    termo: str
    nome: str
    en: str  # trecho do texto que originou a ligacao
    metodo: str  # "sinonimo" ou "cognato"
    studies: int  # quantos estudos incluidos citam a substancia


@dataclass(frozen=True)
class BrasilSection:
    blocks: tuple[Block, ...]
    method: str  # frase para o apendice de metodo


def suggest(works: list[Work], bases: Bases) -> list[Suggestion]:
    """Substancias que os resumos parecem citar, das mais citadas para as menos (a confirmar pelo autor)."""
    vocabulary = consulta.vocabulario(*bases)
    counts: Counter[str] = Counter()
    seen: dict[str, Suggestion] = {}
    for work in works[:MAX_SCAN]:
        for candidate in encontrar(f"{work.title}. {work.abstract}", vocabulary, limite=consulta.MAX_CANDIDATES):
            counts[candidate.termo] += 1
            seen.setdefault(candidate.termo, Suggestion(candidate.termo, candidate.pt, candidate.en, candidate.metodo, 0))
    ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:MAX_SUGGESTIONS]
    return [Suggestion(t, seen[t].nome, seen[t].en, seen[t].metodo, n) for t, n in ranked]


def situations(terms: tuple[str, ...], bases: Bases) -> list[consulta.Situacao]:
    return [consulta.situacao(term, bases[0], bases[1], rename_data=bases[2]) for term in terms]


def display_name(item: consulta.Situacao) -> str:
    """Nome para exibir: o que casa exatamente com o termo (ANVISA primeiro, sem sal), senao o primeiro encontrado, senao o termo."""
    pairs = [(a.chave, a.nome) for a in item.anvisa] + [(r.chave, r.nome) for r in item.rename]  # a ANVISA ja vem sem o sal
    name = next((nome for chave, nome in pairs if chave == item.termo), pairs[0][1] if pairs else item.termo)
    return name[:1].upper() + name[1:]


def _date(meta: dict[str, object]) -> str:
    try:
        return date.fromisoformat(str(meta.get("extraido_em", ""))).strftime("%d/%m/%Y")
    except ValueError:
        return "data desconhecida"


def sources_line(bases: Bases) -> str:
    return (f"ANVISA (dados abertos, extraído em {_date(bases[0].meta)}); Conitec (planilha de decisões, extraída em {_date(bases[1].meta)}); "
            f"{bases[2].meta.get('fonte', 'Rename')} (PDF oficial, extraído em {_date(bases[2].meta)})")


def _br_date(value: str) -> str:
    try:
        return date.fromisoformat(value[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return value


def _month(value: str) -> str:
    return f"{value[5:]}/{value[:4]}" if len(value) == 7 and value[4] == "-" else ""


def _anvisa_text(item: consulta.Situacao) -> str:
    if not item.anvisa:
        return "ANVISA: nenhum registro de medicamento com esta substância."
    main = next((s for s in item.anvisa if s.chave == item.termo), item.anvisa[0])
    parts = [f"{main.ativos} registros ativos" if main.ativos != 1 else "1 registro ativo"]
    if main.inativos:
        parts.append(f"{main.inativos} inativos")
    if main.categorias:
        parts.append(", ".join(f"{n} {CATEGORY_PLURAL.get(name, name.lower())}" for name, n in list(main.categorias.items())[:4]))
    if main.empresas:
        parts.append(f"{main.empresas} empresas")
    if main.validade_max:
        parts.append(f"validade mais distante {_month(main.validade_max)}")
    extra = len(item.anvisa) - 1
    suffix = f" Há também {extra} associações ou outras formas com a substância." if extra > 0 else ""
    return f"ANVISA ({main.nome}): " + "; ".join(p for p in parts if p) + "." + suffix


def _rename_text(item: consulta.Situacao) -> str:
    if not item.rename:
        return "Rename 2024: a substância não consta na relação nacional de medicamentos essenciais."
    main = next((r for r in item.rename if r.chave == item.termo), item.rename[0])
    first = main.apresentacoes[0].texto if main.apresentacoes else ""
    return (f"Rename 2024 ({main.nome}): consta, componente {', '.join(main.componentes).lower()}; "
            f"{len(main.apresentacoes)} apresentações listadas" + (f" (por exemplo, {first})." if first else "."))


def _conitec_blocks(item: consulta.Situacao) -> list[Block]:
    if not item.conitec:
        return [("p", "Conitec: sem decisão registrada para esta substância.")]
    shown = item.conitec[:CONITEC_PER_SUBSTANCE]
    total = len(item.conitec)
    count = "1 decisão registrada" if total == 1 else f"{total} decisões registradas (mostrando {len(shown)})"
    blocks: list[Block] = [("p", f"Conitec: {count}.")]
    for record in shown:
        indication = record.indicacao if len(record.indicacao) <= INDICATION_CHARS else record.indicacao[: INDICATION_CHARS - 1] + "…"
        details = " · ".join(p for p in [record.portaria, _br_date(record.data_publicacao), f"relatório técnico {record.relatorio_tecnico}" if record.relatorio_tecnico else ""] if p)
        decision = f" (decisão do MS: {record.decisao_ms})" if record.decisao_ms and record.decisao_ms != record.recomendacao else ""
        blocks.append(("li", f"{record.ano or 's.d.'} · {record.recomendacao or 'sem recomendação informada'}{decision}"
                             + (f" — {indication}" if indication else "") + (f" [{details}]" if details else "")))
    return blocks


def build(terms: tuple[str, ...], bases: Bases) -> BrasilSection | None:
    """Blocos do documento para as substancias confirmadas; None quando o autor nao confirmou nenhuma."""
    if not terms:
        return None
    blocks: list[Block] = [
        ("h1", "Situação no Brasil"),
        ("meta", f"Substâncias confirmadas pelo autor. Dados oficiais consultados por código, sem IA, em instantâneos datados: {sources_line(bases)}."),
    ]
    for item in situations(terms, bases):
        blocks += [("h2", display_name(item)), ("p", _rename_text(item)), ("p", _anvisa_text(item)), *_conitec_blocks(item)]
    blocks += [("meta", CAUTION), ("meta", PENDING_REVIEW)]
    method = (
        "Situação no Brasil: o autor confirmou as substâncias; a ligação entre o nome citado nos estudos e o nome oficial é uma sugestão "
        f"automática (sinônimos conhecidos e nomes parecidos) que ele revisou. Bases consultadas por código: {sources_line(bases)}."
    )
    return BrasilSection(tuple(blocks), method)
