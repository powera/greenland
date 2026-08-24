#!/usr/bin/env python3

"""Tests for langtools.dialect_overrides module."""

import unittest

from langtools.zh.converter import OPENCC_AVAILABLE

from langtools.dialect_overrides import (
    DIALECT_OVERRIDES,
    DialectOverride,
    get_all_dialect_codes,
    get_base_language,
    get_dialect_display_name,
    get_dialect_override,
    get_dialects_for_language,
    get_dialects_reading,
    get_llm_prompt_note,
    get_parent_language,
    get_sort_key_language,
    get_translation_language,
    get_translation_target_dialects,
    get_tts_locale,
    is_dialect,
    is_translation_target,
    normalize_language_code,
    transform_from_dialect,
    transform_to_dialect,
)


class TestDialectRegistry(unittest.TestCase):
    """Tests for the dialect registry and its consistency."""

    def test_all_expected_dialects_registered(self) -> None:
        expected = {"zh-tw", "es-419", "es-mx", "pt-br", "fr-ca", "en-gb"}
        self.assertEqual(set(DIALECT_OVERRIDES.keys()), expected)

    def test_all_dialect_codes_returns_all(self) -> None:
        codes = get_all_dialect_codes()
        self.assertEqual(set(codes), set(DIALECT_OVERRIDES.keys()))

    def test_parent_languages_are_not_dialects(self) -> None:
        parents = {o.parent_lang for o in DIALECT_OVERRIDES.values()}
        for parent in parents:
            self.assertNotIn(
                parent,
                DIALECT_OVERRIDES,
                f"{parent} is both a parent and a dialect code",
            )

    def test_covered_by_only_names_a_storage_language(self) -> None:
        """A presentation dialect must read text that is actually stored."""
        for code, override in DIALECT_OVERRIDES.items():
            if override.covered_by is None:
                continue
            self.assertFalse(
                override.translation_target,
                f"{code} stores its own translations, so covered_by is meaningless",
            )
            self.assertTrue(
                is_translation_target(override.covered_by),
                f"{code} is covered by {override.covered_by}, which stores nothing itself",
            )


class TestIsDialect(unittest.TestCase):
    def test_known_dialects(self) -> None:
        for code in ["zh-tw", "es-419", "es-mx", "pt-br", "fr-ca", "en-gb"]:
            self.assertTrue(is_dialect(code), f"{code} should be a dialect")

    def test_parent_languages(self) -> None:
        for code in ["zh", "es", "pt", "fr", "en", "de", "lt"]:
            self.assertFalse(is_dialect(code), f"{code} should NOT be a dialect")


class TestGetParentLanguage(unittest.TestCase):
    def test_dialect_returns_parent(self) -> None:
        self.assertEqual(get_parent_language("zh-tw"), "zh")
        self.assertEqual(get_parent_language("es-419"), "es")
        self.assertEqual(get_parent_language("es-mx"), "es")
        self.assertEqual(get_parent_language("pt-br"), "pt")
        self.assertEqual(get_parent_language("fr-ca"), "fr")
        self.assertEqual(get_parent_language("en-gb"), "en")

    def test_non_dialect_returns_self(self) -> None:
        self.assertEqual(get_parent_language("zh"), "zh")
        self.assertEqual(get_parent_language("fr"), "fr")
        self.assertEqual(get_parent_language("ko"), "ko")


class TestGetDialectsForLanguage(unittest.TestCase):
    def test_chinese(self) -> None:
        self.assertEqual(get_dialects_for_language("zh"), ["zh-tw"])

    def test_spanish(self) -> None:
        self.assertEqual(get_dialects_for_language("es"), ["es-419", "es-mx"])

    def test_no_dialects(self) -> None:
        self.assertEqual(get_dialects_for_language("ko"), [])
        self.assertEqual(get_dialects_for_language("lt"), [])


class TestGetDialectDisplayName(unittest.TestCase):
    def test_dialect_codes(self) -> None:
        self.assertEqual(get_dialect_display_name("zh-tw"), "Chinese (Taiwan Traditional)")
        self.assertEqual(get_dialect_display_name("es-419"), "Spanish (Latin American)")
        self.assertEqual(get_dialect_display_name("es-mx"), "Spanish (Mexican)")
        self.assertEqual(get_dialect_display_name("pt-br"), "Portuguese (Brazilian)")
        self.assertEqual(get_dialect_display_name("fr-ca"), "French (Canadian)")
        self.assertEqual(get_dialect_display_name("en-gb"), "English (British)")

    def test_parent_qualified_names(self) -> None:
        # Parents with dialects should get qualified names
        self.assertEqual(get_dialect_display_name("zh"), "Chinese (Mainland Simplified)")
        self.assertEqual(get_dialect_display_name("es"), "Spanish (Castilian)")
        self.assertEqual(get_dialect_display_name("pt"), "Portuguese (European)")


class TestGetDialectOverride(unittest.TestCase):
    def test_returns_override_for_dialect(self) -> None:
        override = get_dialect_override("zh-tw")
        self.assertIsNotNone(override)
        self.assertIsInstance(override, DialectOverride)
        assert override is not None  # for mypy narrowing
        self.assertEqual(override.parent_lang, "zh")

    def test_returns_none_for_non_dialect(self) -> None:
        self.assertIsNone(get_dialect_override("zh"))
        self.assertIsNone(get_dialect_override("xx"))


class TestTransformToDialect(unittest.TestCase):
    @unittest.skipUnless(OPENCC_AVAILABLE, "opencc not installed")
    def test_zh_tw_converts_simplified_to_traditional(self) -> None:
        # "鸡" (simplified) -> "雞" (traditional)
        result = transform_to_dialect("zh-tw", "鸡")
        self.assertEqual(result, "雞")

    def test_non_dialect_returns_unchanged(self) -> None:
        self.assertEqual(transform_to_dialect("es", "hola"), "hola")

    def test_dialect_without_transform_returns_unchanged(self) -> None:
        self.assertEqual(transform_to_dialect("es-mx", "hola"), "hola")

    def test_empty_text(self) -> None:
        self.assertEqual(transform_to_dialect("zh-tw", ""), "")


class TestTransformFromDialect(unittest.TestCase):
    @unittest.skipUnless(OPENCC_AVAILABLE, "opencc not installed")
    def test_zh_tw_converts_traditional_to_simplified(self) -> None:
        # "雞" (traditional) -> "鸡" (simplified)
        result = transform_from_dialect("zh-tw", "雞")
        self.assertEqual(result, "鸡")

    def test_non_dialect_returns_unchanged(self) -> None:
        self.assertEqual(transform_from_dialect("fr", "bonjour"), "bonjour")

    def test_dialect_without_reverse_returns_unchanged(self) -> None:
        self.assertEqual(transform_from_dialect("pt-br", "olá"), "olá")


class TestGetSortKeyLanguage(unittest.TestCase):
    def test_dialect_inherits_parent(self) -> None:
        self.assertEqual(get_sort_key_language("zh-tw"), "zh")
        self.assertEqual(get_sort_key_language("es-419"), "es")
        self.assertEqual(get_sort_key_language("es-mx"), "es")
        self.assertEqual(get_sort_key_language("pt-br"), "pt")
        self.assertEqual(get_sort_key_language("fr-ca"), "fr")

    def test_en_gb_has_no_sort_key(self) -> None:
        # en-gb has sort_key_lang=None, so falls back to parent "en"
        self.assertEqual(get_sort_key_language("en-gb"), "en")

    def test_non_dialect_returns_self(self) -> None:
        self.assertEqual(get_sort_key_language("zh"), "zh")
        self.assertEqual(get_sort_key_language("de"), "de")


class TestGetTtsLocale(unittest.TestCase):
    def test_dialect_locales(self) -> None:
        self.assertEqual(get_tts_locale("zh-tw"), "zh-TW")
        self.assertEqual(get_tts_locale("es-419"), "es-US")
        self.assertEqual(get_tts_locale("es-mx"), "es-MX")
        self.assertEqual(get_tts_locale("pt-br"), "pt-BR")
        self.assertEqual(get_tts_locale("fr-ca"), "fr-CA")
        self.assertEqual(get_tts_locale("en-gb"), "en-GB")

    def test_non_dialect_returns_none(self) -> None:
        self.assertIsNone(get_tts_locale("zh"))
        self.assertIsNone(get_tts_locale("ko"))


class TestGetLlmPromptNote(unittest.TestCase):
    def test_dialects_have_notes(self) -> None:
        for code in DIALECT_OVERRIDES:
            note = get_llm_prompt_note(code)
            self.assertIsNotNone(note, f"{code} should have a prompt note")
            self.assertIsInstance(note, str)
            assert note is not None  # for mypy narrowing
            self.assertTrue(len(note) > 0)

    def test_non_dialect_returns_none(self) -> None:
        self.assertIsNone(get_llm_prompt_note("zh"))
        self.assertIsNone(get_llm_prompt_note("de"))


class TestDialectOverrideDataclass(unittest.TestCase):
    def test_frozen(self) -> None:
        override = DIALECT_OVERRIDES["zh-tw"]
        with self.assertRaises(AttributeError):
            override.parent_lang = "ja"  # type: ignore[misc]

    def test_repr_excludes_callables(self) -> None:
        override = DIALECT_OVERRIDES["zh-tw"]
        repr_str = repr(override)
        # text_transform and reverse_transform are repr=False
        self.assertNotIn("text_transform", repr_str)
        self.assertNotIn("reverse_transform", repr_str)
        # But other fields should be present
        self.assertIn("parent_lang", repr_str)
        self.assertIn("zh", repr_str)


class TestNormalizeLanguageCode(unittest.TestCase):
    def test_case_and_separator_folding(self) -> None:
        self.assertEqual(normalize_language_code("pt-BR"), "pt-br")
        self.assertEqual(normalize_language_code("zh_TW"), "zh-tw")
        self.assertEqual(normalize_language_code("  ES  "), "es")

    def test_canonical_codes_are_unchanged(self) -> None:
        for code in DIALECT_OVERRIDES:
            self.assertEqual(normalize_language_code(code), code)

    def test_region_aliases_fold_to_the_registered_variety(self) -> None:
        self.assertEqual(normalize_language_code("es-US"), "es-419")
        self.assertEqual(normalize_language_code("es-latam"), "es-419")
        self.assertEqual(normalize_language_code("zh-Hant"), "zh-tw")
        self.assertEqual(normalize_language_code("pt-PT"), "pt")

    def test_unknown_codes_pass_through(self) -> None:
        """This is a normalizer, not a validator."""
        self.assertEqual(normalize_language_code("xx-YY"), "xx-yy")
        self.assertEqual(normalize_language_code(""), "")

    def test_lookups_accept_unnormalized_input(self) -> None:
        self.assertTrue(is_dialect("pt-BR"))
        self.assertEqual(get_parent_language("zh_TW"), "zh")
        self.assertEqual(get_tts_locale("PT-br"), "pt-BR")
        self.assertEqual(get_dialect_display_name("es-US"), "Spanish (Latin American)")


class TestTranslationTargets(unittest.TestCase):
    def test_storage_dialects(self) -> None:
        self.assertEqual(get_translation_target_dialects(), ["zh-tw", "es-419", "pt-br"])

    def test_is_translation_target(self) -> None:
        for code in ["zh-tw", "es-419", "pt-br"]:
            self.assertTrue(is_translation_target(code), f"{code} stores its own translations")
        for code in ["es-mx", "fr-ca", "en-gb"]:
            self.assertFalse(is_translation_target(code), f"{code} stores no translations")

    def test_plain_languages_are_translation_targets(self) -> None:
        for code in ["es", "pt", "zh", "lt"]:
            self.assertTrue(is_translation_target(code))

    def test_storage_dialect_reads_its_own_text(self) -> None:
        for code in get_translation_target_dialects():
            self.assertEqual(get_translation_language(code), code)

    def test_mexican_spanish_reads_latin_american_spanish(self) -> None:
        """The reason es-mx is not a separate generation target."""
        self.assertEqual(get_translation_language("es-mx"), "es-419")

    def test_presentation_dialect_without_coverage_reads_its_parent(self) -> None:
        self.assertEqual(get_translation_language("fr-ca"), "fr")
        self.assertEqual(get_translation_language("en-gb"), "en")

    def test_plain_language_reads_itself(self) -> None:
        self.assertEqual(get_translation_language("de"), "de")


class TestGetDialectsReading(unittest.TestCase):
    """The inverse of get_translation_language, used to fan changes outward."""

    def test_latin_american_spanish_is_read_by_mexican_spanish(self) -> None:
        self.assertEqual(get_dialects_reading("es-419"), ["es-mx"])

    def test_a_parent_read_directly_by_a_presentation_dialect(self) -> None:
        self.assertEqual(get_dialects_reading("fr"), ["fr-ca"])
        self.assertEqual(get_dialects_reading("en"), ["en-gb"])

    def test_castilian_spanish_is_read_by_nothing(self) -> None:
        """es-mx reads es-419, not es, so a Castilian edit does not reach it."""
        self.assertEqual(get_dialects_reading("es"), [])

    def test_a_language_with_no_dialects(self) -> None:
        self.assertEqual(get_dialects_reading("lt"), [])

    def test_accepts_unnormalized_codes(self) -> None:
        self.assertEqual(get_dialects_reading("ES-419"), ["es-mx"])

    def test_round_trips_with_get_translation_language(self) -> None:
        for source in {get_translation_language(code) for code in DIALECT_OVERRIDES}:
            for dialect in get_dialects_reading(source):
                self.assertEqual(get_translation_language(dialect), source)


class TestGetBaseLanguage(unittest.TestCase):
    """``get_base_language`` is what picks a langtools module for a code."""

    def test_dialects_resolve_to_their_module_language(self) -> None:
        self.assertEqual(get_base_language("es-419"), "es")
        self.assertEqual(get_base_language("es-mx"), "es")
        self.assertEqual(get_base_language("pt-BR"), "pt")
        self.assertEqual(get_base_language("zh-tw"), "zh")

    def test_plain_language_resolves_to_itself(self) -> None:
        self.assertEqual(get_base_language("lt"), "lt")


if __name__ == "__main__":
    unittest.main()
