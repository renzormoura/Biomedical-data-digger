"""Gera o instantaneo da ANVISA (registro de medicamentos por substancia) a partir dos dados abertos oficiais.

O CSV `DADOS_ABERTOS_MEDICAMENTOS.csv` (dados.anvisa.gov.br, ~46 MB, atualizado diariamente a partir do DATAVISA)
tem uma linha por registro. Aqui ele e reduzido a uma linha por SUBSTANCIA (sal e forma farmaceutica removidos):
quantos registros ativos e inativos, categorias, classes terapeuticas, empresas e a validade mais distante.
Usado pelo script `scripts/atualizar_anvisa.py`; o servidor nunca baixa o CSV.
"""

from __future__ import annotations

import csv
import io
import json
import re
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from brasil.nomes import limpar_substancia, normalizar

CSV_URL = "https://dados.anvisa.gov.br/dados/DADOS_ABERTOS_MEDICAMENTOS.csv"
DICIONARIO_URL = "https://dados.anvisa.gov.br/dados/Documentacao_e_Dicionario_de_Dados_Registros_Validos_Medicamento_V1.pdf"
ALLOWED_HOST = "dados.anvisa.gov.br"
MAX_BYTES = 150_000_000
HTTP_TIMEOUT = 180
USER_AGENT = "BiomedicalDataDigger/1.0 (dados abertos)"
SNAPSHOT_PATH = Path(__file__).resolve().parent.parent / "dados_brasil" / "anvisa.json"
REQUIRED = {"NOME_PRODUTO", "CATEGORIA_REGULATORIA", "DATA_VENCIMENTO_REGISTRO", "CLASSE_TERAPEUTICA", "EMPRESA_DETENTORA_REGISTRO",
            "SITUACAO_REGISTRO", "PRINCIPIO_ATIVO", "TIPO_PRODUTO"}
_ATIVO = "ativo"
_IGNORAR = {"associacoes", "associacao", "outros", "outras", "demais"}
_COMPONENTES = re.compile(r"\s*(?:,|\+|;)\s*")
_CATEGORIAS = {"similar": "Similar", "generico": "Genérico", "novo": "Novo", "especifico": "Específico", "fitoterapico": "Fitoterápico",
               "biologico": "Biológico", "radiofarmaco": "Radiofármaco", "dinamizado": "Dinamizado", "baixo risco": "Baixo risco"}


class AnvisaError(RuntimeError):
    """Falha ao obter ou ler os dados da ANVISA; a mensagem e segura para exibir."""


def baixar(url: str = CSV_URL, tentativas: int = 4) -> tuple[bytes, str]:
    """(conteudo, data de modificacao informada pelo servidor em ISO)."""
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
        raise AnvisaError("Endereco fora do dominio oficial; recusado.")
    last: Exception | None = None
    for attempt in range(tentativas):
        try:
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT)
            response.raise_for_status()
            break
        except requests.RequestException as error:
            last = error
            time.sleep(3.0 * (attempt + 1) if attempt + 1 < tentativas else 0)
    else:
        raise AnvisaError(f"Nao foi possivel baixar {url}: {last}") from last
    if len(response.content) > MAX_BYTES:
        raise AnvisaError("Arquivo grande demais para o esperado; recusado.")
    modified = response.headers.get("Last-Modified", "")
    try:
        modified_iso = parsedate_to_datetime(modified).date().isoformat() if modified else ""
    except (TypeError, ValueError):
        modified_iso = ""
    return response.content, modified_iso


def ler_csv(conteudo: bytes) -> list[dict[str, str]]:
    """Linhas do CSV (separador ';', texto em cp1252) como dicionarios; recusa arquivos com colunas diferentes."""
    reader = csv.DictReader(io.StringIO(conteudo.decode("cp1252", errors="replace"), newline=""), delimiter=";", quotechar='"')
    if not set(reader.fieldnames or ()) >= REQUIRED:
        raise AnvisaError(f"O CSV mudou de formato: faltam as colunas {sorted(REQUIRED - set(reader.fieldnames or ()))}.")
    return list(reader)


def componentes(principio_ativo: str) -> list[str]:
    """Substancias de um registro (associacoes separadas por virgula ou +), ja sem sal nem forma farmaceutica."""
    nomes: list[str] = []
    for parte in _COMPONENTES.split(principio_ativo.strip()):
        nome = limpar_substancia(parte)
        if nome and normalizar(nome) not in _IGNORAR and len(normalizar(nome)) >= 3 and nome not in nomes:
            nomes.append(nome)
    return nomes


def _categoria(texto: str) -> str:
    chave = normalizar(texto).replace("fitoter pico", "fitoterapico")
    return _CATEGORIAS.get(chave, _CATEGORIAS.get(chave.replace(" ", ""), texto.strip().capitalize() if texto.strip() else "Sem categoria"))


def _validade(texto: str) -> str:
    """MMAAAA -> AAAA-MM (vazio se invalido)."""
    texto = texto.strip()
    return f"{texto[2:6]}-{texto[:2]}" if re.fullmatch(r"(0[1-9]|1[0-2])\d{4}", texto) else ""


def agregar(linhas: list[dict[str, str]]) -> tuple[list[dict[str, object]], dict[str, int]]:
    """Uma entrada por substancia; devolve tambem estatisticas da leitura."""
    acc: dict[str, dict[str, object]] = {}
    nomes: dict[str, Counter[str]] = defaultdict(Counter)
    stats = {"linhas": 0, "sem_principio_ativo": 0, "ativos": 0}
    for row in linhas:
        stats["linhas"] += 1
        if row["TIPO_PRODUTO"].strip().upper() != "MEDICAMENTO":
            continue
        partes = componentes(row["PRINCIPIO_ATIVO"])
        if not partes:
            stats["sem_principio_ativo"] += 1
            continue
        ativo = normalizar(row["SITUACAO_REGISTRO"]) == _ATIVO
        stats["ativos"] += ativo
        for nome in partes:
            chave = normalizar(nome)
            entrada = acc.setdefault(chave, {"ativos": 0, "inativos": 0, "ativos_isolado": 0, "categorias": Counter(), "classes": Counter(),
                                             "empresas": set(), "validade": ""})
            nomes[chave][nome] += 1
            if not ativo:
                entrada["inativos"] += 1  # type: ignore[operator]
                continue
            entrada["ativos"] += 1  # type: ignore[operator]
            if len(partes) == 1:
                entrada["ativos_isolado"] += 1  # type: ignore[operator]
            entrada["categorias"][_categoria(row["CATEGORIA_REGULATORIA"])] += 1  # type: ignore[index]
            if row["CLASSE_TERAPEUTICA"].strip():
                entrada["classes"][row["CLASSE_TERAPEUTICA"].strip().capitalize()] += 1  # type: ignore[index]
            if row["EMPRESA_DETENTORA_REGISTRO"].strip():
                entrada["empresas"].add(row["EMPRESA_DETENTORA_REGISTRO"].strip())  # type: ignore[attr-defined]
            entrada["validade"] = max(str(entrada["validade"]), _validade(row["DATA_VENCIMENTO_REGISTRO"]))
    resultado = []
    for chave in sorted(acc):
        e = acc[chave]
        resultado.append({
            "nome": nomes[chave].most_common(1)[0][0], "chave": chave, "ativos": e["ativos"], "inativos": e["inativos"],
            "ativos_isolado": e["ativos_isolado"], "categorias": dict(e["categorias"].most_common()),  # type: ignore[attr-defined]
            "classes": [c for c, _ in e["classes"].most_common(3)],  # type: ignore[attr-defined]
            "empresas": len(e["empresas"]), "validade_max": e["validade"],  # type: ignore[arg-type]
        })
    return resultado, stats


def montar_instantaneo(linhas: list[dict[str, str]], *, arquivo_modificado: str, agora: datetime | None = None) -> dict[str, object]:
    substancias, stats = agregar(linhas)
    if len(substancias) < 1000 or stats["ativos"] < 10000:  # o CSV real tem milhares de substancias e dezenas de milhares de ativos
        raise AnvisaError(f"Leitura suspeita ({len(substancias)} substancias, {stats['ativos']} registros ativos); instantaneo recusado.")
    return {
        "meta": {
            "fonte": "ANVISA, dados abertos de medicamentos registrados (DATAVISA)",
            "arquivo_url": CSV_URL, "dicionario_url": DICIONARIO_URL, "arquivo_modificado": arquivo_modificado,
            "extraido_em": (agora or datetime.now(timezone.utc)).date().isoformat(), "linhas_csv": stats["linhas"],
            "linhas_sem_principio_ativo": stats["sem_principio_ativo"], "registros_ativos": stats["ativos"],
            "substancias": len(substancias),
        },
        "substancias": substancias,
    }


def salvar(instantaneo: dict[str, object], caminho: Path = SNAPSHOT_PATH) -> Path:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(instantaneo, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return caminho


def atualizar(caminho: Path = SNAPSHOT_PATH) -> dict[str, object]:
    conteudo, modificado = baixar()
    snapshot = montar_instantaneo(ler_csv(conteudo), arquivo_modificado=modificado)
    salvar(snapshot, caminho)
    return snapshot
