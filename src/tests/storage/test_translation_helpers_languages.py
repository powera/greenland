"""Tests for shared language registry metadata."""

from storage.translation_helpers import (
    ANCIENT_LANGUAGE_GROUP,
    EXTRA_RELEASE_LANGUAGE_GROUPS,
    LANG_CODE_TO_LLM_FIELD,
    LANGUAGE_FIELDS,
    LANGUAGE_HIERARCHY,
    LANGUAGE_NAMES,
    LLM_FIELD_TO_LANG_CODE,
    SECONDARY_RELEASE_LANGUAGES,
    TIER_4_LANGUAGES,
    get_language_name,
)
from wordfreq.translation.constants import DEFAULT_TRANSLATION_LANGUAGES_BY_CODE


def test_ancient_languages_are_tier4_languages() -> None:
    """Ancient languages are available as tier-4 row-based translation languages."""
    assert ANCIENT_LANGUAGE_GROUP == ["la", "sa", "grc", "ar-classical", "non"]
    assert EXTRA_RELEASE_LANGUAGE_GROUPS["ancient"] == ANCIENT_LANGUAGE_GROUP
    for language_code in ANCIENT_LANGUAGE_GROUP:
        assert language_code in TIER_4_LANGUAGES
        assert language_code not in SECONDARY_RELEASE_LANGUAGES


def test_ancient_language_metadata() -> None:
    """Language display names and storage mappings come from translation_helpers."""
    assert LANGUAGE_FIELDS["la"] == ("la", "Latin", True)
    assert LANGUAGE_FIELDS["sa"] == ("sa", "Sanskrit", True)
    assert LANGUAGE_FIELDS["grc"] == ("grc", "Ancient Greek", True)
    assert LANGUAGE_FIELDS["ar-classical"] == (
        "ar-classical",
        "Classical Arabic (pre-1200)",
        True,
    )
    assert LANGUAGE_FIELDS["non"] == ("non", "Old Norse", True)
    assert LANGUAGE_NAMES["la"] == "Latin"
    assert LANGUAGE_NAMES["sa"] == "Sanskrit"
    assert LANGUAGE_NAMES["grc"] == "Ancient Greek"
    assert LANGUAGE_NAMES["ar-classical"] == "Classical Arabic (pre-1200)"
    assert LANGUAGE_NAMES["non"] == "Old Norse"
    assert get_language_name("la") == "Latin"
    assert get_language_name("sa") == "Sanskrit"
    assert get_language_name("grc") == "Ancient Greek"
    assert get_language_name("ar-classical") == "Classical Arabic (pre-1200)"
    assert get_language_name("non") == "Old Norse"
    for language_code in ANCIENT_LANGUAGE_GROUP:
        assert LANGUAGE_HIERARCHY.index(language_code) < LANGUAGE_HIERARCHY.index("ms")
    assert "ar" not in LANGUAGE_FIELDS


def test_ancient_language_llm_field_mappings() -> None:
    """LLM translation field names map cleanly to ISO-style language codes."""
    assert LLM_FIELD_TO_LANG_CODE["latin_translation"] == "la"
    assert LLM_FIELD_TO_LANG_CODE["sanskrit_translation"] == "sa"
    assert LLM_FIELD_TO_LANG_CODE["ancient_greek_translation"] == "grc"
    assert LLM_FIELD_TO_LANG_CODE["classical_arabic_translation"] == "ar-classical"
    assert LLM_FIELD_TO_LANG_CODE["old_norse_translation"] == "non"
    assert LANG_CODE_TO_LLM_FIELD["la"] == "latin_translation"
    assert LANG_CODE_TO_LLM_FIELD["sa"] == "sanskrit_translation"
    assert LANG_CODE_TO_LLM_FIELD["grc"] == "ancient_greek_translation"
    assert LANG_CODE_TO_LLM_FIELD["ar-classical"] == "classical_arabic_translation"
    assert LANG_CODE_TO_LLM_FIELD["non"] == "old_norse_translation"
    assert "ar" not in LANG_CODE_TO_LLM_FIELD


def test_ancient_languages_are_generation_targets() -> None:
    """The LLM translation path has prompt config for each ancient language."""
    assert DEFAULT_TRANSLATION_LANGUAGES_BY_CODE["grc"]["field"] == "ancient_greek_translation"
    assert (
        DEFAULT_TRANSLATION_LANGUAGES_BY_CODE["ar-classical"]["field"]
        == "classical_arabic_translation"
    )
    assert DEFAULT_TRANSLATION_LANGUAGES_BY_CODE["non"]["field"] == "old_norse_translation"
    assert "ar" not in DEFAULT_TRANSLATION_LANGUAGES_BY_CODE
