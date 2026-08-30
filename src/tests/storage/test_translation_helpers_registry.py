"""Structural invariants and transforms in storage.translation_helpers.

The language registry is data: which languages exist, what tier they sit in and
how their names are spelled all change as languages are added. None of that is
asserted here. What is asserted is that the several tables describing a language
agree with each other, so a language added to one table but not another fails
loudly instead of silently dropping out of exports or LLM prompts.
"""

from __future__ import annotations

from typing import Dict, List

import pytest

from storage.translation_helpers import (
    ANCIENT_LANGUAGE_GROUP,
    EXTRA_RELEASE_LANGUAGE_GROUPS,
    LANG_CODE_TO_LLM_FIELD,
    LANGUAGE_FIELDS,
    LANGUAGE_HIERARCHY,
    LANGUAGE_NAME_TO_CODE,
    LANGUAGE_NAMES,
    LLM_FIELD_TO_LANG_CODE,
    MAX_LLM_LANGUAGES_PER_OPERATION,
    RELEASE_LANGUAGES,
    SECONDARY_RELEASE_LANGUAGES,
    TIER_1_LANGUAGES,
    TIER_2_LANGUAGES,
    TIER_3_LANGUAGES,
    TIER_4_LANGUAGES,
    TRANSLATION_STATUS_VALUES,
    convert_llm_response_to_lang_codes,
    convert_llm_response_to_translation_metadata,
    get_language_code,
    get_language_name,
    get_supported_languages,
    lang_code_to_llm_field,
    llm_field_to_lang_code,
    normalize_llm_language_codes,
    split_llm_language_batches,
    translation_status_is_informative,
)

ALL_TIERS = [TIER_1_LANGUAGES, TIER_2_LANGUAGES, TIER_3_LANGUAGES, TIER_4_LANGUAGES]


def _llm_field(lang_code: str) -> str:
    """Return the LLM field for a registered code, failing the test if there is none."""
    field_name = lang_code_to_llm_field(lang_code)
    assert field_name is not None, f"no LLM field registered for {lang_code}"
    return field_name


# --- registry consistency -------------------------------------------------


def test_llm_field_mapping_is_a_bijection() -> None:
    """Field <-> code mappings must invert exactly, in both directions.

    LANG_CODE_TO_LLM_FIELD is built by inverting LLM_FIELD_TO_LANG_CODE, so two
    fields mapping to one code would silently drop a language.
    """
    codes = list(LLM_FIELD_TO_LANG_CODE.values())
    assert len(codes) == len(set(codes)), "two LLM fields map to the same language code"

    for field_name, lang_code in LLM_FIELD_TO_LANG_CODE.items():
        assert LANG_CODE_TO_LLM_FIELD[lang_code] == field_name


def test_llm_field_helpers_agree_with_the_tables() -> None:
    for field_name, lang_code in LLM_FIELD_TO_LANG_CODE.items():
        assert llm_field_to_lang_code(field_name) == lang_code
        assert lang_code_to_llm_field(lang_code) == field_name

    assert llm_field_to_lang_code("not_a_field") is None
    assert lang_code_to_llm_field("not-a-code") is None


def test_every_tier_language_is_described_in_language_fields() -> None:
    """A language in a tier but missing from LANGUAGE_FIELDS has no display name."""
    for tier in ALL_TIERS:
        for lang_code in tier:
            assert lang_code in LANGUAGE_FIELDS, f"{lang_code} is tiered but undescribed"


def test_tiers_are_disjoint() -> None:
    """A language in two tiers would be generated or exported twice."""
    seen: Dict[str, int] = {}
    for tier_index, tier in enumerate(ALL_TIERS):
        for lang_code in tier:
            assert (
                lang_code not in seen
            ), f"{lang_code} appears in tier {seen[lang_code] + 1} and tier {tier_index + 1}"
            seen[lang_code] = tier_index


def test_no_tier_repeats_a_language() -> None:
    for tier in ALL_TIERS:
        assert len(tier) == len(set(tier))


def test_language_hierarchy_only_orders_described_languages() -> None:
    """The hierarchy drives display order, so every entry needs a description.

    The converse does not hold: a described language may be intentionally left
    out of the hierarchy (zh-tw is described and LLM-addressable but is excluded
    from ordered display), so this checks containment, not equality.
    """
    assert set(LANGUAGE_HIERARCHY) <= set(LANGUAGE_FIELDS)
    assert len(LANGUAGE_HIERARCHY) == len(set(LANGUAGE_HIERARCHY))


def test_tiered_languages_are_all_ordered_by_the_hierarchy() -> None:
    """Anything in a tier is generated and displayed, so it must be ordered."""
    for tier in ALL_TIERS:
        for lang_code in tier:
            assert lang_code in LANGUAGE_HIERARCHY


def test_language_names_round_trip_through_their_codes() -> None:
    for lang_code in LANGUAGE_FIELDS:
        name = get_language_name(lang_code)
        assert name
        assert get_language_code(name) == lang_code
        assert get_language_code(name.lower()) == lang_code


def test_language_name_lookup_is_unambiguous() -> None:
    """Two languages sharing a display name would collide in the name->code map."""
    assert len(LANGUAGE_NAME_TO_CODE) == len(LANGUAGE_NAMES)


def test_language_fields_entries_are_self_consistent() -> None:
    """Names agree with LANGUAGE_NAMES, and each entry names a storage field.

    The storage field is the language code for every language, English
    included: they are all held as LemmaTranslation rows keyed by that code.
    English was once the exception, stored on Lemma.lemma_text, which is why
    the entry still carries the field at all.
    """
    for lang_code, (storage_field, name) in LANGUAGE_FIELDS.items():
        assert storage_field == lang_code
        assert LANGUAGE_NAMES[lang_code] == name


def test_release_languages_are_described_and_internally_consistent() -> None:
    for lang_code in RELEASE_LANGUAGES:
        assert lang_code in LANGUAGE_FIELDS

    assert len(RELEASE_LANGUAGES) == len(set(RELEASE_LANGUAGES))
    assert set(SECONDARY_RELEASE_LANGUAGES) <= set(LANGUAGE_FIELDS)
    assert not set(SECONDARY_RELEASE_LANGUAGES) & set(RELEASE_LANGUAGES)


def test_extra_release_groups_reference_described_languages() -> None:
    for group_name, group in EXTRA_RELEASE_LANGUAGE_GROUPS.items():
        assert group, f"release group {group_name} is empty"
        for lang_code in group:
            assert lang_code in LANGUAGE_FIELDS, f"{group_name} names undescribed {lang_code}"


def test_get_supported_languages_matches_the_registry() -> None:
    assert get_supported_languages() == LANGUAGE_NAMES


def test_unknown_language_lookups() -> None:
    """Name lookup rejects an unknown code loudly; code lookup returns None."""
    assert get_language_code("Not A Language") is None

    with pytest.raises(ValueError):
        get_language_name("not-a-code")


# --- LLM response conversion ---------------------------------------------


def test_convert_llm_response_accepts_string_and_object_values() -> None:
    """The LLM emits bare strings (legacy) and {"translation": ...} objects."""
    sample_field = next(iter(LLM_FIELD_TO_LANG_CODE))
    sample_code = LLM_FIELD_TO_LANG_CODE[sample_field]

    assert convert_llm_response_to_lang_codes({sample_field: "word"}) == {sample_code: "word"}
    assert convert_llm_response_to_lang_codes({sample_field: {"translation": "word"}}) == {
        sample_code: "word"
    }


def test_convert_llm_response_drops_unknown_fields_and_bad_shapes() -> None:
    sample_field = next(iter(LLM_FIELD_TO_LANG_CODE))
    sample_code = LLM_FIELD_TO_LANG_CODE[sample_field]

    converted = convert_llm_response_to_lang_codes(
        {
            sample_field: "word",
            "notes": "some commentary",
            "unknown_translation": "ignored",
        }
    )
    assert converted == {sample_code: "word"}

    # A value of the wrong type degrades to empty text rather than raising.
    assert convert_llm_response_to_lang_codes({sample_field: 17}) == {sample_code: ""}
    assert convert_llm_response_to_lang_codes({sample_field: {"other": "x"}}) == {sample_code: ""}
    assert convert_llm_response_to_lang_codes({}) == {}


def test_translation_metadata_normalizes_unrecognized_status() -> None:
    sample_field = next(iter(LLM_FIELD_TO_LANG_CODE))
    sample_code = LLM_FIELD_TO_LANG_CODE[sample_field]

    metadata = convert_llm_response_to_translation_metadata(
        {sample_field: {"translation": "w", "translation_status": "invented_status"}}
    )

    assert metadata[sample_code]["translation_status"] == "uncertain"


def test_translation_metadata_skips_entries_without_metadata() -> None:
    sample_field = next(iter(LLM_FIELD_TO_LANG_CODE))

    assert convert_llm_response_to_translation_metadata({sample_field: "plain string"}) == {}
    assert convert_llm_response_to_translation_metadata({sample_field: {"translation": "w"}}) == {}
    assert convert_llm_response_to_translation_metadata({"unknown_translation": {"x": "y"}}) == {}


def test_translation_metadata_drops_default_status_for_modern_languages() -> None:
    """The models answer "conventional" for nearly every living-language word."""
    metadata = convert_llm_response_to_translation_metadata(
        {
            _llm_field("es"): {
                "translation": "Europa",
                "translation_status": "conventional",
                "translation_status_note": "",
            },
            _llm_field("la"): {
                "translation": "Europa",
                "translation_status": "conventional",
            },
            _llm_field("lt"): {
                "translation": "kompiuteris",
                "translation_status": "modern_loan",
            },
        }
    )

    assert "es" not in metadata
    assert metadata["la"]["translation_status"] == "conventional"
    assert metadata["lt"]["translation_status"] == "modern_loan"


# --- default-status suppression -------------------------------------------


def test_unset_status_is_never_informative() -> None:
    assert not translation_status_is_informative("la", None)
    assert not translation_status_is_informative("es", "")


def test_conventional_is_informative_only_for_ancient_languages() -> None:
    """It is term_age's evidence there, and the assumed default everywhere else."""
    for language_code in ANCIENT_LANGUAGE_GROUP:
        assert translation_status_is_informative(language_code, "conventional")
    for language_code in ("es", "es-419", "zh", "zh-tw", "fr", "lt", "ja"):
        assert not translation_status_is_informative(language_code, "conventional")


def test_every_non_default_status_is_informative_in_any_language() -> None:
    """A loan or a coinage marks a word that genuinely is unusual."""
    for status in TRANSLATION_STATUS_VALUES - {"conventional"}:
        assert translation_status_is_informative("es", status), status
        assert translation_status_is_informative("la", status), status


def test_a_note_keeps_a_conventional_status() -> None:
    """Somebody wrote the note on purpose, so the status it explains stays."""
    assert translation_status_is_informative("es", "conventional", "the established exonym")


def test_dialect_spelling_is_normalized_before_the_ancient_check() -> None:
    assert not translation_status_is_informative("pt-BR", "conventional")


# --- LLM batching ---------------------------------------------------------


def test_normalize_deduplicates_and_preserves_order() -> None:
    assert normalize_llm_language_codes(["fr", "de", "fr", "es"], operation_name="test") == [
        "fr",
        "de",
        "es",
    ]


def test_normalize_handles_empty_input() -> None:
    assert normalize_llm_language_codes(None, operation_name="test") == []
    assert normalize_llm_language_codes([], operation_name="test") == []


def test_normalize_expands_all_before_explicit_languages() -> None:
    result = normalize_llm_language_codes(
        ["zz", "all"], operation_name="test", all_expansion=["fr", "de"]
    )

    assert result == ["fr", "de", "zz"]


def test_normalize_rejects_all_when_unsupported() -> None:
    with pytest.raises(ValueError):
        normalize_llm_language_codes(["all"], operation_name="test")


def test_normalize_caps_the_language_count() -> None:
    requested = [f"l{index}" for index in range(MAX_LLM_LANGUAGES_PER_OPERATION + 5)]

    result = normalize_llm_language_codes(requested, operation_name="test")

    assert result == requested[:MAX_LLM_LANGUAGES_PER_OPERATION]


def test_batches_preserve_order_and_respect_the_cap() -> None:
    languages = [f"l{index}" for index in range(MAX_LLM_LANGUAGES_PER_OPERATION * 2 + 3)]

    batches: List[List[str]] = split_llm_language_batches(languages)

    assert [lang for batch in batches for lang in batch] == languages
    assert all(len(batch) <= MAX_LLM_LANGUAGES_PER_OPERATION for batch in batches)
    assert split_llm_language_batches([]) == []
