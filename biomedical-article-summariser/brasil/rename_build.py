"""Gera o instantaneo da RENAME 2024 (Relacao Nacional de Medicamentos Essenciais) a partir do PDF oficial.

O PDF do Ministerio da Saude (BVS, 2a edicao, CC BY-NC-SA 4.0) lista os medicamentos por grupo ATC, com a
apresentacao, o componente de financiamento e o codigo ATC. Aqui cada linha vira um registro. A extracao e
um passo de desenvolvimento (usa `pypdf`, que nao e dependencia do servidor) e DEVE ser conferida por amostra
contra o PDF: o layout em tabela nao e garantido. Usado por `scripts/atualizar_rename.py`.
"""

from __future__ import annotations

import io
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from brasil.nomes import limpar_substancia, normalizar

PDF_URL = "https://bvsms.saude.gov.br/bvs/publicacoes/relacao_nacional_medicamentos_2024_2ed.pdf"
ALLOWED_HOST = "bvsms.saude.gov.br"
MAX_BYTES = 40_000_000
HTTP_TIMEOUT = 120
USER_AGENT = "Lastro/1.0 (dados abertos)"
SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "dados_brasil" / "rename.json"
EDICAO = "RENAME 2024 (2ª edição, 2025)"
LICENCA = "CC BY-NC-SA 4.0 (uso não comercial, com atribuição e mesma licença)"

_CABECALHO_LINHA = re.compile(r"^(\|\s*\d+.*|\|\s*\d+\s*|RELAÇÃO NACIONAL.*|MINISTÉRIO DA SAÚDE|continua|continuação|conclusão)$")
_GRUPO = re.compile(r"^[A-Z]\*?: ")
_CABECALHO_TABELA = re.compile(
    r"Denomina[çc][ãa]o\s+Comum\s+Brasileira\s+\(DCB\)\s+Concentra[çc][ãa]o\s*/\s*Composi[çc][ãa]o\s+Forma\s+"
    r"Farmac[êe]utica\s+Componente\s+de\s+[Ff]inanciamento\s+da\s+Assist[êe]ncia\s+Farmac[êe]utica\s+C[óo]digo\s+ATC"
)
_COMP = r"(?:B[áa]sico|Estrat[ée]gico|Especializado|Procedimento\s+Hospitalar\(\d\)|Insumos\s+\([^)]*\))"
_LINHA = re.compile(
    rf"(?P<corpo>.*?)\s(?P<comp>{_COMP}(?:\s+e\s+{_COMP})?)\s+"
    r"(?P<atc>[A-Z]\d{2}[A-Z]{1,2}(?:\d{2}|\s?\d{4})?(?:\(\d\))?|NC)(?:\s*(?:;|e)\s*[A-Z]\d{2}[A-Z]{2}\d{2})*(?:\s+(?:Acesso|Alerta|Reserva|-)(?=\s|$))?(?=\s|$)"
)
_INICIO_APRESENTACAO = re.compile(r"\s(?=\d)|\s-\s|\scada\s")
_SAL_INTERMEDIARIO = re.compile(r"^(\w+ato)\s+(?:s[óo]dico|pot[áa]ssico|c[áa]lcico|dissódico)\s+de\s+", re.IGNORECASE)
_NOMES_SEM_CONCENTRACAO = ("sais para reidratação oral",)
_ROTULO = re.compile(r"^(?:Acesso|Alerta|Reserva|Classificação AWaRe)\s+", re.IGNORECASE)
_PARENTESES = re.compile(r"\s*\([^)]*(?:\)|$)")
_QUEBRA = re.compile(r"(?<=[a-zà-ú])- (?=[a-zà-ú])")
PRIMEIRA_PAGINA = 25  # indice (0-based) da primeira pagina da lista por grupo ATC
ULTIMA_PAGINA = 133  # indice (0-based) da ultima pagina da lista (antes do Anexo I)


class RenameError(RuntimeError):
    """Falha ao obter ou ler a Rename; a mensagem e segura para exibir."""


def baixar(url: str = PDF_URL, tentativas: int = 4) -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
        raise RenameError("Endereco fora do dominio oficial; recusado.")
    last: Exception | None = None
    for tentativa in range(tentativas):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            break
        except requests.RequestException as error:
            last = error
            time.sleep(3.0 * (tentativa + 1) if tentativa + 1 < tentativas else 0)
    else:
        raise RenameError("Nao foi possivel baixar o PDF da Rename.") from last
    if len(response.content) > MAX_BYTES:
        raise RenameError("O PDF da Rename e maior que o esperado; recusado.")
    return response.content


def paginas(conteudo: bytes) -> list[str]:
    try:
        from pypdf import PdfReader  # dependencia so de desenvolvimento
    except ImportError as error:
        raise RenameError("Instale pypdf (requirements-dev.txt) para gerar o instantaneo da Rename.") from error
    try:
        leitor = PdfReader(io.BytesIO(conteudo))
        return [(pagina.extract_text() or "") for pagina in leitor.pages]
    except Exception as error:  # noqa: BLE001 - pypdf levanta tipos variados em PDF corrompido
        raise RenameError("Nao foi possivel ler o PDF da Rename.") from error


def _nome_e_apresentacao(corpo: str, nome_anterior: str) -> tuple[str, str]:
    corpo = re.sub(r"^-\s+", "", corpo.strip())
    for fixo in _NOMES_SEM_CONCENTRACAO:  # itens cujo nome nao e seguido de numero no PDF
        if corpo.lower().startswith(fixo):
            return corpo[: len(fixo)], corpo[len(fixo):].strip()
    partes = _INICIO_APRESENTACAO.split(corpo, maxsplit=1)
    if len(partes) == 1 or not partes[0].strip():
        return nome_anterior, corpo
    nome = _QUEBRA.sub("", _ROTULO.sub("", partes[0].strip()))
    if not nome[:1].isalpha():
        return nome_anterior, corpo
    return nome, corpo[len(partes[0]):].strip(" -")


def extrair(textos: list[str]) -> list[dict[str, object]]:
    """Uma entrada por linha da tabela (nome, apresentacao, componente, ATC, pagina do PDF)."""
    itens: list[dict[str, object]] = []
    nome = ""
    for indice in range(PRIMEIRA_PAGINA, min(ULTIMA_PAGINA + 1, len(textos))):
        linhas = [x for x in textos[indice].split("\n") if not _CABECALHO_LINHA.match(x.strip()) and not _GRUPO.match(x.strip())]
        texto = _CABECALHO_TABELA.sub(" ", re.sub(r"\s+", " ", " ".join(linhas).replace("sexuais e insulinas", "")))
        for achado in _LINHA.finditer(texto):
            nome, apresentacao = _nome_e_apresentacao(achado.group("corpo"), nome)
            componente = re.sub(r"\s+", " ", achado.group("comp"))
            if componente.startswith("Insumos") or not nome:
                continue
            itens.append({
                "nome": nome, "apresentacao": apresentacao, "componente": re.sub(r"\(\d\)", "", componente).strip(),
                "atc": re.sub(r"\s", "", achado.group("atc").split("(")[0]), "pagina": indice + 1,
            })
    return itens


def chave_do_nome(nome: str) -> str:
    """Chave de busca: sem parenteses (nome cientifico), sem sal ('cloridrato de') e normalizada."""
    limpo = _PARENTESES.sub("", nome).strip()
    limpo = _SAL_INTERMEDIARIO.sub("", limpo)
    return normalizar(limpar_substancia(limpo))


def montar_instantaneo(itens: list[dict[str, object]], *, paginas_pdf: int, agora: datetime | None = None) -> dict[str, object]:
    if not itens:
        raise RenameError("Nenhum item reconhecido no PDF; o layout pode ter mudado.")
    registros = [dict(item, chave=chave_do_nome(str(item["nome"]))) for item in itens]
    registros = [r for r in registros if r["chave"]]
    return {
        "meta": {
            "fonte": EDICAO, "url": PDF_URL, "licenca": LICENCA, "paginas_pdf": paginas_pdf, "itens": len(registros),
            "substancias": len({r["chave"] for r in registros}),
            "extraido_em": (agora or datetime.now(timezone.utc)).date().isoformat(),
            "aviso": "Extraido do PDF por script; conferido por amostra. Constar na Rename nao significa disponibilidade na unidade.",
        },
        "itens": registros,
    }


def salvar(instantaneo: dict[str, object], caminho: Path = SNAPSHOT_PATH) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(instantaneo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return caminho


def atualizar(caminho: Path = SNAPSHOT_PATH) -> dict[str, object]:
    conteudo = baixar()
    textos = paginas(conteudo)
    instantaneo = montar_instantaneo(extrair(textos), paginas_pdf=len(textos))
    salvar(instantaneo, caminho)
    return instantaneo
