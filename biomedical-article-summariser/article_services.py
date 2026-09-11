"""Busca, normalizacao e cache de artigos cientificos."""

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
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


AREA_KEYWORDS = {
    "Todas": [],
    "Cardiologia": ["cardio", "heart", "coronary", "myocard", "arrhythmia", "hypertension", "vascular"],
    "Oncologia": ["cancer", "tumor", "oncology", "neoplasia", "carcinoma", "chemotherapy", "radiotherapy"],
    "Endocrinologia": ["diabetes", "insulin", "endocr", "metabolic", "thyroid", "glucose", "hormone"],
    "Infectologia": ["infection", "sepsis", "virus", "bacteria", "infectious", "covid", "antibiotic"],
    "Neurologia": ["neuro", "brain", "stroke", "parkinson", "alzheim", "epilepsy", "cognitive"],
    "Pulmologia": ["lung", "pulmonary", "asthma", "copd", "respiratory"],
    "Imunologia": ["immune", "immun", "inflammation", "autoimmun", "cytokine", "allergy"],
    "Nefrologia": ["kidney", "renal", "dialysis", "glomerul", "nephro"],
    "Pediatria": ["pediatric", "child", "newborn", "infant", "adolescent"],
}


def _area_matches(title: str, journal: str, area: str) -> bool:
    if not area or area == "Todas":
        return True
    haystack = f"{title} {journal}".lower()
    keywords = AREA_KEYWORDS.get(area, [])
    return any(keyword in haystack for keyword in keywords)


def _reliability_label_for_item(item: dict) -> tuple[str, float]:
    journal = (item.get("journalTitle") or "").lower()
    source = (item.get("source") or "").upper()
    is_open = bool(item.get("isOpenAccess"))
    citations = int(item.get("citedByCount") or 0)

    score = 0.60
    if source in {"MED", "PMC"}:
        score += 0.20
    if any(name in journal for name in ["nejm", "nature", "lancet", "jama", "bmj", "cell", "science"]):
        score += 0.15
    if is_open:
        score += 0.05
    if citations > 0:
        score += min(citations / 1000, 0.15)

    score = min(score, 0.99)
    source_labels = {
        "MED": "PubMed / Europe PMC",
        "PMC": "PubMed / Europe PMC",
        "OPENALEX": "OpenAlex",
        "SEMANTIC_SCHOLAR": "Semantic Scholar",
        "CROSSREF": "Crossref",
        "ARXIV": "arXiv",
    }
    source_label = source_labels.get(source, source or "Fonte externa")
    if score >= 0.90:
        return f"Alta confiabilidade · {source_label}", round(score, 2)
    if score >= 0.75:
        return f"Boa confiabilidade · {source_label}", round(score, 2)
    return f"Confiabilidade moderada · {source_label}", round(score, 2)


def _search_europe_pmc(keyword: str, page_size: int) -> list[dict]:
    response = requests.get(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        params={"query": keyword, "resultType": "core", "format": "json", "pageSize": page_size},
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("resultList", {}).get("result", [])


def _search_openalex(keyword: str, page_size: int) -> list[dict]:
    response = requests.get(
        "https://api.openalex.org/works",
        params={
            "search": keyword,
            "per-page": page_size,
        },
        headers={"User-Agent": "BiomedicalDataDigger/1.0"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("results", [])


def _search_semantic_scholar(keyword: str, page_size: int) -> list[dict]:
    response = requests.get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={
            "query": keyword,
            "limit": page_size,
            "fields": "title,year,venue,externalIds,citationCount,paperId",
        },
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("data", [])


def _search_crossref(keyword: str, page_size: int) -> list[dict]:
    response = requests.get(
        "https://api.crossref.org/works",
        params={
            "query": keyword,
            "rows": page_size,
        },
        headers={"User-Agent": "BiomedicalDataDigger/1.0"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("message", {}).get("items", [])


def _search_arxiv(keyword: str, page_size: int) -> list[dict]:
    response = requests.get(
        "https://export.arxiv.org/api/query",
        params={"search_query": f'all:"{keyword}"', "max_results": page_size},
        timeout=15,
    )
    response.raise_for_status()
    feed = bs(response.content, "lxml-xml")
    return feed.find_all("entry")


def _year_from_crossref(item: dict) -> str:
    date_parts = item.get("published", {}).get("date-parts", [[]])
    return str(date_parts[0][0]) if date_parts and date_parts[0] else "—"


def _normalize_search_result(item: dict, source: str) -> dict:
    if source == "MED":
        return {
            "title": item.get("title") or "Título não informado",
            "pmid": str(item.get("pmid") or ""),
            "journal": item.get("journalTitle") or "Revista não informada",
            "year": item.get("pubYear") or "—",
            "doi": item.get("doi") or "",
            "source": source,
            "cited_by": int(item.get("citedByCount") or 0),
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{item.get('pmid')}/" if item.get("pmid") else "",
        }
    if source == "OPENALEX":
        location = item.get("primary_location") or {}
        return {
            "title": item.get("title") or "Título não informado",
            "pmid": "",
            "journal": (location.get("source") or {}).get("display_name") or "Revista não informada",
            "year": item.get("publication_year") or "—",
            "doi": (item.get("doi") or "").replace("https://doi.org/", ""),
            "source": source,
            "cited_by": int(item.get("cited_by_count") or 0),
            "url": item.get("doi") or item.get("id") or "",
        }
    if source == "SEMANTIC_SCHOLAR":
        external_ids = item.get("externalIds") or {}
        return {
            "title": item.get("title") or "Título não informado",
            "pmid": str(external_ids.get("PubMed") or ""),
            "journal": item.get("venue") or "Revista não informada",
            "year": item.get("year") or "—",
            "doi": external_ids.get("DOI") or "",
            "source": source,
            "cited_by": int(item.get("citationCount") or 0),
            "url": f"https://www.semanticscholar.org/paper/{item.get('paperId')}" if item.get("paperId") else "",
        }
    if source == "CROSSREF":
        titles = item.get("title") or []
        journals = item.get("container-title") or []
        return {
            "title": titles[0] if titles else "Título não informado",
            "pmid": "",
            "journal": journals[0] if journals else "Revista não informada",
            "year": _year_from_crossref(item),
            "doi": item.get("DOI") or "",
            "source": source,
            "cited_by": int(item.get("is-referenced-by-count") or 0),
            "url": item.get("URL") or (f"https://doi.org/{item.get('DOI')}" if item.get("DOI") else ""),
        }
    title = clean_text(item.find("title").get_text()) if item.find("title") else "Título não informado"
    arxiv_url = item.find("id").get_text(strip=True) if item.find("id") else ""
    published = item.find("published")
    year = published.get_text(strip=True)[:4] if published else "—"
    return {
        "title": title,
        "pmid": "",
        "journal": "arXiv",
        "year": year,
        "doi": "",
        "source": source,
        "cited_by": 0,
        "url": arxiv_url,
    }


def _deduplicate_articles(articles: list[dict]) -> list[dict]:
    unique = {}
    for article in articles:
        key = (article["doi"] or article["pmid"] or re.sub(r"\W+", " ", article["title"]).strip().lower())
        if key and key not in unique:
            unique[key] = article
    return list(unique.values())


def search_reliable_articles(keyword: str, limit: int = 5, area: str = "Todas") -> list[dict]:
    """Busca artigos em todas as fontes suportadas e ordena os resultados."""
    if not keyword or not keyword.strip():
        return []

    page_size = max(1, min(int(limit or 5), 10))
    source_searchers = {
        "MED": _search_europe_pmc,
        "OPENALEX": _search_openalex,
        "SEMANTIC_SCHOLAR": _search_semantic_scholar,
        "CROSSREF": _search_crossref,
        "ARXIV": _search_arxiv,
    }
    fetch_size = min(max(page_size * 2, 10), 25)
    raw_results = []
    failures = []
    with ThreadPoolExecutor(max_workers=len(source_searchers)) as executor:
        pending = {
            executor.submit(searcher, keyword.strip(), fetch_size): source
            for source, searcher in source_searchers.items()
        }
        for future in as_completed(pending):
            source = pending[future]
            try:
                raw_results.extend(
                    _normalize_search_result(item, source)
                    for item in future.result()
                )
            except Exception as error:
                failures.append(f"{source}: {error}")

    if not raw_results and failures:
        raise RuntimeError("Nenhuma fonte de artigos respondeu. " + " | ".join(failures))

    ranked = []
    for item in _deduplicate_articles(raw_results):
        if not _area_matches(item["title"], item["journal"], area):
            continue

        reliability_label, reliability_score = _reliability_label_for_item(item)
        item["reliability"] = reliability_label
        item["reliability_score"] = reliability_score
        ranked.append(item)

    ranked.sort(key=lambda item: (item["reliability_score"], item["cited_by"]), reverse=True)
    return ranked[:page_size]


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
