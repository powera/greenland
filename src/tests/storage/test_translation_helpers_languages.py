"""Tests for shared language registry metadata."""

from langtools.dialect_overrides import (
    get_all_dialect_codes,
    get_parent_language,
    get_translation_language,
    get_translation_target_dialects,
)
from storage.translation_helpers import (
    ANCIENT_LANGUAGE_GROUP,
    EXTRA_RELEASE_LANGUAGE_GROUPS,
    LANG_CODE_TO_LLM_FIELD,
    LANGUAGE_FIELDS,
    LANGUAGE_HIERARCHY,
    LANGUAGE_NAMES,
    LLM_FIELD_TO_LANG_CODE,
    RELEASE_LANGUAGES,
    SECONDARY_RELEASE_LANGUAGES,
    TIER_4_LANGUAGES,
    get_default_generation_languages,
    get_language_name,
    has_sort_key,
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
    assert LANGUAGE_FIELDS["la"] == ("la", "Latin")
    assert LANGUAGE_FIELDS["sa"] == ("sa", "Sanskrit")
    assert LANGUAGE_FIELDS["grc"] == ("grc", "Ancient Greek")
    assert LANGUAGE_FIELDS["ar-classical"] == (
        "ar-classical",
        "Classical Arabic (pre-1200)",
    )
    assert LANGUAGE_FIELDS["non"] == ("non", "Old Norse")
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


def test_storage_dialects_are_registered_everywhere_a_language_must_be() -> None:
    """A dialect that stores translations needs the full language registration.

    Missing any one of these makes it look supported while a generation run
    silently skips it: LANGUAGE_FIELDS routes storage, LLM_FIELD_TO_LANG_CODE
    parses the model's reply, DEFAULT_TRANSLATION_LANGUAGES_BY_CODE supplies the
    prompt, and LANGUAGE_HIERARCHY orders it in the UI.
    """
    for language_code in get_translation_target_dialects():
        assert language_code in LANGUAGE_FIELDS, language_code
        assert language_code in LANG_CODE_TO_LLM_FIELD, language_code
        assert language_code in DEFAULT_TRANSLATION_LANGUAGES_BY_CODE, language_code
        assert language_code in LANGUAGE_HIERARCHY, language_code
        assert language_code in get_default_generation_languages(), language_code
        assert language_code in RELEASE_LANGUAGES, language_code


def test_presentation_dialects_are_not_storage_languages() -> None:
    """es-mx and friends must not acquire a column behind our back.

    Each reads another variety's text, so a LANGUAGE_FIELDS entry would create a
    second place to store the same words.
    """
    presentation_dialects = set(get_all_dialect_codes()) - set(get_translation_target_dialects())
    assert presentation_dialects == {"es-mx", "fr-ca", "en-gb"}
    for language_code in presentation_dialects:
        assert language_code not in LANGUAGE_FIELDS, language_code
        assert language_code not in DEFAULT_TRANSLATION_LANGUAGES_BY_CODE, language_code
        assert get_translation_language(language_code) in LANGUAGE_FIELDS, language_code


def test_storage_dialect_metadata() -> None:
    assert LANGUAGE_FIELDS["es-419"] == ("es-419", "Spanish (Latin America)")
    assert LANGUAGE_FIELDS["pt-br"] == ("pt-br", "Portuguese (Brazil)")
    assert LANGUAGE_NAMES["es-419"] == "Spanish (Latin America)"
    assert get_language_name("pt-br") == "Portuguese (Brazil)"
    assert LLM_FIELD_TO_LANG_CODE["spanish_latam_translation"] == "es-419"
    assert LLM_FIELD_TO_LANG_CODE["portuguese_brazil_translation"] == "pt-br"
    assert LANG_CODE_TO_LLM_FIELD["es-419"] == "spanish_latam_translation"
    assert LANG_CODE_TO_LLM_FIELD["pt-br"] == "portuguese_brazil_translation"


def test_storage_dialects_sort_next_to_their_parent() -> None:
    """A dialect should render beside the variety it extends, not at the end."""
    for dialect, parent in [("zh-tw", "zh"), ("es-419", "es"), ("pt-br", "pt")]:
        assert LANGUAGE_HIERARCHY.index(dialect) == LANGUAGE_HIERARCHY.index(parent) + 1


def test_dialects_inherit_their_parents_sort_key_support() -> None:
    """zh-tw sorts by pinyin and es-419 by the Spanish remapping, like the parent."""
    for dialect in get_translation_target_dialects():
        assert has_sort_key(dialect) is has_sort_key(get_parent_language(dialect))
    assert has_sort_key("zh-tw") is True
    assert has_sort_key("es-419") is True
    assert has_sort_key("en-gb") is False
