#!/usr/bin/python3

"""Unit tests for 0061 word-to-IPA Levenshtein-based scoring."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_word_to_ipa_runner_module():
    base_runner_module = types.ModuleType("benchmarks.lib.utils.base_runner")

    class BenchmarkRunner:
        def __init__(self, model, metadata):
            self.model = model
            self.metadata = metadata

    setattr(base_runner_module, "BenchmarkRunner", BenchmarkRunner)
    sys.modules.setdefault("benchmarks.lib.utils.base_runner", base_runner_module)

    data_models_module = types.ModuleType("benchmarks.lib.utils.data_models")

    class BenchmarkMetadata:
        def __init__(self, code, name, description):
            self.code = code
            self.name = name
            self.description = description

    class BenchmarkResult:
        pass

    setattr(data_models_module, "BenchmarkMetadata", BenchmarkMetadata)
    setattr(data_models_module, "BenchmarkResult", BenchmarkResult)
    sys.modules.setdefault("benchmarks.lib.utils.data_models", data_models_module)

    factory_module = types.ModuleType("benchmarks.lib.utils.factory")

    def runner(_code):
        def decorator(cls):
            return cls

        return decorator

    setattr(factory_module, "runner", runner)
    sys.modules.setdefault("benchmarks.lib.utils.factory", factory_module)

    words_module = types.ModuleType("words")

    def build_ipa_pronunciation_prompt(_language_code, _word, definition="", sentence=""):
        return "context\n\nprompt"

    setattr(words_module, "build_ipa_pronunciation_prompt", build_ipa_pronunciation_prompt)
    sys.modules.setdefault("words", words_module)

    module_path = Path(__file__).with_name("word_to_ipa_runner.py")
    spec = importlib.util.spec_from_file_location("word_to_ipa_runner_under_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER_MODULE = _load_word_to_ipa_runner_module()
WordToIPARunner = RUNNER_MODULE.WordToIPARunner


class TestWordToIPAScoring(unittest.TestCase):
    def setUp(self):
        self.runner = WordToIPARunner.__new__(WordToIPARunner)

    def test_exact_match_scores_100(self):
        question_data = {"correct_answer": "kæt"}

        score = self.runner.score_response(question_data, {"ipa": "kæt"})

        self.assertEqual(score, 100)

    def test_levenshtein_80_percent_scores_48(self):
        question_data = {"correct_answer": "abcde"}

        score = self.runner.score_response(question_data, {"ipa": "abcdx"})

        self.assertEqual(score, 48)

    def test_levenshtein_50_percent_scores_30(self):
        question_data = {"correct_answer": "abcd"}

        score = self.runner.score_response(question_data, {"ipa": "abxy"})

        self.assertEqual(score, 30)

    def test_water_british_vs_american_gets_partial_credit(self):
        # American GA: \u02c8w\u0254t\u025a  British: /\u02c8w\u0254\u02d0t\u0259r/
        # These are dialectal variants and should score above 0.
        question_data = {"correct_answer": "\u02c8w\u0254t\u025a"}

        score = self.runner.score_response(question_data, {"ipa": "/\u02c8w\u0254\u02d0t\u0259r/"})

        self.assertGreater(score, 0)
        self.assertLess(score, 100)

    def test_normalize_strips_slashes(self):
        normalized = self.runner._normalize_ipa("/\u02c8w\u0254\u02d0t\u0259r/")

        self.assertNotIn("/", normalized)

    def test_phonetically_similar_scores_higher_than_unrelated(self):
        # r vs \u0279 (r vs IPA r) should score higher than r vs z
        question_data = {"correct_answer": "r"}
        similar_score = self.runner.score_response(question_data, {"ipa": "\u0279"})
        unrelated_score = self.runner.score_response(question_data, {"ipa": "z"})

        self.assertGreaterEqual(similar_score, unrelated_score)


if __name__ == "__main__":
    unittest.main()
