#!/usr/bin/python3

"""Runner for algebra benchmark."""

import logging
import re
from typing import Any, Dict, Optional, Set, Tuple

from benchmarks.lib.utils.base import BenchmarkRunner
from benchmarks.lib.utils.factory import runner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0025_algebra"


def _parse_two_roots(text: str) -> Optional[Set[int]]:
    """Extract exactly two integers from a free-text response and return as a set."""
    nums = re.findall(r"-?\d+", text)
    if len(nums) >= 2:
        return {int(nums[0]), int(nums[1])}
    return None


@runner(BENCHMARK_CODE)
class AlgebraRunner(BenchmarkRunner):
    """Runner for testing a model's ability to solve linear and quadratic equations."""

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        prompt = question_data.get("question_text", "")
        answer_type = question_data.get("answer_type", "numeric")

        if answer_type == "free_text":
            schema: Optional[Dict] = {
                "type": "object",
                "properties": {
                    "values": {
                        "type": "string",
                        "description": (
                            "Both values of x, comma-separated, smallest first " "(e.g. '-3, 5')"
                        ),
                    }
                },
                "required": ["values"],
            }
        else:
            schema = {
                "type": "object",
                "properties": {
                    "result": {
                        "type": "number",
                        "description": "The value of x",
                    }
                },
                "required": ["result"],
            }

        context = (
            "You are solving an algebra equation. "
            "Find the value(s) of x that satisfy the equation. "
            "Provide your answer in the specified JSON format."
        )

        return prompt, schema, context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        answer_type = question_data.get("answer_type", "numeric")
        expected_str = str(question_data.get("correct_answer", ""))

        if answer_type == "free_text":
            # Two-root quadratic: compare parsed integer sets
            expected_roots = _parse_two_roots(expected_str)
            if expected_roots is None:
                return False

            if isinstance(response, dict):
                raw = str(response.get("values", ""))
            else:
                raw = str(response)

            actual_roots = _parse_two_roots(raw)
            return actual_roots == expected_roots

        else:
            # Linear or single-root quadratic: numeric comparison
            expected = float(expected_str)
            actual: Optional[float] = None

            if isinstance(response, dict) and "result" in response:
                try:
                    actual = float(response["result"])
                except (ValueError, TypeError):
                    return False
            else:
                try:
                    actual = float(str(response))
                except (ValueError, TypeError):
                    return False

            return abs(actual - expected) < 0.001

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        if hasattr(response, "structured_data") and response.structured_data:
            return {
                "prompt": question_data.get("question_text", ""),
                "response": response.structured_data,
                "expected": question_data.get("correct_answer"),
                "is_correct": is_correct,
            }
        else:
            return {
                "prompt": question_data.get("question_text", ""),
                "response": response.response_text,
                "expected": question_data.get("correct_answer"),
                "is_correct": is_correct,
            }
