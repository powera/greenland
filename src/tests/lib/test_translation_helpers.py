#!/usr/bin/python3

"""Tests for translation helper language normalization."""

import unittest

from storage.translation_helpers import (
    MAX_LLM_LANGUAGES_PER_OPERATION,
    convert_llm_response_to_lang_codes,
    convert_llm_response_to_translation_metadata,
    get_tier_1_and_tier_2_languages,
    normalize_llm_language_codes,
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
        self.assertEqual(normalized[-1], "l15")

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
