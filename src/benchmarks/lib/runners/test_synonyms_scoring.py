#!/usr/bin/python3

"""Unit tests for synonyms scoring."""

import unittest

from benchmarks.synonyms_scoring import score_synonyms_response


class TestSynonymsScoring(unittest.TestCase):
    def test_partial_score_with_mandatory_and_optional(self):
        question_data = {
            "correct_answer": {
                "mandatory_synonyms": ["cap"],
                "optional_synonyms": ["headgear", "headwear"],
            }
        }
        response = {"synonyms": ["cap", "lid", "headgear"]}

        score = score_synonyms_response(question_data, response)
        self.assertAlmostEqual(score, 88.33, places=2)

    def test_missing_mandatory_penalized(self):
        question_data = {
            "correct_answer": {
                "mandatory_synonyms": ["cap"],
                "optional_synonyms": ["headgear", "headwear"],
            }
        }
        response = {"synonyms": ["headgear", "headwear"]}

        score = score_synonyms_response(question_data, response)
        self.assertLess(score, 30.0)

    def test_no_synonyms_expected_empty_response(self):
        question_data = {
            "correct_answer": {
                "mandatory_synonyms": [],
                "optional_synonyms": [],
            }
        }

        self.assertEqual(score_synonyms_response(question_data, {"synonyms": []}), 100.0)
        self.assertEqual(score_synonyms_response(question_data, {"synonyms": ["foo"]}), 80.0)


if __name__ == "__main__":
    unittest.main()
