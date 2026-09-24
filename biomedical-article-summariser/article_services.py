"""Busca, normalizacao e cache de artigos cientificos."""

import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from functools import wraps
from typing import Tuple
from urllib.parse import parse_qs, urlparse

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


GOOGLE_SCHOLAR_HOSTS = ("scholar.google.com", "scholar.google")


def _looks_like_url(value: str) -> bool:
    if value.startswith(("http://", "https://")):
        return True
    domain_pattern = r"^[\w-]+(\.[\w-]+)+(/|\?|$|#|:)"
    return bool(re.match(domain_pattern, value, re.IGNORECASE)) and " " not in value


def _normalize_url(value: str) -> str:
    if value.startswith(("http://", "https://")):
        return value
    return f"https://{value}"


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

    # DOI embutido em qualquer URL (ex.: pagina da editora, scholar com query doi)
    doi_in_url = re.search(r"(10\.\d{4,9}/\S+?)(?=$|[\s])", value)
    if doi_in_url:
        doi = doi_in_url.group(1).rstrip(".,;)")
        return "doi", doi

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

    # Google Academico: cluster, links= e paginas de resultado viram busca por titulo
    if any(host in value.lower() for host in GOOGLE_SCHOLAR_HOSTS):
        return "google_scholar", _normalize_url(value)

    # Qualquer outro link: tratar como pagina de artigo generica
    if _looks_like_url(value):
        return "generic_url", _normalize_url(value)

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


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
}


def _meta_content(soup: bs, *names: str) -> str:
    for name in names:
        for attr in ("name", "property"):
            tag = soup.find("meta", attrs={attr: name})
            if tag and tag.get("content", "").strip():
                return tag["content"].strip()
    return ""


def _title_lookup(query: str) -> Article:
    """Busca o artigo mais relevante por titulo/palavra-chave nas APIs abertas."""
    searchers = (
        (
            "Europe PMC",
            lambda: _search_europe_pmc(query, 3),
            lambda item: (
                item.get("title", ""),
                clean_text(item.get("abstractText", "")),
            ),
        ),
        (
            "Semantic Scholar",
            lambda: _search_semantic_scholar(query, 3),
            lambda item: (
                item.get("title", ""),
                "",
            ),
        ),
        (
            "OpenAlex",
            lambda: _search_openalex(query, 3),
            lambda item: (
                item.get("title", ""),
                _abstract_from_inverted_index(item.get("abstract_inverted_index")),
            ),
        ),
    )
    for source_name, searcher, extractor in searchers:
        try:
            for item in searcher():
                title, abstract = extractor(item)
                if title and abstract:
                    return title, abstract
                if title:
                    last_title_only = title
        except Exception:
            continue
    return last_title_only or f"Nenhum resultado encontrado para: {query}", ""


def _abstract_from_inverted_index(inverted: dict | None) -> str:
    if not inverted:
        return ""
    try:
        words = [""] * (max(position for positions in inverted.values() for position in positions) + 1)
        for word, positions in inverted.items():
            for position in positions:
                words[position] = word
        return clean_text(" ".join(words))
    except Exception:
        return ""


def _query_from_slug(url: str) -> str:
    """Converte o slug final de uma URL em texto pesquisavel (ex.: /article/titulo-longo)."""
    path = urlparse(url if "//" in url else f"https://{url}").path
    slug = [segment for segment in path.split("/") if segment][-1] if path.strip("/") else ""
    words = re.split(r"[-_]+", slug)
    meaningful = [w for w in words if len(w) > 2 and not re.fullmatch(r"[A-Z]?\d+", w)]
    if len(meaningful) < 4:
        return ""
    return " ".join(meaningful)


def _extract_identifier_from_url(url: str) -> tuple[str, str]:
    """Extrai (tipo, id) de URLs de editoras sem depender de acessar a pagina.

    Suporta PII da Elsevier/ScienceDirect (resolvido depois no Crossref),
    DOI embutido no caminho e Springer article IDs.
    """
    doi_match = re.search(r"(10\.\d{4,9}/[^\s?#&]+)", url)
    if doi_match:
        return "doi", doi_match.group(1).rstrip(".,;)")
    pii_match = re.search(r"/pii/([A-Z0-9]{16,20})", url, re.IGNORECASE)
    if pii_match:
        return "pii", pii_match.group(1).upper()
    springer_match = re.search(r"/(?:article|chapter)/(10\d{3,4}/\d+)", url, re.IGNORECASE)
    if springer_match:
        return "doi", springer_match.group(1)
    return "", ""


def _pii_to_doi(pii: str) -> str:
    """Deriva o DOI no formato antigo da Elsevier a partir do PII (heuristica).

    PII: S + ISSN(8) + ano(2) + item(5) + check(1) -> 10.1016/s0378-7788(01)00137-2
    Nem todo artigo segue esse padrao, entao o resultado e sempre validado.
    """
    if len(pii) != 17 or not pii.startswith("S"):
        return ""
    issn, year, item, check = pii[1:9], pii[9:11], pii[11:16], pii[16]
    if not (issn + item + check).isdigit():
        return ""
    return f"10.1016/{pii[0]}{issn[:4]}-{issn[4:]}({year}){item}-{check}".lower()


def _fetch_by_crossref_alternative_id(alternative_id: str) -> Article:
    """Localiza o artigo no Crossref por alternative-id (ex.: PII da Elsevier)."""
    try:
        response = requests.get(
            "https://api.crossref.org/works",
            params={"filter": f"alternative-id:{alternative_id}", "rows": 1},
            headers={"User-Agent": "BiomedicalDataDigger/1.0"},
            timeout=15,
        )
        response.raise_for_status()
        items = response.json().get("message", {}).get("items", [])
        if not items:
            return "", ""
        item = items[0]
        titles = item.get("title") or []
        title = titles[0] if titles else ""
        abstract = clean_text(re.sub(r"<[^>]+>", " ", item.get("abstract", "")))
        return title, abstract
    except Exception:
        return "", ""


def fetch_from_generic_url(url: str) -> Article:
    """Extrai titulo e resumo de qualquer pagina de artigo usando meta tags."""
    # Identificador na propria URL resolve sem precisar acessar a pagina
    id_type, identifier = _extract_identifier_from_url(url)
    if id_type == "doi":
        doi_title, doi_abstract = fetch_by_doi(identifier)
        if doi_abstract:
            return doi_title, doi_abstract
    elif id_type == "pii":
        crossref_title, crossref_abstract = _fetch_by_crossref_alternative_id(identifier)
        if crossref_title and crossref_abstract:
            return crossref_title, crossref_abstract
        derived_doi = _pii_to_doi(identifier)
        if derived_doi:
            doi_title, doi_abstract = fetch_by_doi(derived_doi)
            if doi_abstract:
                return doi_title, doi_abstract

    try:
        response = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
        response.raise_for_status()
        soup = bs(response.content, "lxml")

        title = (
            _meta_content(soup, "citation_title", "citation_journal_title")
            or _meta_content(soup, "og:title", "twitter:title")
            or (soup.title.get_text(strip=True) if soup.title else "")
            or "Titulo nao encontrado"
        )
        abstract = _meta_content(
            soup,
            "citation_abstract",
            "description",
            "og:description",
            "twitter:description",
        )
        abstract = clean_text(re.sub(r"<[^>]+>", " ", abstract))
        if title and abstract:
            return title, abstract

        # Sem meta tags uteis: tentar localizar um DOI na pagina e buscar nas APIs
        doi = _meta_content(soup, "citation_doi", "dc.doi") or ""
        if not doi:
            doi_match = re.search(r"10\.\d{4,9}/\S+", soup.get_text(" ", strip=True)[:20000])
            doi = doi_match.group(0).rstrip(".,;)") if doi_match else ""
        if doi:
            doi_title, doi_abstract = fetch_by_doi(doi)
            if doi_abstract:
                return doi_title, doi_abstract

        # Identificador extraido da URL como plano B (PII no Crossref)
        if id_type == "pii":
            crossref_title, crossref_abstract = _fetch_by_crossref_alternative_id(identifier)
            if crossref_title:
                return crossref_title, crossref_abstract

        # Ultimo recurso: usar as primeiras linhas de texto visivel da pagina
        body_text = clean_text(soup.body.get_text(" ", strip=True)) if soup.body else ""
        if body_text and len(body_text) > 200:
            return title, body_text[:4000]
        return title, abstract
    except Exception as error:
        # Pagina bloqueada (403 etc.): tentar ainda o identificador da URL
        if id_type == "pii":
            crossref_title, crossref_abstract = _fetch_by_crossref_alternative_id(identifier)
            if crossref_title:
                return crossref_title, crossref_abstract
            derived_doi = _pii_to_doi(identifier)
            if derived_doi:
                doi_title, doi_abstract = fetch_by_doi(derived_doi)
                if doi_title and doi_title != "Artigo nao encontrado via DOI":
                    return doi_title, doi_abstract
        if id_type == "doi":
            doi_title, doi_abstract = fetch_by_doi(identifier)
            if doi_title and doi_title != "Artigo nao encontrado via DOI":
                return doi_title, doi_abstract
        # Ultimo recurso: buscar o artigo pelas APIs abertas usando a slug da URL
        slug_text = _query_from_slug(url)
        if slug_text:
            lookup_title, lookup_abstract = _title_lookup(slug_text)
            if lookup_abstract:
                return lookup_title, lookup_abstract
            if lookup_title and not str(lookup_title).startswith("Nenhum resultado"):
                return lookup_title, ""
        return f"Erro ao acessar a pagina: {error}", ""


def fetch_from_google_scholar(scholar_url: str) -> Article:
    """Resolve links do Google Academico (cluster, resultado, busca ou redirecionamento)."""
    parsed = urlparse(scholar_url if "//" in scholar_url else f"https://{scholar_url}")
    params = parse_qs(parsed.query)

    # Link copiado de um resultado (scholar_url?url=...) aponta para o artigo real
    target = params.get("url", [""])[0]
    if target:
        return fetch_from_generic_url(target)

    # Pagina de cluster: um artigo especifico agrupado
    if params.get("cluster"):
        try:
            response = requests.get(
                f"https://scholar.google.com/scholar?cluster={params['cluster'][0]}&hl=en",
                headers=BROWSER_HEADERS,
                timeout=15,
            )
            response.raise_for_status()
            soup = bs(response.content, "lxml")
            first_title = soup.select_one("h3.gs_rt")
            if first_title:
                title_text = first_title.get_text(strip=True)
                title, abstract = _title_lookup(title_text)
                if abstract:
                    return title, abstract
                return fetch_from_generic_url(_first_result_link(soup)) if _first_result_link(soup) else (title_text, "")
        except Exception:
            pass

    # Pagina de busca: usar a consulta q= para encontrar o artigo nas APIs abertas
    query = params.get("q", [""])[0] or params.get("as_q", [""])[0]
    if query:
        return _title_lookup(query)

    # Qualquer outra pagina do Academico: extrair o que der da propria pagina
    return fetch_from_generic_url(scholar_url)


def _first_result_link(soup: bs) -> str:
    for anchor in soup.select("h3.gs_rt a[href]"):
        href = anchor.get("href", "")
        if href.startswith("http"):
            return href
    return ""


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
    "Tecnologia e Computacao": ["computer", "computing", "software", "hardware", "technology", "artificial intelligence", "machine learning", "deep learning", "data science", "cybersecurity", "internet", "algorithm"],
    "Engenharia Civil": ["civil engineering", "construction", "building", "concrete", "structural", "geotechnical", "pavement", "transportation", "infrastructure"],
    "Engenharia Eletrica": ["electrical engineering", "electric", "power system", "energy", "circuit", "electronics", "robotics", "telecommunication", "signal processing"],
    "Engenharia Quimica": ["chemical engineering", "process engineering", "catalysis", "polymer", "reactor", "thermodynamic", "separation", "bioprocess"],
    "Quimica": ["chemistry", "chemical", "molecule", "compound", "synthesis", "spectroscopy", "analytical chemistry", "organic chemistry", "inorganic chemistry"],
    "Fisica": ["physics", "quantum", "particle", "astrophysics", "relativity", "mechanics", "thermodynamics", "condensed matter"],
    "Matematica e Estatistica": ["mathematics", "mathematical", "statistics", "statistical", "probability", "regression", "optimization", "theorem"],
    "Ciencias Sociais e Sociologia": ["sociology", "social science", "social behavior", "society", "inequality", "community", "demographic", "migration", "social policy"],
    "Psicologia": ["psychology", "psychological", "mental health", "behavior", "cognition", "emotion", "therapy", "personality"],
    "Economia e Negocios": ["economics", "economic", "business", "finance", "management", "market", "entrepreneurship", "organization", "commerce"],
    "Educacao": ["education", "teaching", "learning", "school", "student", "curriculum", "pedagogy", "university", "academic"],
    "Direito e Politicas Publicas": ["law", "legal", "justice", "policy", "public policy", "governance", "regulation", "human rights"],
    "Meio Ambiente e Sustentabilidade": ["environment", "environmental", "sustainability", "climate", "ecology", "pollution", "biodiversity", "renewable", "conservation"],
    "Agricultura e Alimentos": ["agriculture", "crop", "food", "soil", "plant science", "livestock", "irrigation", "nutrition"],
}


def _area_matches(title: str, journal: str, area: str) -> bool:
    if not area or area == "Todas":
        return True
    haystack = f"{title} {journal}".lower()
    keywords = AREA_KEYWORDS.get(area, [])
    return any(keyword in haystack for keyword in keywords)


def _bibliographic_relevance_for_item(item: dict) -> tuple[str, float]:
    """Calcula um indicador transparente de relevancia para descoberta bibliografica.

    O indicador nao avalia a qualidade metodologica do estudo. Ele combina impacto
    de citacoes ajustado pela idade, atualidade, completude dos metadados e cobertura
    da fonte, todos normalizados para o intervalo de 0 a 1.
    """
    journal = (item.get("journal") or item.get("journalTitle") or "").lower()
    source = (item.get("source") or "").upper()
    citations = int(item.get("cited_by") or item.get("citedByCount") or 0)
    year_value = item.get("year") or item.get("pubYear")
    try:
        publication_year = int(str(year_value)[:4])
    except (TypeError, ValueError):
        publication_year = None

    current_year = datetime.now().year
    age = max(1, current_year - publication_year) if publication_year else 10
    citation_rate = citations / age
    impact_score = min(citation_rate / 20, 1.0)
    recency_score = max(0.0, 1.0 - (age / 15)) if publication_year else 0.0
    metadata_fields = [
        item.get("title"),
        journal,
        publication_year,
        item.get("doi") or item.get("pmid"),
        item.get("url"),
    ]
    metadata_score = sum(bool(field) for field in metadata_fields) / len(metadata_fields)
    source_score = {
        "MED": 1.0,
        "PMC": 1.0,
        "OPENALEX": 0.95,
        "SEMANTIC_SCHOLAR": 0.90,
        "CROSSREF": 0.85,
        "ARXIV": 0.80,
    }.get(source, 0.70)

    score = (
        impact_score * 0.40
        + recency_score * 0.25
        + metadata_score * 0.20
        + source_score * 0.15
    )
    score = round(min(max(score, 0.0), 0.99), 2)
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
        return f"Alta relevância bibliográfica · {source_label}", score
    if score >= 0.75:
        return f"Boa relevância bibliográfica · {source_label}", score
    return f"Relevância bibliográfica moderada · {source_label}", score


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

        relevance_label, relevance_score = _bibliographic_relevance_for_item(item)
        item["reliability"] = relevance_label
        item["reliability_score"] = relevance_score
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
        "google_scholar": (fetch_from_google_scholar, "Google Academico"),
        "generic_url": (fetch_from_generic_url, "Pagina do artigo"),
    }
    if input_type in fetchers:
        fetcher, source = fetchers[input_type]
        title, abstract = fetcher(value)
        return title, abstract, source
    # Ultimo recurso: parece uma URL mesmo sem formato reconhecido
    if _looks_like_url(value):
        title, abstract = fetch_from_generic_url(_normalize_url(value))
        return title, abstract, "Pagina do artigo"
    raise ValueError("Nao foi possivel identificar o formato do ID ou URL.")
