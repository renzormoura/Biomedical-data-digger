"""A interface e os avisos gerados pelo servidor nao usam emoji (identidade institucional)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import pages

ROOT = Path(__file__).resolve().parent.parent / "nexus-science"
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⛔✅]")
UI_FILES = [
    "static/browse.js", "static/app.js", "templates/browse.html", "templates/ia.html", "templates/_footer.html",
    "pages.py", "workflow.py", "grounding.py", "presentation.py", "extraction_view.py",
]


@pytest.mark.parametrize("name", UI_FILES)
def test_ui_sources_have_no_emoji(name):
    text = (ROOT / name).read_text(encoding="utf-8")
    assert not EMOJI.search(text), f"emoji em {name}: {EMOJI.findall(text)}"


def test_tab_names_are_plain_text():
    for page in pages.ALL_PAGES:
        assert page.tab_name == page.title and page.tab_name[0].isalpha()
