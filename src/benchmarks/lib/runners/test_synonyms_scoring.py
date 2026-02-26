#!/usr/bin/python3

"""Unit tests for synonyms runner evaluate_response (0017).

Kept as a standalone script so it can run without the full benchmark
dependency chain (sqlalchemy, etc.).  Uses the same dynamic-load approach
as test_synonyms_runner_partial_credit.py.
"""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_runner() -> types.ModuleType:
    clients_module = types.ModuleType("clients")
    clients_module.unified_client = object()  # type: ignore[attr-defined]
    sys.modules.setdefault("clients", clients_module)

    ollama_module = types.ModuleType("clients.ollama_client")

    class OllamaTimeoutError(Exception):
        pass

    ollama_module.OllamaTimeoutError = OllamaTimeoutError  # type: ignore[attr-defined]
    sys.modules.setdefault("clients.ollama_client", ollama_module)

    base_module = types.ModuleType("benchmarks.lib.utils.base")

    class BenchmarkRunner:
        def __init__(self, model: object, metadata: object) -> None:
            self.model = model
            self.metadata = metadata

    base_module.BenchmarkRunner = BenchmarkRunner  # type: ignore[attr-defined]
    sys.modules.setdefault("benchmarks.lib.utils.base", base_module)

    factory_module = types.ModuleType("benchmarks.lib.utils.factory")

    def runner(_code: str):  # type: ignore[no-untyped-def]
        def decorator(cls):  # type: ignore[no-untyped-def]
            return cls

        return decorator

    factory_module.runner = runner  # type: ignore[attr-defined]
    sys.modules.setdefault("benchmarks.lib.utils.factory", factory_module)

    module_path = Path(__file__).with_name("synonyms_runner.py")
    spec = importlib.util.spec_from_file_location("synonyms_runner_scoring_test", module_path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_RUNNER_MODULE = _load_runner()
_SynonymsRunner = _RUNNER_MODULE.SynonymsRunner


class TestSynonymsEvaluateResponse(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = _SynonymsRunner.__new__(_SynonymsRunner)

    def test_correct_synonym_passes(self) -> None:
        question_data = {"correct_answer": {"synonym": "cap"}}
        self.assertTrue(self.runner.evaluate_response(question_data, {"synonym": "cap"}))

    def test_wrong_synonym_fails(self) -> None:
        question_data = {"correct_answer": {"synonym": "cap"}}
        self.assertFalse(self.runner.evaluate_response(question_data, {"synonym": "scarf"}))

    def test_case_insensitive_match(self) -> None:
        question_data = {"correct_answer": {"synonym": "cap"}}
        self.assertTrue(self.runner.evaluate_response(question_data, {"synonym": "Cap"}))

    def test_whitespace_trimmed(self) -> None:
        question_data = {"correct_answer": {"synonym": "cap"}}
        self.assertTrue(self.runner.evaluate_response(question_data, {"synonym": "  cap  "}))

    def test_non_dict_response_fails(self) -> None:
        question_data = {"correct_answer": {"synonym": "cap"}}
        self.assertFalse(self.runner.evaluate_response(question_data, "cap"))


if __name__ == "__main__":
    unittest.main()
