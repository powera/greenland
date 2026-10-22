"""Tests that ``voras --populate --guid`` honours --languages.

The single-lemma path built its list from every missing language and never
looked at --languages, so a run meant to fill three languages asked for all of
them (and the prompt then kept only the first ten).
"""

from __future__ import annotations

import argparse
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Sequence

import pytest

from agents.voras.cli import _handle_single_lemma_populate
from words.translation_workflow import LemmaTranslations

LEMMA = SimpleNamespace(lemma_text="be", guid="V11_027", pos_type="verb", definition_text="x")


class _FakeWorkflow:
    """Records which languages generation was asked for, and generates nothing."""

    def __init__(self, translations: Dict[str, Optional[str]]) -> None:
        self.translations = translations
        self.requested: List[str] = []

    def collect_translations(self, session: Any, lemma: Any) -> Dict[str, Optional[str]]:
        return dict(self.translations)

    def generate_translations_for_lemma(
        self, session: Any, lemma: Any, missing_languages: Sequence[str]
    ) -> LemmaTranslations:
        self.requested = list(missing_languages)
        return LemmaTranslations(error="test double")


@pytest.fixture(autouse=True)
def _no_exclusions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "words.translation_populate.excluded_translation_languages", lambda *a, **k: []
    )
    monkeypatch.setattr(
        "words.translation_populate.uncertain_translation_languages", lambda *a, **k: []
    )


def _args(languages: Optional[List[str]]) -> argparse.Namespace:
    return argparse.Namespace(languages=languages, retry_uncertain=False, dry_run=False)


def test_languages_flag_narrows_the_request() -> None:
    workflow = _FakeWorkflow({"en": "be", "fr": None, "de": None, "lt": None})

    _handle_single_lemma_populate(workflow, LEMMA, None, _args(["fr", "lt"]))

    assert workflow.requested == ["fr", "lt"]


def test_a_requested_language_already_present_is_not_asked_for() -> None:
    workflow = _FakeWorkflow({"en": "be", "fr": "être", "de": None})

    _handle_single_lemma_populate(workflow, LEMMA, None, _args(["fr", "de"]))

    assert workflow.requested == ["de"]


def test_without_the_flag_only_the_default_ten_are_asked_for() -> None:
    workflow = _FakeWorkflow(
        {"en": "be", "fr": None, "de": None, "es-419": None, "vi": None, "la": None}
    )

    _handle_single_lemma_populate(workflow, LEMMA, None, _args(None))

    assert workflow.requested == ["fr", "de", "es-419"]


def test_all_asks_for_tiers_one_to_three_only() -> None:
    workflow = _FakeWorkflow({"en": "be", "fr": None, "vi": None, "es-419": None, "la": None})

    _handle_single_lemma_populate(workflow, LEMMA, None, _args(["all"]))

    assert workflow.requested == ["fr", "vi", "es-419"]


def test_ancient_asks_for_the_ancient_languages() -> None:
    workflow = _FakeWorkflow({"en": "be", "fr": None, "la": None, "grc": None})

    _handle_single_lemma_populate(workflow, LEMMA, None, _args(["ancient"]))

    assert workflow.requested == ["la", "grc"]
