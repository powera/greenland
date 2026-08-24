#!/usr/bin/python3

"""Tests for translation helper language normalization."""

import unittest

from storage.translation_helpers import (
    MAX_LLM_LANGUAGES_PER_OPERATION,
    convert_llm_response_to_lang_codes,
    convert_llm_response_to_translation_metadata,
    get_tier_1_and_tier_2_languages,
    normalize_llm_language_codes,
    split_llm_language_batches,
)


class TestTranslationHelpers(unittest.TestCase):

    def test_all_expands_to_tier1_tier2(self):
        self.assertEqual(
            normalize_llm_language_codes(
                ["all"],
                operation_name="test operation",
                all_expansion=get_tier_1_and_tier_2_languages(),
            ),
            get_tier_1_and_tier_2_languages(),
        )

    def test_dedupes_and_limits(self):
        oversized = [f"l{i}" for i in range(20)] + ["l0", "l1"]
        normalized = normalize_llm_language_codes(
            oversized,
            operation_name="test operation",
        )
        self.assertEqual(len(normalized), MAX_LLM_LANGUAGES_PER_OPERATION)
        self.assertEqual(normalized[0], "l0")
        self.assertEqual(normalized[-1], "l9")

    def test_no_cap_when_the_caller_batches(self):
        """``max_languages=None`` is how a batching caller keeps its whole set."""
        oversized = [f"l{i}" for i in range(20)]
        normalized = normalize_llm_language_codes(
            oversized,
            operation_name="test operation",
            max_languages=None,
        )
        self.assertEqual(normalized, oversized)

    def test_canonicalizes_dialect_spellings(self):
        self.assertEqual(
            normalize_llm_language_codes(
                ["pt-BR", "zh_TW", "ES", "es-419"],
                operation_name="test operation",
            ),
            ["pt-br", "zh-tw", "es", "es-419"],
        )

    def test_dedupes_after_canonicalizing(self):
        """es-US and es-419 are the same variety, so only one request is made."""
        self.assertEqual(
            normalize_llm_language_codes(
                ["es-419", "es-US", "ES-419"],
                operation_name="test operation",
            ),
            ["es-419"],
        )

    def test_split_llm_language_batches_chunks_in_order(self):
        batches = split_llm_language_batches([f"l{i}" for i in range(11)])
        self.assertEqual([len(batch) for batch in batches], [MAX_LLM_LANGUAGES_PER_OPERATION, 1])
        self.assertEqual(batches[0][0], "l0")
        self.assertEqual(batches[-1], ["l10"])

    def test_converts_structured_translation_response_metadata(self):
        response = {
            "latin_translation": {
                "translation": "lycopersicum",
                "translation_status": "late_construction",
                "translation_status_note": "Neo-Latin botanical learner cue.",
            },
            "sanskrit_translation": {
                "translation": "रक्तफलम्",
                "translation_status": "descriptive",
                "translation_status_note": "Descriptive modern coinage.",
            },
        }

        self.assertEqual(
            convert_llm_response_to_lang_codes(response),
            {"la": "lycopersicum", "sa": "रक्तफलम्"},
        )
        self.assertEqual(
            convert_llm_response_to_translation_metadata(response),
            {
                "la": {
                    "translation_status": "late_construction",
                    "translation_status_note": "Neo-Latin botanical learner cue.",
                },
                "sa": {
                    "translation_status": "descriptive",
                    "translation_status_note": "Descriptive modern coinage.",
                },
            },
        )


if __name__ == "__main__":
    unittest.main()
