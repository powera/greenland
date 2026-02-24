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

    base_runner_module.BenchmarkRunner = BenchmarkRunner
    sys.modules.setdefault("benchmarks.lib.utils.base_runner", base_runner_module)

    data_models_module = types.ModuleType("benchmarks.lib.utils.data_models")

    class BenchmarkMetadata:
        def __init__(self, code, name, description):
            self.code = code
            self.name = name
            self.description = description

    class BenchmarkResult:
        pass

    data_models_module.BenchmarkMetadata = BenchmarkMetadata
    data_models_module.BenchmarkResult = BenchmarkResult
    sys.modules.setdefault("benchmarks.lib.utils.data_models", data_models_module)

    factory_module = types.ModuleType("benchmarks.lib.utils.factory")

    def runner(_code):
        def decorator(cls):
            return cls

        return decorator

    factory_module.runner = runner
    sys.modules.setdefault("benchmarks.lib.utils.factory", factory_module)

    words_module = types.ModuleType("words")

    def build_ipa_pronunciation_prompt(_language_code, _word, definition="", sentence=""):
        return "context\n\nprompt"

    words_module.build_ipa_pronunciation_prompt = build_ipa_pronunciation_prompt
    sys.modules.setdefault("words", words_module)

    module_path = Path(__file__).with_name("word_to_ipa_runner.py")
    spec = importlib.util.spec_from_file_location("word_to_ipa_runner_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
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


if __name__ == "__main__":
    unittest.main()
