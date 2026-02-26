#!/usr/bin/python3

"""Unit tests for synonyms runner exact-match scoring (0017)."""

import unittest

from benchmarks.lib.runners.test_synonyms_runner_partial_credit import (
    RUNNER_MODULE,
    SynonymsRunner,
)


class TestSynonymsRunnerScoring(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = SynonymsRunner.__new__(SynonymsRunner)

    def test_correct_synonym_passes(self) -> None:
        question_data = {"correct_answer": {"synonym": "cap"}}

        class FakeResponse:
            structured_data = {"synonym": "cap"}

        debug = self.runner.build_debug_info(question_data, FakeResponse(), True)
        self.assertEqual(debug["response"], "cap")
        self.assertTrue(debug["is_correct"])

    def test_wrong_synonym_fails(self) -> None:
        question_data = {"correct_answer": {"synonym": "cap"}}

        class FakeResponse:
            structured_data = {"synonym": "scarf"}

        debug = self.runner.build_debug_info(question_data, FakeResponse(), False)
        self.assertEqual(debug["response"], "scarf")
        self.assertFalse(debug["is_correct"])


if __name__ == "__main__":
    unittest.main()
