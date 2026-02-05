"""Tests for barsukas.helpers.lemma_display."""

from types import SimpleNamespace
from typing import List

import pytest

from barsukas.helpers.lemma_display import group_derivative_forms


def _form(language_code: str, grammatical_form: str, text: str = "x") -> SimpleNamespace:
    """Build a lightweight stand-in for a DerivativeForm ORM object."""
    return SimpleNamespace(
        language_code=language_code,
        grammatical_form=grammatical_form,
        derivative_form_text=text,
    )


class TestGroupDerivativeForms:
    """Tests for the group_derivative_forms helper."""

    def test_empty_input(self) -> None:
        forms, synonyms, alternatives, langs = group_derivative_forms([])
        assert forms == {}
        assert synonyms == {}
        assert alternatives == {}
        assert langs == []

    def test_regular_forms_grouped_by_language(self) -> None:
        items = [
            _form("en", "present_participle", "eating"),
            _form("en", "past_tense", "ate"),
            _form("fr", "infinitive", "manger"),
        ]
        forms, synonyms, alternatives, langs = group_derivative_forms(items)

        assert len(forms["en"]) == 2
        assert len(forms["fr"]) == 1
        assert synonyms == {}
        assert alternatives == {}
        assert langs == []

    def test_synonyms_grouped_by_language(self) -> None:
        items = [
            _form("en", "synonym", "consume"),
            _form("fr", "synonym", "bouffer"),
        ]
        forms, synonyms, alternatives, langs = group_derivative_forms(items)

        assert forms == {}
        assert "en" in synonyms
        assert "fr" in synonyms
        assert sorted(langs) == ["en", "fr"]

    def test_alternative_form_types(self) -> None:
        """All four alternative form types should be recognised."""
        for alt_type in [
            "abbreviation",
            "expanded_form",
            "alternate_spelling",
            "alternative_form",
        ]:
            items = [_form("de", alt_type, "alt")]
            forms, synonyms, alternatives, langs = group_derivative_forms(items)

            assert "de" in alternatives, f"{alt_type} was not classified as alternative"
            assert forms == {}
            assert synonyms == {}

    def test_all_synonym_languages_combines_synonyms_and_alternatives(self) -> None:
        items = [
            _form("en", "synonym", "consume"),
            _form("fr", "abbreviation", "abbr"),
        ]
        _, _, _, langs = group_derivative_forms(items)
        assert sorted(langs) == ["en", "fr"]

    def test_mixed_forms(self) -> None:
        """Regular, synonym, and alternative forms are separated correctly."""
        items = [
            _form("en", "past_tense", "ate"),
            _form("en", "synonym", "consume"),
            _form("en", "alternate_spelling", "eat up"),
            _form("fr", "infinitive", "manger"),
        ]
        forms, synonyms, alternatives, langs = group_derivative_forms(items)

        assert list(forms.keys()) == ["en", "fr"]
        assert len(forms["en"]) == 1
        assert list(synonyms.keys()) == ["en"]
        assert list(alternatives.keys()) == ["en"]
        assert langs == ["en"]
