"""Contexto curado e verificável do Brasil, usado para complementar analises.

Este modulo nao substitui a leitura do artigo. Ele fornece orientacoes gerais e
estruturadas sobre instituicoes e regulacao (SUS, ANVISA, vigilancia sanitaria), com
ponto de origem. Os textos sao mantidos manualmente pelo desenvolvedor, ainda SEM revisao
por especialista (por isso carregam o aviso "pendente de revisao"), e NAO trazem dados
especificos como listas de medicamentos ou recomendacoes de incorporacao: o que depende
disso deve ser respondido como "nao verificavel".

Tambem expoe uma camada de verificacao de fontes externas: consultas HTTP
limitadas (timeout, limite de bytes, falha convertida em status explicito).
Quando a verificacao falha, o resultado e "nao verificavel" - nunca uma
afirmacao inventada.
"""

from __future__ import annotations

import os
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONTEXT_FILE = os.path.join(BASE_DIR, "contexto_brasil.json")

# ---------------------------------------------------------------------------
# Canais de verificacao (fontes oficiais/curadas, com data de confirmacao)
# ---------------------------------------------------------------------------
VERIFICATION_SOURCES: dict[str, dict] = {
    "bvs": {
        "name": "BVS-MS / Biblioteca Virtual em Saúde (Min. Saúde)",
        "catalog_url": "https://bvsms.saude.gov.br/",
        "note": "Base oficial do Ministério da Saúde: medicamentos, documentos e diretrizes.",
        "updated": "2026-09 (pendente de revisão por especialista)",
    },
    "anvisa": {
        "name": "ANVISA",
        "catalog_url": "https://www.gov.br/anvisa/pt-br",
        "note": "Registro de produtos, medicamentos, bulas e vigilancia sanitaria.",
        "updated": "2026-09 (pendente de revisão por especialista)",
    },
    "minsaude": {
        "name": "Ministério da Saúde",
        "catalog_url": "https://www.gov.br/saude/pt-br",
        "note": "Politicas de saude, SUS, vigilancia epidemiologica, normas e diretrizes.",
        "updated": "2026-09 (pendente de revisão por especialista)",
    },
    "conass": {
        "name": "CONASS (Conselho Nacional de Secretários de Saúde)",
        "catalog_url": "https://www.conass.org.br",
        "note": "Conselho Nacional de Secretarios de Saude (secretarias estaduais); posicionamentos e documentos de referencia.",
        "updated": "2026-09 (pendente de revisão por especialista)",
    },
    # Fontes ambientais: URLs de portais institucionais; a alcancabilidade e checada em
    # tempo de execucao. "updated" indica que o catalogo ainda nao foi revisado por especialista.
    "mma": {
        "name": "Ministério do Meio Ambiente",
        "catalog_url": "https://www.gov.br/mma/pt-br",
        "note": "Politicas ambientais nacionais, biodiversidade, clima e residuos.",
        "updated": "2026-10 (pendente de revisão)",
    },
    "ibama": {
        "name": "IBAMA",
        "catalog_url": "https://www.gov.br/ibama/pt-br",
        "note": "Licenciamento, fiscalizacao e controle ambiental federal.",
        "updated": "2026-10 (pendente de revisão)",
    },
    "conama": {
        "name": "CONAMA",
        "catalog_url": "https://conama.mma.gov.br/",
        "note": "Conselho Nacional do Meio Ambiente; resolucoes e normas ambientais.",
        "updated": "2026-10 (pendente de revisão)",
    },
    "ods": {
        "name": "ONU Brasil — Objetivos de Desenvolvimento Sustentável",
        "catalog_url": "https://brasil.un.org/pt-br/sdgs",
        "note": "Descricao oficial dos 17 ODS e suas metas.",
        "updated": "2026-10 (pendente de revisão)",
    },
}

# ---------------------------------------------------------------------------
# Mapeamento de conceitos -> chaves do registro curado
# ---------------------------------------------------------------------------
MAPA_CONCEITOS: dict[str, list[str]] = {
    "SUS": ["sus", "sistema unico de saude", "saude publica", "universalidade", "integralidade", "unified health system"],
    "ANVISA": ["anvisa", "registro", "bula", "regulamentacao", "produto", "marketing authorization"],
    "VIGILANCIA_SANITARIA": ["vigilancia", "epidemiologia", "surtos", "biosseguranca", "surveillance", "outbreak",
                             "pharmacovigilance"],
    "MEDICAMENTO_GENERICO": ["generico", "bioequivalencia", "generic drug", "bioequivalence"],
    "MEDICAMENTO_OUTRO": ["medicamento", "farmaco", "insumo", "dose", "posologia", "dosage"],
    "POPULACOES_ESPECIAIS": ["gestante", "idoso", "pediatrico", "renal", "hepatico", "pregnant", "elderly", "pediatric"],
}


def _normalizar(texto: str) -> str:
    """Minusculas, sem acentos e com pontuacao virando espaco (para casar palavras inteiras)."""
    base = unicodedata.normalize("NFKD", texto.lower()).encode("ascii", "ignore").decode()
    return " " + re.sub(r"[^a-z0-9]+", " ", base).strip() + " "


@dataclass(frozen=True)
class ItemContexto:
    item: str
    contexto: str
    fonte: str
    codigo_fonte: str
    atualizado: str

    def card(self) -> str:
        """Bloco de texto pronto para injetar em um prompt."""
        return (
            f"- {self.item}: {self.contexto}\n"
            f"  Fonte: **{self.fonte}** | codigo {self.codigo_fonte} | atualizado em {self.atualizado}"
        )


class ContextoBrasilError(RuntimeError):
    """Erro de configuracao ou disponibilidade do contexto curado."""


CONTEXTO_REGISTRY: dict[str, ItemContexto] = {
    "SUS": ItemContexto(
        item="SUS",
        contexto=(
            "O SUS garante atencao a saude sob principios de universalidade, "
            "integralidade e equidade. A disponibilidade concreta de um medicamento, "
            "procedimento ou medida no sistema depende de editais, protocolos, "
            "bancos de medicamentos, convenios e estados/municipios. "
            "Nao se infere disponibilidade no SUS apenas a partir da literatura "
            "cientifica, a menos que o texto informe expressamente o ambito de "
            "utilizacao."
        ),
        fonte="Ministerio da Saude / SUS",
        codigo_fonte="MIN-SAUDE-SUS",
        atualizado="2026-09 (pendente de revisão por especialista)",
    ),
    "ANVISA": ItemContexto(
        item="ANVISA",
        contexto=(
            "A ANVISA regula produtos de saude, incluindo medicamentos, por meio de "
            "registro, bula, instrucoes de uso e vigilancia sanitaria pos-comercializacao. "
            "A disponibilidade de um medicamento no Brasil nao e automaticamente "
            "garantida pelo SUS so porque ele tem registro ou indicacao "
            "cientifica. Municipios/estados e o Ministerio da Saude definem "
            "o ambito de utilizacao."
        ),
        fonte="ANVISA",
        codigo_fonte="ANVISA-REGULACAO",
        atualizado="2026-09 (pendente de revisão por especialista)",
    ),
    "VIGILANCIA_SANITARIA": ItemContexto(
        item="Vigilancia Sanitaria",
        contexto=(
            "A vigilancia sanitaria acompanha riscos sanitarios, produtos, surtos, "
            "envenenamentos, radiacao, alimentos, vacinas e biosseguranca, entre outros. "
            "Portais oficiais de saude e institutos de referencia sao fontes primarias; "
            "artigos cientificos podem sinalizar riscos, mas nao substituem "
            "vigilancia operacional nem comunicados oficiais."
        ),
        fonte="Ministerio da Saude / ANVISA",
        codigo_fonte="VIGILANCIA-AGENCIAS",
        atualizado="2026-09 (pendente de revisão por especialista)",
    ),
    "MEDICAMENTO_GENERICO": ItemContexto(
        item="Medicamento Generico",
        contexto=(
            "Medicamentos genericos devem ter bioequivalencia, principio ativo "
            "identificado e qualidade comprovada. O uso no SUS nao e garantido so "
            "pela existencia de medicamento generico; os protocolos de acesso "
            "definem a dispensacao. O artigo pode citar eficacia, mas nao valida "
            "se o medicamento esta disponivel ou financiado no SUS."
        ),
        fonte="ANVISA / Ministerio da Saude",
        codigo_fonte="ANVISA-GENERICO",
        atualizado="2026-09 (pendente de revisão por especialista)",
    ),
    "MEDICAMENTO_OUTRO": ItemContexto(
        item="Medicamento / Insumo",
        contexto=(
            "Medicamentos e insumos podem ter registro, uso indicado, preco, "
            "estoque e disponibilidade gerencial. A classe de medicamento nao "
            "garante que o produto esteja disponivel, nem que haja disponibilidade "
            "para todos os perfis. Perfil de paciente, comorbidades e dose "
            "tambem devem ser extraidos do artigo antes de afirmar aplicabilidade."
        ),
        fonte="ANVISA / paineis de medicamentos",
        codigo_fonte="ANVISA-DISPONIBILIDADE",
        atualizado="2026-09 (pendente de revisão por especialista)",
    ),
    "POPULACOES_ESPECIAIS": ItemContexto(
        item="Populacoes Especiais",
        contexto=(
            "Idosos, gestantes, lactantes, criancas, pacientes renais/hepaticos, "
            "imunossuprimidos e outros grupos podem ter dosagem, vigilancia e "
            "restricoes especificas. A ausencia de dados no artigo nao deve ser "
            "completada com conhecimento externo."
        ),
        fonte="Ministerio da Saude / sociedades cientificas",
        codigo_fonte="POP-ESPECIAL",
        atualizado="2026-09 (pendente de revisão por especialista)",
    ),
}


def selecionar_contexto(texto: str) -> list[ItemContexto]:
    """Retorna os itens curados relevantes para um trecho de texto.

    Casamento por palavra inteira (sem acento); nao faz inferencia, apenas filtra o registro.
    """
    if not texto:
        return []
    normalized = _normalizar(texto)
    found: list[ItemContexto] = []
    for key, palavras in MAPA_CONCEITOS.items():
        # palavra inteira: "sus" nao casa com "versus" nem "susceptible"; "renal" nao casa com "adrenal"
        if any(f" {palavra} " in normalized for palavra in palavras):
            item = CONTEXTO_REGISTRY.get(key)
            if item and item not in found:
                found.append(item)
    return found


def bloco_contexto(texto: str) -> str:
    """Gera o bloco de contexto pronto para o prompt (vazio se nada relevante)."""
    itens = selecionar_contexto(texto)
    if not itens:
        return ""
    linhas = ["--- CONTEXTO CURADO DO BRASIL (complementar; nao substitui o artigo) ---"]
    linhas.extend(item.card() for item in itens)
    linhas.append("--- FIM DO CONTEXTO CURADO ---")
    return "\n".join(linhas)


# ---------------------------------------------------------------------------
# Verificacao de fontes externas (HTTP limitado e seguro)
# ---------------------------------------------------------------------------

_URL_SCHEMES_OK = {"http", "https"}


def _url_segura(url: str) -> bool:
    """Aceita apenas http/https com host. Bloqueia file://, etc."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    return parsed.scheme in _URL_SCHEMES_OK and bool(parsed.netloc)


def _texto_visivel(html: str, max_chars: int = 1500) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text)[:max_chars]


class VerificacaoExterna:
    """Consulta limitada a fontes publicas com falha explicita.

    Regras de confiabilidade:
    - somente http/https;
    - timeout curto;
    - falha de rede/HTTP vira status "nao_verificavel", nunca afirmacao;
    - resultados em cache por TTL para nao travar a interface;
    - nenhum conteudo retornado e tratado como verdade; apenas anexo verificavel.
    """

    TIMEOUT_SECONDS = 6
    MAX_BYTES = 400 * 1024
    CACHE_TTL_SECONDS = 600  # 10 minutos

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "NexusScience/1.0 (verificacao de contexto de saude)",
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9",
            }
        )
        self._cache: dict[str, tuple[float, dict]] = {}

    def consultar(self, url: str) -> dict:
        """Retorna status explicito + trecho util, ou 'nao_verificavel'."""
        now = time.time()
        cached = self._cache.get(url)
        if cached and now - cached[0] < self.CACHE_TTL_SECONDS:
            return dict(cached[1])
        result = self._consultar_sem_cache(url)
        self._cache[url] = (now, result)
        return dict(result)

    def _consultar_sem_cache(self, url: str) -> dict:
        if not url or not _url_segura(url):
            return {"status": "nao_verificavel", "motivo": "url_invalida", "url": url}
        try:
            response = self._session.get(url, timeout=self.TIMEOUT_SECONDS, stream=True)
            response.raise_for_status()
            content = b""
            for chunk in response.iter_content(8192):
                content += chunk
                if len(content) >= self.MAX_BYTES:
                    break
            html = content.decode(response.encoding or "utf-8", errors="replace")
        except requests.exceptions.Timeout:
            return {"status": "nao_verificavel", "motivo": "timeout", "url": url}
        except requests.exceptions.ConnectionError:
            return {"status": "nao_verificavel", "motivo": "conexao_falhou", "url": url}
        except requests.exceptions.HTTPError as error:
            code = error.response.status_code if error.response is not None else "?"
            return {"status": "nao_verificavel", "motivo": f"http_{code}", "url": url}
        except Exception:  # pragma: no cover - defesa
            return {"status": "nao_verificavel", "motivo": "erro_interno", "url": url}

        soup = BeautifulSoup(html, "lxml")
        title_tag = soup.find("title")
        return {
            "status": "ok",
            "url": url,
            "titulo": title_tag.get_text(strip=True) if title_tag else "",
            "trecho": _texto_visivel(html),
        }

    def verificar_fontes(self, urls: list[str]) -> list[dict]:
        return [self.consultar(u) for u in urls if u]


def relatorio_verificacao(resultados: list[dict]) -> str:
    """Monta o bloco de anexo verificavel para o prompt."""
    if not resultados:
        return ""
    linhas = ["--- ANEXO DE VERIFICACAO EXTERNA (somente para referencia; nao e o artigo) ---"]
    for r in resultados:
        if r.get("status") == "ok":
            linhas.append(f"- [OK] {r.get('url', '')} | titulo: {r.get('titulo', '')}")
            trecho = r.get("trecho", "")
            if trecho:
                linhas.append(f"  trecho: {trecho}")
        else:
            linhas.append(
                f"- [NAO VERIFICAVEL] {r.get('url', '')} | motivo: {r.get('motivo', '')}"
            )
    linhas.append(
        "Regra: conteudo deste anexo NAO deve ser apresentado como fato do artigo. "
        "Se o anexo estiver vazio ou com status NAO VERIFICAVEL, responda "
        "'Nao verificavel com as fontes acessiveis'."
    )
    linhas.append("--- FIM DO ANEXO ---")
    return "\n".join(linhas)


_verificacao: Optional[VerificacaoExterna] = None


def get_verificacao() -> VerificacaoExterna:
    global _verificacao
    if _verificacao is None:
        _verificacao = VerificacaoExterna()
    return _verificacao
