"""Leitura de XML vindo da rede (arXiv, PubMed) sem expor o servidor a entidades maliciosas."""

from __future__ import annotations

import xml.etree.ElementTree as ET  # noqa: S405 - entradas validadas por `parse_xml` antes de analisar

from catalog import CatalogError


def parse_xml(content: bytes) -> ET.Element:
    """Analisa XML recusando declaracoes de entidade (ataque de expansao); DOCTYPE com DTD externo e ignorado."""
    if b"<!ENTITY" in content:
        raise CatalogError("A fonte devolveu um formato inesperado.")
    try:
        return ET.fromstring(content)  # noqa: S314 - sem entidades; o analisador do Python nao busca DTD externo
    except ET.ParseError as error:
        raise CatalogError("A fonte devolveu uma resposta ilegível.") from error


def text_of(element: ET.Element | None) -> str:
    """Texto completo de um elemento, incluindo marcacao interna (ex.: <i>), com espacos normalizados."""
    if element is None:
        return ""
    return " ".join("".join(element.itertext()).split())
