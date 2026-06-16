"""Tests for shared language registry metadata."""

from storage.translation_helpers import (
    LANG_CODE_TO_LLM_FIELD,
    LANGUAGE_FIELDS,
    LANGUAGE_HIERARCHY,
    LANGUAGE_NAMES,
    LLM_FIELD_TO_LANG_CODE,
    SECONDARY_RELEASE_LANGUAGES,
    TIER_4_LANGUAGES,
    get_language_name,
)


def test_latin_and_sanskrit_are_tier4_languages() -> None:
    """Latin and Sanskrit are available as tier-4 row-based translation languages."""
    assert "la" in TIER_4_LANGUAGES
    assert "sa" in TIER_4_LANGUAGES
    assert "la" in SECONDARY_RELEASE_LANGUAGES
    assert "sa" in SECONDARY_RELEASE_LANGUAGES


def test_latin_and_sanskrit_language_metadata() -> None:
    """Language display names and storage mappings come from translation_helpers."""
    assert LANGUAGE_FIELDS["la"] == ("la", "Latin", True)
    assert LANGUAGE_FIELDS["sa"] == ("sa", "Sanskrit", True)
    assert LANGUAGE_NAMES["la"] == "Latin"
    assert LANGUAGE_NAMES["sa"] == "Sanskrit"
    assert get_language_name("la") == "Latin"
    assert get_language_name("sa") == "Sanskrit"
    assert LANGUAGE_HIERARCHY.index("la") < LANGUAGE_HIERARCHY.index("ms")
    assert LANGUAGE_HIERARCHY.index("sa") < LANGUAGE_HIERARCHY.index("ms")


def test_latin_and_sanskrit_llm_field_mappings() -> None:
    """LLM translation field names map cleanly to ISO-style language codes."""
    assert LLM_FIELD_TO_LANG_CODE["latin_translation"] == "la"
    assert LLM_FIELD_TO_LANG_CODE["sanskrit_translation"] == "sa"
    assert LANG_CODE_TO_LLM_FIELD["la"] == "latin_translation"
    assert LANG_CODE_TO_LLM_FIELD["sa"] == "sanskrit_translation"
