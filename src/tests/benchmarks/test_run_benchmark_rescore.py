#!/usr/bin/python3
"""Tests for benchmark rescore debug metadata refresh."""

import json
import sys
import types
from typing import Any, Dict

if "pydantic" not in sys.modules:
    pydantic_stub = types.ModuleType("pydantic")

    class BaseModel:  # pragma: no cover - compatibility shim
        pass

    setattr(pydantic_stub, "BaseModel", BaseModel)
    sys.modules["pydantic"] = pydantic_stub

from benchmarks import run_benchmark


class _RunnerWithDebugBuilder:
    CORRECTNESS_THRESHOLD = 80

    def build_debug_info(
        self, question_data: Dict[str, Any], response: Any, is_correct: bool
    ) -> Dict[str, Any]:
        return {
            "response": response,
            "question_name": question_data["name"],
            "is_correct": is_correct,
            "test_case_results": [{"case": "new", "passed": is_correct}],
        }


class _RunnerWithFailingDebugBuilder:
    def build_debug_info(
        self, question_data: Dict[str, Any], response: Any, is_correct: bool
    ) -> None:
        raise RuntimeError("debug build failed")


def test_refresh_debug_json_recomputes_test_case_results() -> None:
    debug_text = run_benchmark._refresh_debug_json(
        runner=_RunnerWithDebugBuilder(),
        question_data={"name": "case-a"},
        model_response="answer",
        rescored=85,
        existing_debug_json={"test_case_results": [{"case": "old", "passed": False}]},
    )

    payload = json.loads(debug_text)

    assert payload["response"] == "answer"
    assert payload["question_name"] == "case-a"
    assert payload["is_correct"] is True
    assert payload["test_case_results"] == [{"case": "new", "passed": True}]
    assert payload["scoring_runner"] == "_RunnerWithDebugBuilder"


def test_refresh_debug_json_keeps_existing_when_debug_builder_fails() -> None:
    debug_text = run_benchmark._refresh_debug_json(
        runner=_RunnerWithFailingDebugBuilder(),
        question_data={"name": "case-b"},
        model_response="answer",
        rescored=0,
        existing_debug_json={"existing": "value"},
    )

    payload = json.loads(debug_text)

    assert payload["existing"] == "value"
    assert payload["scoring_runner"] == "_RunnerWithFailingDebugBuilder"
    assert "test_case_results" not in payload
