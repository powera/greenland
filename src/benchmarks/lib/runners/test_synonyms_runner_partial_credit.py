#!/usr/bin/python3

"""Unit tests for 0111 synonyms runner partial-credit behavior."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_synonyms_runner_module():
    clients_module = types.ModuleType("clients")
    clients_module.unified_client = object()
    sys.modules.setdefault("clients", clients_module)

    ollama_module = types.ModuleType("clients.ollama_client")

    class OllamaTimeoutError(Exception):
        pass

    ollama_module.OllamaTimeoutError = OllamaTimeoutError
    sys.modules.setdefault("clients.ollama_client", ollama_module)

    base_module = types.ModuleType("benchmarks.lib.utils.base")

    class BenchmarkRunner:
        def __init__(self, model, metadata):
            self.model = model
            self.metadata = metadata

    base_module.BenchmarkRunner = BenchmarkRunner
    sys.modules.setdefault("benchmarks.lib.utils.base", base_module)

    data_models_module = types.ModuleType("benchmarks.lib.utils.data_models")

    class BenchmarkResult:
        pass

    data_models_module.BenchmarkResult = BenchmarkResult
    sys.modules.setdefault("benchmarks.lib.utils.data_models", data_models_module)

    factory_module = types.ModuleType("benchmarks.lib.utils.factory")

    def runner(_code):
        def decorator(cls):
            return cls

        return decorator

    factory_module.runner = runner
    sys.modules.setdefault("benchmarks.lib.utils.factory", factory_module)

    runners_pkg = types.ModuleType("benchmarks.lib.runners")
    runners_pkg.__path__ = []
    sys.modules.setdefault("benchmarks.lib.runners", runners_pkg)

    scoring_path = Path(__file__).parents[2] / "synonyms_scoring.py"
    scoring_spec = importlib.util.spec_from_file_location("benchmarks.synonyms_scoring", scoring_path)
    scoring_module = importlib.util.module_from_spec(scoring_spec)
    assert scoring_spec and scoring_spec.loader
    scoring_spec.loader.exec_module(scoring_module)
    sys.modules["benchmarks.synonyms_scoring"] = scoring_module

    partial_path = Path(__file__).with_name("partial_credit_runner.py")
    partial_spec = importlib.util.spec_from_file_location(
        "benchmarks.lib.runners.partial_credit_runner", partial_path
    )
    partial_module = importlib.util.module_from_spec(partial_spec)
    assert partial_spec and partial_spec.loader
    partial_spec.loader.exec_module(partial_module)
    sys.modules["benchmarks.lib.runners.partial_credit_runner"] = partial_module

    module_path = Path(__file__).with_name("synonyms_runner.py")
    spec = importlib.util.spec_from_file_location("synonyms_runner_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


RUNNER_MODULE = _load_synonyms_runner_module()
SynonymsRunner = RUNNER_MODULE.SynonymsRunner
PartialCreditRunner = RUNNER_MODULE.PartialCreditRunner


class TestSynonymsRunnerPartialCredit(unittest.TestCase):
    def setUp(self):
        self.runner = SynonymsRunner.__new__(SynonymsRunner)

    def test_runner_uses_partial_credit_base(self):
        self.assertTrue(issubclass(SynonymsRunner, PartialCreditRunner))

    def test_score_response_returns_partial_numeric_score(self):
        question_data = {
            "correct_answer": {
                "mandatory_synonyms": ["cap"],
                "optional_synonyms": ["headgear", "headwear"],
            }
        }
        response = {"synonyms": ["cap", "headgear"]}

        score = self.runner.score_response(question_data, response)

        self.assertEqual(score, 90)


if __name__ == "__main__":
    unittest.main()
