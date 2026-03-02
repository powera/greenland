#!/usr/bin/python3

from benchmarks.lib.runners.python_coding_runner import PythonGCDRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata


def _runner() -> PythonGCDRunner:
    metadata = BenchmarkMetadata(code="0302_python_gcd", name="Python GCD")
    return PythonGCDRunner(model="gpt-4o-mini", metadata=metadata)


def test_python_coding_runner_scores_valid_solution() -> None:
    runner = _runner()
    question_data = {
        "correct_answer": {
            "function_name": "gcd_checked",
            "test_cases": [
                {"args": [54, 24], "expected": 6},
                {"args": [0, 5], "expected_exception": "ValueError"},
                {"args": ["8", 2], "expected_exception": "TypeError"},
            ],
        }
    }

    response = """
def gcd_checked(a, b):
    if not isinstance(a, int) or not isinstance(b, int):
        raise TypeError("ints required")
    if a <= 0 or b <= 0:
        raise ValueError("positive ints required")
    while b:
        a, b = b, a % b
    return a
"""

    assert runner.score_response(question_data, response) == 100


def test_python_coding_runner_allows_isinstance_builtin() -> None:
    runner = _runner()
    question_data = {
        "correct_answer": {
            "function_name": "classify",
            "test_cases": [
                {"args": [5], "expected": "int"},
                {"args": ["x"], "expected": "other"},
            ],
        }
    }

    response = """
def classify(value):
    if isinstance(value, int):
        return \"int\"
    return \"other\"
"""

    assert runner.score_response(question_data, response) == 100


def test_python_coding_runner_blocks_imports() -> None:
    runner = _runner()
    question_data = {
        "correct_answer": {
            "function_name": "gcd_checked",
            "test_cases": [{"args": [54, 24], "expected": 6}],
        }
    }

    response = """
import os

def gcd_checked(a, b):
    return 6
"""

    assert runner.score_response(question_data, response) == 0
