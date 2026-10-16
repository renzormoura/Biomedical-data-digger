from catalog import Work
from citations import Author
from exports import EXPORT_FORMATS, to_bibtex, to_citations, to_ris


def work(ref="1", **overrides):
    base = {
        "ref": ref, "title": "Efeito do exercício sobre a pressão arterial (exemplo).",
        "authors": (Author("Moraes Teixeira", "Helena"), Author("Bastos", "Ricardo")), "journal": "Revista Exemplo",
        "year": 2023, "volume": "41", "issue": "2", "pages": "112-124", "doi": "10.0000/exemplo.001",
        "abstract": "Resumo do artigo.", "keywords": ("hipertensão", "exercício"),
    }
    base.update(overrides)
    return Work(**base)


def test_bibtex_fields_and_pages_dash():
    bib = to_bibtex([work()])
    assert bib.startswith("@article{moraesteixeira2023efeito,")
    assert "author = {Moraes Teixeira, Helena and Bastos, Ricardo}" in bib
    assert "title = {{Efeito do exercício sobre a pressão arterial (exemplo)}}" in bib
    assert "pages = {112--124}" in bib and "volume = {41}" in bib and "number = {2}" in bib and "doi = {10.0000/exemplo.001}" in bib


def test_bibtex_keys_are_unique_and_special_characters_escaped():
    bib = to_bibtex([work("1"), work("2", title="Estudo A & B com 100% (exemplo)")])
    keys = [line.split("{")[1].rstrip(",") for line in bib.splitlines() if line.startswith("@article")]
    assert len(set(keys)) == 2
    assert "A \\& B com 100\\%" in bib


def test_bibtex_omits_empty_fields_and_handles_missing_authors():
    bib = to_bibtex([work(authors=(), volume="", issue="", pages="", doi="", year=None)])
    assert bib.startswith("@article{anon") and "volume" not in bib and "pages" not in bib and "doi" not in bib
    assert "author" not in bib and "year" not in bib


def test_ris_records():
    ris = to_ris([work(), work("2", pages="e12", keywords=(), abstract="")])
    assert ris.count("TY  - JOUR") == 2 and ris.count("ER  - ") == 2
    assert "AU  - Moraes Teixeira, Helena" in ris and "SP  - 112" in ris and "EP  - 124" in ris
    assert "KW  - hipertensão" in ris and "AB  - Resumo do artigo." in ris
    second = ris.split("\n\n")[1]
    assert "SP  - e12" in second and "EP  -" not in second and "AB  -" not in second


def test_text_citations_use_the_requested_style():
    text = to_citations([work(), work("2")], "ABNT")
    assert text.count("\n\n") == 1 and text.startswith("MORAES TEIXEIRA, H.; BASTOS, R. Efeito")
    assert to_citations([work()], "Vancouver").startswith("Moraes Teixeira H, Bastos R.")


def test_export_formats_registry_is_complete():
    assert set(EXPORT_FORMATS) == {"bibtex", "ris", "abnt", "apa", "vancouver"}
    for filename, mime, build in EXPORT_FORMATS.values():
        assert filename and mime and build([work()])
    assert to_bibtex([]) == "" and to_ris([]) == ""
