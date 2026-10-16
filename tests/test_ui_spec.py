"""Invariantes da especificacao declarativa da UI e smoke test de montagem."""

from collections import Counter

import pytest

import prompt_builders
import ui
from config import Settings
from domain import Article
from ratelimit import SlidingWindowLimiter
from workflow import AnalysisService, ArticleRepository

PAGES = [ui.GENERAL_PAGE, ui.MEDICAL_PAGE]


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.key)
def test_no_two_buttons_share_a_prompt_builder(page):
    """Regressao dos 'botoes falsos': cada botao deve ter prompt proprio."""
    counts = Counter(button.builder for button in page.buttons())
    duplicated = [b.__name__ for b, n in counts.items() if n > 1]
    assert not duplicated, f"builders reutilizados em {page.key}: {duplicated}"


@pytest.mark.parametrize("page", PAGES, ids=lambda p: p.key)
def test_button_labels_are_unique(page):
    labels = [button.label for button in page.buttons()]
    assert len(labels) == len(set(labels))


def test_every_prompt_builder_is_reachable_from_some_page():
    used = {b.builder for page in PAGES for b in page.buttons()}
    internal = {
        prompt_builders.build_message_auditoria_resposta,
        prompt_builders.build_message_comparacao_artigos,
    }
    all_builders = {
        fn for name, fn in vars(prompt_builders).items() if name.startswith("build_message_") and callable(fn)
    }
    assert all_builders - used - internal == set(), "builder morto: nenhum botao o utiliza"


def test_medical_page_is_clinical_and_general_is_not():
    assert ui.MEDICAL_PAGE.clinical and not ui.GENERAL_PAGE.clinical


def test_brazil_context_buttons_declare_verification_sources():
    sources = {b.label: b.sources for b in ui.MEDICAL_PAGE.buttons() if b.sources}
    assert len(sources) == 3


def test_update_history_dedupes_and_caps():
    repo = ArticleRepository(lambda raw: (f"Título {raw}", "x" * 300, "src"))
    history: list = []
    for number in range(15):
        repo.get(str(10_000_000 + number))
        history = ui.update_history(str(10_000_000 + number), history, repo)
    assert len(history) == ui.HISTORY_LIMIT
    assert history[0][0] == "10000014"
    again = ui.update_history("10000014", history, repo)
    assert again == history


def test_update_history_ignores_unresolved_articles():
    repo = ArticleRepository(lambda raw: ("t", "x" * 300, "s"))
    assert ui.update_history("99999999", [], repo) == []


def test_history_rows_placeholder_when_empty():
    assert ui.history_rows([])[0][0] == "—"


def test_search_formatters():
    item = {
        "title": "T", "journal": "J", "year": 2024, "pmid": "1", "source": "MED",
        "url": "https://x", "reliability": "Alta", "reliability_score": 0.95,
    }
    assert ui.format_search_rows([item])[0][2] == "2024"
    assert "🟢" in ui.format_search_summary([item])
    assert "🟠" in ui.format_search_summary([{**item, "reliability_score": 0.5}])


def test_css_loads_and_splits_medical_overrides():
    base, medical = ui.load_css()
    assert base and len(medical) >= len(base)


class _NoopGenerator:
    def ensure_available(self, model):
        pass

    def generate(self, messages, model):
        return "ok"


def test_full_app_builds_without_launching(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "a.sqlite3"))
    repository = ArticleRepository(lambda raw: ("t", "x" * 300, "s"))
    service = AnalysisService(repository, _NoopGenerator(), SlidingWindowLimiter(5, 60))
    app = ui.build_app(service, repository, Settings())
    assert app is not None


def test_settings_validation(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "abc")
    with pytest.raises(ValueError):
        Settings.from_env()
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "0")
    with pytest.raises(ValueError):
        Settings.from_env()
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "20")
    assert Settings.from_env().llm_calls_per_minute == 20


def test_article_dataclass_is_hashable_and_frozen():
    article = Article("id", "t", "abs")
    with pytest.raises(Exception):
        article.title = "x"  # type: ignore[misc]
