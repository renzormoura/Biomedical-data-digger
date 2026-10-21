"""Gera o instantaneo da Tabela SIGTAP (procedimentos, medicamentos e OPM do SUS) a partir do arquivo oficial do DATASUS.

O DATASUS publica a Tabela Unificada de Procedimentos como um ZIP de arquivos de largura fixa (latin-1), com o layout
descrito nos proprios `*_layout.txt`. Este modulo descobre o arquivo mais recente na pagina oficial, baixa por FTP,
le so o que o produto usa (procedimento, grupo, subgrupo e forma de organizacao) e grava um JSON compacto, com a
origem e a data da extracao. Usado pelo script `scripts/atualizar_sigtap.py`; o servidor nunca baixa nada em execucao.
"""

from __future__ import annotations

import io
import json
import re
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

PAGE_URL = "http://sigtap.datasus.gov.br/tabela-unificada/app/download.jsp"
ALLOWED_FTP_HOST = "ftp2.datasus.gov.br"
MAX_BYTES = 25_000_000
HTTP_TIMEOUT = 60
USER_AGENT = "NexusScience/1.0 (atualizacao de dados oficiais)"
SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "dados_brasil" / "sigtap.json"
_LINK = re.compile(r'href="(ftp://ftp2\.datasus\.gov\.br/pub/sistemas/tup/downloads/TabelaUnificada_(\d{6})_v\d+\.zip)"', re.IGNORECASE)
MIN_PROCEDIMENTOS = 3000  # a tabela real tem milhares; muito menos indica leitura errada


class SigtapError(RuntimeError):
    """Falha ao obter ou ler a Tabela SIGTAP; a mensagem e segura para exibir."""


def descobrir_arquivo(html: str) -> tuple[str, str]:
    """(url do ZIP, competencia AAAAMM) da tabela mais recente anunciada na pagina oficial."""
    found = _LINK.findall(html)
    if not found:
        raise SigtapError("A pagina do SIGTAP nao traz o link da Tabela Unificada.")
    url, competencia = max(found, key=lambda item: (item[1], item[0]))
    if urlparse(url).hostname != ALLOWED_FTP_HOST:
        raise SigtapError("O link da tabela aponta para fora do servidor oficial do DATASUS; recusado.")
    return url, competencia


def _baixar(url: str, tentativas: int = 4) -> bytes:
    last: Exception | None = None
    for attempt in range(tentativas):
        try:
            with urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=HTTP_TIMEOUT) as response:  # noqa: S310 - host conferido acima
                content = response.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise SigtapError("Arquivo grande demais para o esperado; recusado.")
            return content
        except OSError as error:
            last = error
            time.sleep(2.0 * (attempt + 1) if attempt + 1 < tentativas else 0)
    raise SigtapError(f"Nao foi possivel baixar {url}: {last}") from last


def baixar_tabela() -> tuple[bytes, str, str]:
    """(conteudo do ZIP, url, competencia AAAAMM)."""
    page = _baixar(PAGE_URL).decode("latin-1", errors="replace")
    url, competencia = descobrir_arquivo(page)
    return _baixar(url), url, competencia


def _layout(texto: str) -> dict[str, tuple[int, int]]:
    """Coluna -> (inicio, fim) em indice de fatia, a partir do `*_layout.txt` (CSV: Coluna,Tamanho,Inicio,Fim,Tipo)."""
    colunas: dict[str, tuple[int, int]] = {}
    for linha in texto.splitlines()[1:]:
        partes = linha.strip().split(",")
        if len(partes) >= 4 and partes[2].isdigit() and partes[3].isdigit():
            colunas[partes[0]] = (int(partes[2]) - 1, int(partes[3]))
    return colunas


def _ler(arquivo: zipfile.ZipFile, nome: str, campos: tuple[str, ...]) -> list[dict[str, str]]:
    try:
        colunas = _layout(arquivo.read(f"{nome}_layout.txt").decode("latin-1"))
        dados = arquivo.read(f"{nome}.txt").decode("latin-1")
    except KeyError as error:
        raise SigtapError(f"A tabela mudou de formato: falta o arquivo {nome}.") from error
    faltam = [campo for campo in campos if campo not in colunas]
    if faltam:
        raise SigtapError(f"A tabela mudou de formato: faltam as colunas {faltam} em {nome}.")
    return [{campo: linha[colunas[campo][0]:colunas[campo][1]].strip() for campo in campos} for linha in dados.splitlines() if linha.strip()]


def montar_instantaneo(conteudo: bytes, *, arquivo_url: str, competencia: str, agora: datetime | None = None) -> dict[str, object]:
    try:
        arquivo = zipfile.ZipFile(io.BytesIO(conteudo))
    except zipfile.BadZipFile as error:
        raise SigtapError("O arquivo do SIGTAP nao e um ZIP valido.") from error
    procedimentos = _ler(arquivo, "tb_procedimento", ("CO_PROCEDIMENTO", "NO_PROCEDIMENTO", "TP_COMPLEXIDADE"))
    if len(procedimentos) < MIN_PROCEDIMENTOS:
        raise SigtapError(f"Poucos procedimentos lidos ({len(procedimentos)}); instantaneo recusado.")
    grupos = {r["CO_GRUPO"]: r["NO_GRUPO"] for r in _ler(arquivo, "tb_grupo", ("CO_GRUPO", "NO_GRUPO"))}
    subgrupos = {r["CO_GRUPO"] + r["CO_SUB_GRUPO"]: r["NO_SUB_GRUPO"] for r in _ler(arquivo, "tb_sub_grupo", ("CO_GRUPO", "CO_SUB_GRUPO", "NO_SUB_GRUPO"))}
    versao = arquivo.read("versao").decode("latin-1").strip() if "versao" in arquivo.namelist() else ""
    itens = [[r["CO_PROCEDIMENTO"], " ".join(r["NO_PROCEDIMENTO"].split()), r["TP_COMPLEXIDADE"]] for r in procedimentos if r["CO_PROCEDIMENTO"]]
    itens.sort(key=lambda item: item[0])
    return {
        "meta": {
            "fonte": "DATASUS, Tabela de Procedimentos, Medicamentos, Orteses, Proteses e Materiais Especiais do SUS (SIGTAP)",
            "pagina_url": PAGE_URL, "arquivo_url": arquivo_url, "competencia": competencia, "versao_layout": versao,
            "extraido_em": (agora or datetime.now(timezone.utc)).date().isoformat(), "procedimentos": len(itens),
        },
        "grupos": grupos,
        "subgrupos": subgrupos,
        "procedimentos": itens,  # [codigo, nome, complexidade (0 nao se aplica, 1 basica, 2 media, 3 alta)]
    }


def salvar(instantaneo: dict[str, object], caminho: Path = SNAPSHOT_PATH) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(instantaneo, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return caminho


def atualizar(caminho: Path = SNAPSHOT_PATH) -> dict[str, object]:
    conteudo, url, competencia = baixar_tabela()
    snapshot = montar_instantaneo(conteudo, arquivo_url=url, competencia=competencia)
    salvar(snapshot, caminho)
    return snapshot
