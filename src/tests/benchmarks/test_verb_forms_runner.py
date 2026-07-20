"""Tests for verb forms benchmark scoring."""

import unittest

import sys
import types

if "pydantic" not in sys.modules:
    sys.modules["pydantic"] = types.SimpleNamespace(BaseModel=object)

# Must precede any runner import; see test_sentence_decomposition_scoring.py.
import benchmarks.lib.utils  # noqa: F401  (import order matters)

from benchmarks.lib.runners.verb_forms_runner import CORRECTNESS_THRESHOLD, VerbFormsRunner


class TestVerbFormsRunnerScoring(unittest.TestCase):
    """Verify weighted exact-match scoring behavior."""

    def setUp(self) -> None:
        # Avoid DB-bound BenchmarkRunner.__init__ in unit tests.
        self.runner = VerbFormsRunner.__new__(VerbFormsRunner)

    def _question_data(self) -> dict:
        return {
            "question_text": "test",
            "correct_answer": {
                "language_code": "en",
                "lemma": "work",
                "required_extra_forms": ["present_participle", "past_participle"],
                "forms": {
                    "present": {
                        "1s": "work",
                        "2s": "work",
                        "3s": "works",
                        "1p": "work",
                        "2p": "work",
                        "3p": "work",
                    },
                    "past": {
                        "1s": "worked",
                        "2s": "worked",
                        "3s": "worked",
                        "1p": "worked",
                        "2p": "worked",
                        "3p": "worked",
                    },
                    "future": {
                        "1s": "will work",
                        "2s": "will work",
                        "3s": "will work",
                        "1p": "will work",
                        "2p": "will work",
                        "3p": "will work",
                    },
                },
                "extra_forms": {
                    "present_participle": "working",
                    "past_participle": "worked",
                },
            },
        }

    def _perfect_response(self) -> dict:
        return {
            "language_code": "en",
            "lemma": "work",
            "forms": {
                "present": {
                    "1s": "work",
                    "2s": "work",
                    "3s": "works",
                    "1p": "work",
                    "2p": "work",
                    "3p": "work",
                },
                "past": {
                    "1s": "worked",
                    "2s": "worked",
                    "3s": "worked",
                    "1p": "worked",
                    "2p": "worked",
                    "3p": "worked",
                },
                "future": {
                    "1s": "will work",
                    "2s": "will work",
                    "3s": "will work",
                    "1p": "will work",
                    "2p": "will work",
                    "3p": "will work",
                },
            },
            "extra_forms": {
                "present_participle": "working",
                "past_participle": "worked",
            },
        }

    def test_score_is_around_seventy_for_eighteen_of_twenty(self) -> None:
        question = self._question_data()
        response = self._perfect_response()

        # Introduce two mismatches out of 20 total scored slots.
        response["forms"]["present"]["3s"] = "work"
        response["extra_forms"]["present_participle"] = "workin"

        score = self.runner.score_response(question, response)

        self.assertEqual(score, 72)
        self.assertGreaterEqual(score, CORRECTNESS_THRESHOLD)

    def test_perfect_match_gets_exact_bonus(self) -> None:
        score = self.runner.score_response(self._question_data(), self._perfect_response())
        self.assertEqual(score, 100)


if __name__ == "__main__":
    unittest.main()
