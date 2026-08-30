#!/usr/bin/python3

"""Unit tests for 0017 synonyms runner."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_synonyms_runner_module() -> types.ModuleType:
    clients_module = types.ModuleType("clients")
    setattr(clients_module, "unified_client", object())
    sys.modules.setdefault("clients", clients_module)

    ollama_module = types.ModuleType("clients.ollama_client")

    class OllamaTimeoutError(Exception):
        pass

    setattr(ollama_module, "OllamaTimeoutError", OllamaTimeoutError)
    sys.modules.setdefault("clients.ollama_client", ollama_module)

    base_module = types.ModuleType("benchmarks.lib.utils.base")

    class BenchmarkRunner:
        def __init__(self, model: object, metadata: object) -> None:
            self.model = model
            self.metadata = metadata

    setattr(base_module, "BenchmarkRunner", BenchmarkRunner)
    sys.modules.setdefault("benchmarks.lib.utils.base", base_module)

    data_models_module = types.ModuleType("benchmarks.lib.utils.data_models")

    class BenchmarkResult:
        pass

    setattr(data_models_module, "BenchmarkResult", BenchmarkResult)
    sys.modules.setdefault("benchmarks.lib.utils.data_models", data_models_module)

    factory_module = types.ModuleType("benchmarks.lib.utils.factory")

    def runner(_code: str):  # type: ignore[no-untyped-def]
        def decorator(cls):  # type: ignore[no-untyped-def]
            return cls

        return decorator

    setattr(factory_module, "runner", runner)
    sys.modules.setdefault("benchmarks.lib.utils.factory", factory_module)

    module_path = Path(__file__).with_name("synonyms_runner.py")
    spec = importlib.util.spec_from_file_location("synonyms_runner_under_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER_MODULE = _load_synonyms_runner_module()
SynonymsRunner = RUNNER_MODULE.SynonymsRunner


class TestSynonymsRunner(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = SynonymsRunner.__new__(SynonymsRunner)

    def test_runner_uses_benchmark_runner_base(self) -> None:
        from benchmarks.lib.utils.base import BenchmarkRunner

        self.assertTrue(issubclass(SynonymsRunner, BenchmarkRunner))

    def test_prepare_prompt_returns_correct_fields(self) -> None:
        question_data = {
            "question_text": 'Which of these words is a synonym of "hat" in EN: cap, scarf, coat',
            "schema": {
                "type": "object",
                "properties": {"synonym": {"type": "string"}},
                "required": ["synonym"],
            },
        }
        prompt, schema, context = self.runner.prepare_prompt(question_data)

        self.assertIn("hat", prompt)
        self.assertIsNotNone(schema)
        self.assertIsNotNone(context)

    def test_build_debug_info(self) -> None:
        question_data = {"correct_answer": {"synonym": "cap"}}

        class FakeResponse:
            structured_data = {"synonym": "cap"}

        debug = self.runner.build_debug_info(question_data, FakeResponse(), True)
        self.assertEqual(debug["response"], "cap")
        self.assertEqual(debug["expected"], "cap")
        self.assertTrue(debug["is_correct"])

    def test_evaluate_response_correct(self) -> None:
        question_data = {"correct_answer": {"synonym": "cap"}}
        self.assertTrue(self.runner.evaluate_response(question_data, {"synonym": "cap"}))

    def test_evaluate_response_wrong(self) -> None:
        question_data = {"correct_answer": {"synonym": "cap"}}
        self.assertFalse(self.runner.evaluate_response(question_data, {"synonym": "scarf"}))

    def test_evaluate_response_case_insensitive(self) -> None:
        question_data = {"correct_answer": {"synonym": "cap"}}
        self.assertTrue(self.runner.evaluate_response(question_data, {"synonym": "Cap"}))

    def test_evaluate_response_whitespace_trimmed(self) -> None:
        question_data = {"correct_answer": {"synonym": "cap"}}
        self.assertTrue(self.runner.evaluate_response(question_data, {"synonym": "  cap  "}))

    def test_evaluate_response_non_dict_fails(self) -> None:
        question_data = {"correct_answer": {"synonym": "cap"}}
        self.assertFalse(self.runner.evaluate_response(question_data, "cap"))


if __name__ == "__main__":
    unittest.main()
