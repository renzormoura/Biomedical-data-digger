"""Testes baseados em propriedades (Hypothesis) para o parsing de identificadores."""

from hypothesis import given, settings
from hypothesis import strategies as st

import article_services
from grounding import check_numeric_grounding
from workflow import canonical_key, wrap_source

KNOWN_TYPES = {"pmid", "pmcid", "doi", "arxiv", "openalex", "semantic_scholar", "google_scholar", "generic_url", "unknown"}


@given(st.text(max_size=300))
@settings(max_examples=300)
def test_detect_input_type_is_total(raw):
    input_type, value = article_services.detect_input_type(raw)
    assert input_type in KNOWN_TYPES
    assert isinstance(value, str)


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=200))
@settings(max_examples=300)
def test_normalize_doi_is_idempotent(raw):
    once = article_services._normalize_doi(raw)
    assert article_services._normalize_doi(once) == once


@given(st.from_regex(r"10\.[0-9]{4,6}/[A-Za-z0-9._-]{3,30}", fullmatch=True))
def test_plain_dois_roundtrip_through_detection(doi):
    input_type, value = article_services.detect_input_type(doi)
    assert input_type == "doi"
    assert value.lower().startswith(doi.lower()[:7])


@given(st.integers(min_value=100_000, max_value=999_999_999))
def test_numeric_ids_are_pmids_and_urls_agree(pmid):
    assert article_services.detect_input_type(str(pmid)) == ("pmid", str(pmid))
    assert canonical_key(str(pmid)) == canonical_key(f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/")


@given(st.text(max_size=500))
def test_wrap_source_never_leaves_a_forged_delimiter(text):
    wrapped = wrap_source("X", text)
    inner = wrapped[len("<<<X_START>>>\n"): -len("\n<<<X_END>>>")]
    assert "<<<" not in inner and ">>>" not in inner


@given(st.text(max_size=300), st.text(max_size=300))
def test_grounding_never_raises(response, source):
    report = check_numeric_grounding(response, source)
    assert report.ok == (not report.ungrounded)


@given(st.text(max_size=300))
def test_text_is_always_grounded_in_itself(text):
    assert check_numeric_grounding(text, text).ok
