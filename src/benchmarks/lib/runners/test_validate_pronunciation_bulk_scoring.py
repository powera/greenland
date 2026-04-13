#!/usr/bin/python3

"""Unit tests for 0141 bulk pronunciation scoring rules."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path


def _load_validate_pronunciation_bulk_runner_module():
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

    agents_verification_module = types.ModuleType("agents.bebras.verification")

    def build_bulk_pronunciation_verification_context():
        return "context"

    def build_bulk_pronunciation_verification_prompt(_items):
        return "prompt"

    def build_bulk_pronunciation_verification_schema():
        return {}

    agents_verification_module.build_bulk_pronunciation_verification_context = (
        build_bulk_pronunciation_verification_context
    )
    agents_verification_module.build_bulk_pronunciation_verification_prompt = (
        build_bulk_pronunciation_verification_prompt
    )
    agents_verification_module.build_bulk_pronunciation_verification_schema = (
        build_bulk_pronunciation_verification_schema
    )
    sys.modules.setdefault("agents.bebras.verification", agents_verification_module)

    clients_module = types.ModuleType("clients")
    clients_module.unified_client = types.SimpleNamespace(generate_chat=lambda **_: None)
    sys.modules.setdefault("clients", clients_module)

    module_path = Path(__file__).with_name("validate_pronunciation_bulk_runner.py")
    spec = importlib.util.spec_from_file_location(
        "validate_pronunciation_bulk_runner_under_test", module_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


RUNNER_MODULE = _load_validate_pronunciation_bulk_runner_module()
ValidatePronunciationBulkRunner = RUNNER_MODULE.ValidatePronunciationBulkRunner


class TestValidatePronunciationBulkScoring(unittest.TestCase):
    def test_perfect_match_scores_100(self):
        score, breakdown = ValidatePronunciationBulkRunner._score_from_entry_sets(
            expected_wrong_ipa_entries=[{"entry_id": "C1_001"}],
            expected_wrong_phonetic_entries=[{"entry_id": "C1_002"}],
            actual_wrong_ipa_entries=[{"entry_id": "C1_001"}],
            actual_wrong_phonetic_entries=[{"entry_id": "C1_002"}],
        )

        self.assertEqual(score, 100)
        self.assertEqual(breakdown["missing_count"], 0)
        self.assertEqual(breakdown["extra_count"], 0)

    def test_missing_any_expected_entry_scores_0(self):
        score, breakdown = ValidatePronunciationBulkRunner._score_from_entry_sets(
            expected_wrong_ipa_entries=[{"entry_id": "C1_001"}],
            expected_wrong_phonetic_entries=[{"entry_id": "C1_002"}],
            actual_wrong_ipa_entries=[{"entry_id": "C1_001"}],
            actual_wrong_phonetic_entries=[],
        )

        self.assertEqual(score, 0)
        self.assertEqual(breakdown["missing_count"], 1)

    def test_extra_entries_penalized_with_base_deduction(self):
        score, breakdown = ValidatePronunciationBulkRunner._score_from_entry_sets(
            expected_wrong_ipa_entries=[{"entry_id": "C1_001"}],
            expected_wrong_phonetic_entries=[],
            actual_wrong_ipa_entries=[{"entry_id": "C1_001"}, {"entry_id": "C1_010"}],
            actual_wrong_phonetic_entries=[],
        )

        self.assertEqual(score, 70)
        self.assertEqual(breakdown["missing_count"], 0)
        self.assertEqual(breakdown["extra_count"], 1)


if __name__ == "__main__":
    unittest.main()
