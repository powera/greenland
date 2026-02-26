#!/usr/bin/python3

"""Runner for geometry benchmark."""

import logging
from typing import Any, Dict, Optional, Tuple

from benchmarks.lib.utils.base import BenchmarkRunner
from benchmarks.lib.utils.factory import runner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0027_geometry"

_DEFAULT_TOLERANCE = 0.001


@runner(BENCHMARK_CODE)
class GeometryRunner(BenchmarkRunner):
    """Runner for testing a model's ability to calculate geometric measurements."""

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        prompt = question_data.get("question_text", "")

        schema = {
            "type": "object",
            "properties": {
                "result": {
                    "type": "number",
                    "description": "The numeric result of the geometry calculation",
                }
            },
            "required": ["result"],
        }

        context = (
            "You are solving a geometry problem. "
            "Apply the appropriate formula and calculate the result. "
            "Provide your answer as a number in the specified JSON format."
        )

        return prompt, schema, context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        expected = float(question_data.get("correct_answer", 0))

        # Read tolerance from the stored evaluation_criteria (set per shape type)
        criteria = question_data.get("evaluation_criteria", {})
        tolerance = float(criteria.get("tolerance", _DEFAULT_TOLERANCE))

        actual: Optional[float] = None
        if isinstance(response, dict) and "result" in response:
            try:
                actual = float(response["result"])
            except (ValueError, TypeError):
                return False
        else:
            try:
                actual = float(response)
            except (ValueError, TypeError):
                return False

        return abs(actual - expected) < tolerance

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
