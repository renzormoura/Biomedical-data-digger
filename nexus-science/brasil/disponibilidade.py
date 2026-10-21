"""Disponibilidade no SUS: o que um artigo (ou um termo) estuda existe no SUS, sim ou nao? Por consulta, sem IA e sem rede.

Junta as quatro bases do pacote Brasil:
- medicamentos: Rename (lista nacional de essenciais), decisoes da Conitec, registro na ANVISA e os medicamentos do
  Componente Especializado que a SIGTAP codifica (grupo 06);
- cirurgias, exames, procedimentos e tecnicas: Tabela SIGTAP do DATASUS.

Cada item recebe um veredito com a fonte e a data. Os vereditos dizem o que as BASES mostram; nenhum garante que a
unidade de saude da pessoa ofereca o item: a interface repete esse aviso em todo resultado.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from brasil import anvisa, conitec, consulta, rename, sigtap
from brasil.nomes import normalizar

GRUPO_MEDICAMENTOS = "06"

# chave -> (rotulo curto, tom visual). Os tons sao estaveis: a interface os usa como classe de estilo.
VEREDITOS: dict[str, tuple[str, str]] = {
    "disponivel": ("Consta no SUS", "ok"),
    "incorporado": ("Incorporado ao SUS", "ok"),
    "registrado": ("Registrado, sem oferta encontrada", "warn"),
    "nao_incorporado": ("Avaliado e não incorporado", "no"),
    "excluido": ("Excluído do SUS", "no"),
    "nao_encontrado": ("Não encontrado nas bases", "none"),
}
_INCORPORA = {"incorporar", "ampliar", "manter", "aprovar"}
_NAO_INCORPORA = {"nao incorporar", "nao ampliar"}
AVISO = (
    "Constar em uma lista oficial não garante que a unidade de saúde da pessoa tenha o item: a oferta depende do município, "
    "do serviço habilitado e do estoque. Dados de instantâneo, ainda sem revisão de especialista."
)


@dataclass(frozen=True)
class Item:
    tipo: str  # "medicamento" ou "procedimento"
    nome: str
    veredito: str
    origem: str  # trecho do artigo que originou a ligacao; vazio na busca manual
    metodo: str  # "sinonimo", "cognato" ou "manual"
    detalhes: tuple[str, ...] = ()
    procedimentos: tuple[sigtap.Procedimento, ...] = ()
    total_procedimentos: int = 0
    fontes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def rotulo(self) -> str:
        return VEREDITOS[self.veredito][0]


def _ultima_decisao(registros: tuple[conitec.Registro, ...]) -> conitec.Registro | None:
    return max(registros, key=lambda r: (r.data_publicacao, r.tecnologia), default=None)


def _medicamento(situacao: consulta.Situacao, tabela: sigtap.Instantaneo, origem: str, metodo: str) -> Item:
    nome = situacao.candidato.pt if situacao.candidato else situacao.termo.capitalize()
    detalhes: list[str] = []
    fontes: list[str] = []
    especializado = tuple(p for p in sigtap.buscar(situacao.termo, instantaneo=tabela, limite=400).itens if p.codigo.startswith(GRUPO_MEDICAMENTOS))
    decisao = _ultima_decisao(situacao.conitec)
    rotulo_decisao = normalizar(decisao.decisao_ms) if decisao else ""
    veredito = "nao_encontrado"
    if situacao.rename:
        componentes = ", ".join(c.lower() for r in situacao.rename for c in r.componentes)
        detalhes.append(f"Consta na Rename 2024 (medicamentos essenciais), componente {componentes}.")
        fontes.append("Rename")
        veredito = "disponivel"
    if especializado:
        detalhes.append(f"A SIGTAP tem {len(especializado)} código(s) de medicamento para este princípio ativo (ex.: {especializado[0].nome.capitalize()}).")
        fontes.append("SIGTAP")
        veredito = "disponivel"
    if decisao:
        fontes.append("Conitec")
        quando = f", portaria {decisao.portaria}" if decisao.portaria else ""
        detalhes.append(f"Decisão mais recente da Conitec: {decisao.decisao_ms or decisao.recomendacao} ({decisao.data_publicacao[:4]}{quando}).")
        if veredito == "nao_encontrado":
            if rotulo_decisao in _INCORPORA:
                veredito = "incorporado"
            elif rotulo_decisao in _NAO_INCORPORA:
                veredito = "nao_incorporado"
            elif rotulo_decisao == "excluir":
                veredito = "excluido"
    if situacao.anvisa:
        fontes.append("ANVISA")
        ativos = sum(s.ativos for s in situacao.anvisa)
        detalhes.append(f"{ativos} registro(s) ativo(s) na ANVISA: o produto pode ser vendido no país, o que não significa oferta pelo SUS.")
        if veredito == "nao_encontrado":
            veredito = "registrado"
    return Item("medicamento", nome, veredito, origem, metodo, tuple(detalhes), fontes=tuple(fontes))


def _procedimento(termo: str, tabela: sigtap.Instantaneo, origem: str, metodo: str, *, exibicao: str = "") -> Item:
    achados = sigtap.buscar(termo, instantaneo=tabela)
    nome = exibicao or termo.capitalize()
    if not achados.total:
        return Item("procedimento", nome, "nao_encontrado", origem, metodo, ("Nenhum procedimento com esse nome na Tabela SIGTAP. O SUS pode cobri-lo sob outro nome.",), fontes=("SIGTAP",))
    grupos = sorted({p.grupo for p in achados.itens if p.grupo})
    detalhes = (f"{achados.total} procedimento(s) com esse nome na Tabela SIGTAP" + (f" ({'; '.join(grupos)})." if grupos else "."),)
    return Item("procedimento", nome, "disponivel", origem, metodo, detalhes, achados.itens, achados.total, ("SIGTAP",))


def avaliar_termo(
    termo: str, anvisa_data: anvisa.Instantaneo, conitec_data: conitec.Instantaneo, rename_data: rename.Instantaneo, tabela: sigtap.Instantaneo,
) -> list[Item]:
    """Busca manual: o termo pode ser medicamento, procedimento, tecnica ou produto (em portugues)."""
    normalizado = consulta.normalizar_termo(termo)
    itens: list[Item] = []
    situacao = consulta.situacao(normalizado, anvisa_data, conitec_data, rename_data=rename_data)
    medicamento = _medicamento(situacao, tabela, "", "manual")
    if medicamento.veredito != "nao_encontrado":
        itens.append(medicamento)
    if medicamento.veredito == "nao_encontrado":  # achou o medicamento: os exames "de insulina" etc. so confundiriam; refine a busca
        procedimento = _procedimento(normalizado, tabela, "", "manual", exibicao=termo.strip().capitalize())
        if procedimento.veredito != "nao_encontrado":
            itens.append(procedimento)
    return itens or [Item("procedimento", termo.strip().capitalize(), "nao_encontrado", "", "manual",
                          ("Não achamos esse termo na Rename, na Conitec, na ANVISA nem na Tabela SIGTAP. Tente o nome técnico em português.",))]


def avaliar_texto(
    texto: str, anvisa_data: anvisa.Instantaneo, conitec_data: conitec.Instantaneo, rename_data: rename.Instantaneo, tabela: sigtap.Instantaneo,
) -> list[Item]:
    """Intervencoes que o texto (em ingles) parece citar: medicamentos e procedimentos, cada um a confirmar."""
    itens = [
        _medicamento(s, tabela, s.candidato.en if s.candidato else "", s.candidato.metodo if s.candidato else "manual")
        for s in consulta.situacoes_do_texto(texto, anvisa_data, conitec_data, rename_data)
    ]
    for candidato in sigtap.candidatos(texto, instantaneo=tabela):
        item = _procedimento(candidato.termo, tabela, candidato.en, candidato.metodo)
        if item.veredito == "nao_encontrado" and not candidato.verificavel:
            continue  # um cognato so nasce de uma palavra da tabela; "nao achei" so vale para sinonimos curados
        itens.append(item)
    return itens


def como_contexto(itens: list[Item]) -> str:
    """Bloco de contexto para o Laboratorio de IA: o que as bases dizem, para o modelo explicar sem inventar."""
    if not itens:
        return ""
    linhas = ["--- DISPONIBILIDADE NO SUS: o que as bases oficiais mostram (use somente isto; cada item e uma possivel correspondencia) ---"]
    for item in itens:
        extra = f" (trecho do artigo: {item.origem})" if item.origem else ""
        linhas.append(f"- {item.nome}{extra} [{item.tipo}]: {item.rotulo}. " + " ".join(item.detalhes))
    linhas.append("--- FIM ---")
    return "\n".join(linhas)
