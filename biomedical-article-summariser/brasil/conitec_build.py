"""Gera o instantaneo da CONITEC (recomendacoes sobre medicamentos) a partir da planilha oficial.

A Conitec publica uma planilha Excel aberta com todas as tecnologias avaliadas. Este modulo descobre o link
atual na pagina oficial, baixa o arquivo, le o XLSX so com a biblioteca padrao e guarda apenas os medicamentos
em JSON compacto, com a origem e a data da extracao. Usado pelo script `scripts/atualizar_conitec.py`; o
servidor nunca baixa nada em tempo de execucao.
"""

from __future__ import annotations

import io
import json
import re
import time
import unicodedata
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse
from xml.etree.ElementTree import Element

import requests

from xmlutil import parse_xml

PAGE_URL = "https://www.gov.br/conitec/pt-br/assuntos/avaliacao-de-tecnologias-em-saude/recomendacoes-da-conitec"
ALLOWED_HOST = "www.gov.br"
MAX_BYTES = 8_000_000
HTTP_TIMEOUT = 40
USER_AGENT = "Lastro/1.0 (atualizacao de dados oficiais)"
SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "dados_brasil" / "conitec.json"
_LINK = re.compile(r'href="([^"]*recomendacoesdaconitec_(\d{8})\.xlsx[^"]*)"', re.IGNORECASE)
_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_EXCEL_EPOCH = date(1899, 12, 30)
COLUMNS = {
    "ANO": "ano", "TECNOLOGIA AVALIADA E INDICACAO": "tecnologia", "RELATORIO TECNICO": "relatorio_tecnico",
    "RELATORIO PARA A SOCIEDADE": "relatorio_sociedade", "RECOMENDACAO DA CONITEC FINAL": "recomendacao",
    "DECISAO DO MS": "decisao_ms", "PORTARIA": "portaria", "DATA DA PUBLICACAO": "data_publicacao", "TIPO": "tipo",
    "INDICACAO": "indicacao",
}


class ConitecError(RuntimeError):
    """Falha ao obter ou ler a planilha da Conitec; a mensagem e segura para exibir."""


def _fold(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().upper().strip()


def descobrir_arquivo(html: str) -> tuple[str, str]:
    """(url absoluta, AAAAMMDD) da planilha mais recente anunciada na pagina oficial."""
    found = _LINK.findall(html)
    if not found:
        raise ConitecError("A pagina da Conitec nao traz o link da planilha de recomendacoes.")
    href, stamp = max(found, key=lambda item: item[1])
    url = urljoin(PAGE_URL, href)
    if urlparse(url).scheme != "https" or urlparse(url).hostname != ALLOWED_HOST:
        raise ConitecError("O link da planilha aponta para fora do dominio oficial; recusado.")
    return url, stamp


def _get(url: str, tentativas: int = 6) -> bytes:
    """Baixa com ate 6 tentativas: o portal gov.br responde 404/5xx de forma intermitente (medido em 2026-10)."""
    last: Exception | None = None
    for attempt in range(tentativas):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            break
        except requests.RequestException as error:
            last = error
            time.sleep(2.0 * (attempt + 1) if attempt + 1 < tentativas else 0)
    else:
        raise ConitecError(f"Nao foi possivel baixar {url}: {last}") from last
    if len(response.content) > MAX_BYTES:
        raise ConitecError("Arquivo grande demais para o esperado; recusado.")
    return response.content


def baixar_planilha() -> tuple[bytes, str, str]:
    """(conteudo, url do arquivo, AAAAMMDD do nome do arquivo)."""
    url, stamp = descobrir_arquivo(_get(PAGE_URL).decode("utf-8", errors="replace"))
    return _get(url), url, stamp


def _celulas(linha: Element, textos: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for cell in linha.findall(f"{_NS}c"):
        column = re.match(r"[A-Z]+", cell.get("r", ""))
        if not column:
            continue
        value = cell.find(f"{_NS}v")
        if value is not None and value.text is not None:
            out[column.group(0)] = textos[int(value.text)] if cell.get("t") == "s" else value.text
        else:
            inline = cell.find(f"{_NS}is")
            out[column.group(0)] = "".join(t.text or "" for t in inline.iter(f"{_NS}t")) if inline is not None else ""
    return out


def ler_xlsx(content: bytes) -> list[dict[str, str]]:
    """Linhas da primeira aba como dicionarios com os nomes de campo de `COLUMNS` (colunas desconhecidas sao ignoradas)."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
        textos = [
            "".join(t.text or "" for t in si.iter(f"{_NS}t"))
            for si in parse_xml(archive.read("xl/sharedStrings.xml")).findall(f"{_NS}si")
        ] if "xl/sharedStrings.xml" in archive.namelist() else []
        sheet = parse_xml(archive.read("xl/worksheets/sheet1.xml"))
    except (zipfile.BadZipFile, KeyError) as error:
        raise ConitecError("A planilha da Conitec esta em um formato inesperado.") from error
    rows = [_celulas(r, textos) for r in sheet.iterfind(f".//{_NS}sheetData/{_NS}row")]
    if not rows:
        raise ConitecError("A planilha da Conitec veio vazia.")
    header = {col: COLUMNS[_fold(name)] for col, name in rows[0].items() if _fold(name) in COLUMNS}
    missing = set(COLUMNS.values()) - set(header.values())
    if missing:
        raise ConitecError(f"A planilha mudou de formato: faltam as colunas {sorted(missing)}.")
    return [{field: row.get(col, "").strip() for col, field in header.items()} for row in rows[1:]]


def serial_para_data(valor: str) -> str:
    """Data serial do Excel (ex.: 46253) em ISO; vazio se nao for um numero valido."""
    try:
        return (_EXCEL_EPOCH + timedelta(days=int(float(valor)))).isoformat()
    except (ValueError, OverflowError):
        return ""


def _rotulo(texto: str) -> str:
    text = " ".join(texto.split())
    return text[:1].upper() + text[1:].lower() if text else ""


def registros_medicamentos(linhas: list[dict[str, str]]) -> list[dict[str, object]]:
    """So os medicamentos (escopo da fase 1), com datas em ISO e rotulos de decisao padronizados."""
    out: list[dict[str, object]] = []
    for row in linhas:
        if _fold(row.get("tipo", "")) != "MEDICAMENTO" or not row.get("tecnologia"):
            continue
        out.append({
            "ano": int(row["ano"]) if row.get("ano", "").isdigit() else None,
            "tecnologia": " ".join(row["tecnologia"].split()),
            "indicacao": " ".join(row.get("indicacao", "").split()),
            "recomendacao": _rotulo(row.get("recomendacao", "")),
            "decisao_ms": _rotulo(row.get("decisao_ms", "")),
            "portaria": " ".join(row.get("portaria", "").split()),
            "data_publicacao": serial_para_data(row.get("data_publicacao", "")),
            "relatorio_tecnico": " ".join(row.get("relatorio_tecnico", "").split()),
            "relatorio_sociedade": " ".join(row.get("relatorio_sociedade", "").split()),
        })
    return out


def montar_instantaneo(linhas: list[dict[str, str]], *, arquivo_url: str, arquivo_data: str, agora: datetime | None = None) -> dict[str, object]:
    medicamentos = registros_medicamentos(linhas)
    if len(medicamentos) < 100:  # a planilha real tem centenas; muito menos indica leitura errada
        raise ConitecError(f"Poucos medicamentos lidos ({len(medicamentos)}); instantaneo recusado.")
    medicamentos.sort(key=lambda r: (str(r["data_publicacao"]), str(r["tecnologia"])), reverse=True)
    return {
        "meta": {
            "fonte": "CONITEC, recomendacoes sobre tecnologias avaliadas (planilha oficial)",
            "pagina_url": PAGE_URL, "arquivo_url": arquivo_url, "arquivo_data": arquivo_data,
            "extraido_em": (agora or datetime.now(timezone.utc)).date().isoformat(),
            "linhas_planilha": len(linhas), "linhas_medicamento": len(medicamentos), "escopo": "somente medicamentos",
        },
        "registros": medicamentos,
    }


def salvar(instantaneo: dict[str, object], caminho: Path = SNAPSHOT_PATH) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(instantaneo, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return caminho


def atualizar(caminho: Path = SNAPSHOT_PATH) -> dict[str, object]:
    content, url, stamp = baixar_planilha()
    snapshot = montar_instantaneo(ler_xlsx(content), arquivo_url=url, arquivo_data=stamp)
    salvar(snapshot, caminho)
    return snapshot
