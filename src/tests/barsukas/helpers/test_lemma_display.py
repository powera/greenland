"""Tests for barsukas.helpers.lemma_display."""

from types import SimpleNamespace
from typing import List

import pytest

from barsukas.helpers.lemma_display import (
    build_lemma_pronunciation_rows,
    get_pronunciation_languages,
    group_derivative_forms,
    group_populated_pronunciations,
)


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


class TestGroupPopulatedPronunciations:
    """Tests for the pronunciation grouping helper."""

    def test_empty_input(self) -> None:
        assert group_populated_pronunciations([]) == {}

    def test_groups_forms_with_either_pronunciation_field(self) -> None:
        populated = [
            SimpleNamespace(
                language_code="en",
                grammatical_form="base",
                derivative_form_text="eat",
                ipa_pronunciation="/iːt/",
                phonetic_pronunciation=None,
            ),
            SimpleNamespace(
                language_code="fr",
                grammatical_form="base",
                derivative_form_text="manger",
                ipa_pronunciation=None,
                phonetic_pronunciation="mahn-ZHAY",
            ),
        ]

        grouped = group_populated_pronunciations(populated)

        assert list(grouped.keys()) == ["en", "fr"]
        assert grouped["en"][0].derivative_form_text == "eat"
        assert grouped["fr"][0].derivative_form_text == "manger"

    def test_skips_forms_without_populated_pronunciation_fields(self) -> None:
        grouped = group_populated_pronunciations(
            [
                SimpleNamespace(
                    language_code="en",
                    grammatical_form="base",
                    derivative_form_text="eat",
                    ipa_pronunciation="",
                    phonetic_pronunciation="",
                )
            ]
        )

        assert grouped == {}


class TestBuildLemmaPronunciationRows:
    """Tests for lemma/base pronunciation row aggregation."""

    def test_prefers_translation_pronunciations_and_falls_back_to_base_form(self) -> None:
        derivative_forms = [
            SimpleNamespace(
                language_code="en",
                grammatical_form="infinitive",
                derivative_form_text="eat",
                is_base_form=True,
                ipa_pronunciation="/iːt/",
                phonetic_pronunciation="EET",
            ),
            SimpleNamespace(
                language_code="es",
                grammatical_form="infinitive",
                derivative_form_text="comer",
                is_base_form=True,
                ipa_pronunciation="/koˈmeɾ/",
                phonetic_pronunciation="koh-MEHR",
            ),
        ]

        rows = build_lemma_pronunciation_rows(
            derivative_forms=derivative_forms,
            translations={"en": "eat", "es": "comer"},
            translation_pronunciations={"en": (None, None), "es": ("/koˈmeɾ/", "ko-MEHR")},
        )

        assert rows["en"]["source"] == "base_form"
        assert rows["en"]["ipa"] == "/iːt/"
        assert rows["es"]["source"] == "lemma_translation"
        assert rows["es"]["phonetic"] == "ko-MEHR"

    def test_skips_languages_without_any_pronunciation_data(self) -> None:
        rows = build_lemma_pronunciation_rows(
            derivative_forms=[],
            translations={"en": "eat", "fr": "manger"},
            translation_pronunciations={"en": (None, None), "fr": (None, None)},
        )

        assert rows == {}


class TestGetPronunciationLanguages:
    """Tests for eligible pronunciation language selection."""

    def test_includes_languages_from_forms_and_translations(self) -> None:
        languages = get_pronunciation_languages(
            derivative_forms=[_form("fr", "infinitive", "manger")],
            translations={"en": "eat", "es": "comer", "de": None, "it": "  "},
        )

        assert languages == ["en", "es", "fr"]
