"""Busca, normalizacao e cache de artigos cientificos."""

import re
import threading
from functools import wraps
from typing import Tuple

import requests
from bs4 import BeautifulSoup as bs
from loguru import logger


Article = Tuple[str, str]
_article_cache: dict[str, Article] = {}
_cache_lock = threading.Lock()


def get_cached_article(article_id: str) -> Article | None:
    with _cache_lock:
        return _article_cache.get(article_id)


def set_cached_article(article_id: str, title: str, abstract: str) -> None:
    with _cache_lock:
        if len(_article_cache) >= 20:
            oldest = next(iter(_article_cache))
            del _article_cache[oldest]
        _article_cache[article_id] = (title, abstract)


def catch_request_error(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.RequestException as error:
            print(f"Request error in {func.__name__}: {error}")
            return None

    return wrapper


def clean_text(text: str) -> str:
    text = re.sub(r"\{.*?\}", "", text)
    text = re.sub(r"\\[a-zA-Z]+", "", text)
    text = re.sub(r"\[\s*(\d+\s*(,\s*\d+\s*)*)\]", "", text)
    return re.sub(r"\s+", " ", text).strip()


@catch_request_error
@logger.catch
def get_xml_from_url(url: str) -> bs:
    response = requests.get(url)
    response.raise_for_status()
    return bs(response.content, "lxml-xml")


def fetch_article_abstract(soup: bs) -> Article:
    if soup is None:
        return "No XML found", ""
    title_tag = soup.find("article-title")
    title = title_tag.get_text(strip=True) if title_tag else "No Title Found for this article"
    abstract_tag = soup.find("abstract")
    if not abstract_tag:
        return title, ""
    abstract = " ".join(
        clean_text(paragraph.get_text(strip=True))
        for paragraph in abstract_tag.find_all("p")
        if paragraph.get_text(strip=True)
    )
    return title, abstract


def fetch_full_text(soup: bs) -> Article:
    if soup is None:
        return "No XML found", ""
    title_tag = soup.find("article-title")
    title = title_tag.get_text(strip=True) if title_tag else "No Title Found"
    section_labels = {
        "intro": "Introducao", "methods": "Metodos", "results": "Resultados",
        "discussion": "Discussao", "conclusions": "Conclusao", "abstract": "Abstract",
    }
    sections = []
    for section in soup.find_all("sec"):
        section_type = (section.get("sec-type") or "").lower()
        label = next((name for key, name in section_labels.items() if key in section_type), None)
        if label is None:
            title_tag = section.find("title")
            label = title_tag.get_text(strip=True) if title_tag else None
        if not label:
            continue
        paragraphs = [
            clean_text(paragraph.get_text(strip=True))
            for paragraph in section.find_all("p")
            if paragraph.get_text(strip=True)
        ]
        if paragraphs:
            sections.append(f"**{label}:**\n" + " ".join(paragraphs))
    if sections:
        return title, "\n\n".join(sections)
    abstract_tag = soup.find("abstract")
    if abstract_tag:
        return title, " ".join(
            clean_text(paragraph.get_text(strip=True))
            for paragraph in abstract_tag.find_all("p")
            if paragraph.get_text(strip=True)
        )
    return title, ""


def get_abstract_from_pmid(pmid: str) -> Article:
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:{pmid}&resultType=core&format=json"
    response = requests.get(url)
    response.raise_for_status()
    results = response.json().get("resultList", {}).get("result", [])
    if not results:
        return "Artigo nao encontrado", ""
    article = results[0]
    return article.get("title", "Titulo nao encontrado"), clean_text(article.get("abstractText", ""))


def detect_input_type(raw: str) -> Tuple[str, str]:
    value = raw.strip()
    url_patterns = [
        (r"pubmed\.ncbi\.nlm\.nih\.gov/(\d+)", "pmid"),
        (r"ncbi\.nlm\.nih\.gov/pubmed/(\d+)", "pmid"),
        (r"pmc\.ncbi\.nlm\.nih\.gov/articles/(PMC\d+)", "pmcid"),
        (r"ncbi\.nlm\.nih\.gov/pmc/articles/(PMC\d+)", "pmcid"),
        (r"europepmc\.org/article/MED/(\d+)", "pmid"),
        (r"europepmc\.org/articles/(PMC\d+)", "pmcid"),
        (r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5}(?:v\d+)?)", "arxiv"),
        (r"arxiv\.org/(?:abs|pdf)/([a-z\-]+/\d+)", "arxiv"),
        (r"doi\.org/(10\.\d{4,}/\S+)", "doi"),
        (r"openalex\.org/(W\d+)", "openalex"),
        (r"semanticscholar\.org/paper/[^/]+/([a-f0-9]{40})", "semantic_scholar"),
    ]
    for pattern, input_type in url_patterns:
        match = re.search(pattern, value, re.IGNORECASE)
        if match:
            return input_type, match.group(1)
    checks = [
        (r"^PMC\d{4,}$", "pmcid", str.upper),
        (r"^\d{6,9}$", "pmid", lambda item: item),
        (r"^10\.\d{4,}/\S+$", "doi", lambda item: item),
        (r"^\d{4}\.\d{4,5}(v\d+)?$", "arxiv", lambda item: item),
        (r"^[a-z\-]+/\d{7}$", "arxiv", lambda item: item),
        (r"^W\d{6,}$", "openalex", str.upper),
        (r"^[a-f0-9]{40}$", "semantic_scholar", lambda item: item),
    ]
    for pattern, input_type, normalizer in checks:
        if re.match(pattern, value, re.IGNORECASE):
            return input_type, normalizer(value)
    return "unknown", value


def fetch_by_doi(doi: str) -> Article:
    try:
        response = requests.get(
            f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=title,abstract",
            timeout=10,
        )
        if response.status_code == 200:
            data = response.json()
            title, abstract = data.get("title", ""), clean_text(data.get("abstract") or "")
            if title and abstract:
                return title, abstract
    except Exception:
        pass
    try:
        response = requests.get(
            f"https://api.crossref.org/works/{doi}", timeout=10,
            headers={"User-Agent": "BiomedicalDataDigger/1.0"},
        )
        if response.status_code == 200:
            item = response.json().get("message", {})
            raw_title = item.get("title", [""])
            title = raw_title[0] if raw_title else "Titulo nao encontrado"
            abstract = clean_text(re.sub(r"<[^>]+>", " ", item.get("abstract", "")))
            if title:
                return title, abstract
    except Exception:
        pass
    return "Artigo nao encontrado via DOI", ""


def fetch_by_arxiv(arxiv_id: str) -> Article:
    try:
        clean_id = re.sub(r"v\d+$", "", arxiv_id)
        response = requests.get(
            f"https://export.arxiv.org/api/query?id_list={clean_id}",
            timeout=10,
        )
        response.raise_for_status()
        entry = bs(response.content, "lxml-xml").find("entry")
        if not entry:
            return "Artigo nao encontrado no arXiv", ""
        title_tag, summary_tag = entry.find("title"), entry.find("summary")
        return (
            clean_text(title_tag.get_text()) if title_tag else "Titulo nao encontrado",
            clean_text(summary_tag.get_text()) if summary_tag else "",
        )
    except Exception as error:
        return f"Erro ao buscar no arXiv: {error}", ""


def fetch_by_openalex(openalex_id: str) -> Article:
    try:
        response = requests.get(
            f"https://api.openalex.org/works/{openalex_id}", timeout=10,
            headers={"User-Agent": "BiomedicalDataDigger/1.0"},
        )
        response.raise_for_status()
        data = response.json()
        inverted = data.get("abstract_inverted_index")
        if not inverted:
            return data.get("title", "Titulo nao encontrado"), ""
        words = [""] * (max(position for positions in inverted.values() for position in positions) + 1)
        for word, positions in inverted.items():
            for position in positions:
                words[position] = word
        return data.get("title", "Titulo nao encontrado"), clean_text(" ".join(words))
    except Exception as error:
        return f"Erro ao buscar no OpenAlex: {error}", ""


def fetch_by_semantic_scholar(s2_id: str) -> Article:
    try:
        response = requests.get(
            f"https://api.semanticscholar.org/graph/v1/paper/{s2_id}?fields=title,abstract",
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("title", "Titulo nao encontrado"), clean_text(data.get("abstract") or "")
    except Exception as error:
        return f"Erro ao buscar no Semantic Scholar: {error}", ""


def resolve_article(raw_input: str) -> Tuple[str, str, str]:
    input_type, value = detect_input_type(raw_input.strip())
    if input_type == "pmcid":
        soup = get_xml_from_url(f"https://www.ebi.ac.uk/europepmc/webservices/rest/{value}/fullTextXML")
        title, abstract = fetch_article_abstract(soup)
        return title, abstract, "Europe PMC (PMCID)"
    fetchers = {
        "pmid": (get_abstract_from_pmid, "PubMed / Europe PMC (PMID)"),
        "doi": (fetch_by_doi, "DOI via Semantic Scholar / CrossRef"),
        "arxiv": (fetch_by_arxiv, "arXiv"),
        "openalex": (fetch_by_openalex, "OpenAlex"),
        "semantic_scholar": (fetch_by_semantic_scholar, "Semantic Scholar"),
    }
    if input_type in fetchers:
        fetcher, source = fetchers[input_type]
        title, abstract = fetcher(value)
        return title, abstract, source
    raise ValueError("Nao foi possivel identificar o formato do ID ou URL.")
