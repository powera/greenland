#!/usr/bin/python3

"""Runner for fractions and percentages benchmark."""

import logging
from typing import Any, Dict, Optional, Tuple

from benchmarks.lib.utils.base import BenchmarkRunner
from benchmarks.lib.utils.factory import runner

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0024_percentage_math"


@runner(BENCHMARK_CODE)
class PercentageMathRunner(BenchmarkRunner):
    """Runner for testing a model's ability to calculate fractions and percentages."""

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt for fractions and percentages question.

        Args:
            question_data: Question data from database

        Returns:
            Tuple of (prompt, schema, context)
        """
        prompt = question_data.get("question_text", "")

        schema = {
            "type": "object",
            "properties": {
                "result": {
                    "type": "number",
                    "description": "The numeric result of the calculation",
                }
            },
            "required": ["result"],
        }

        context = (
            "You are performing a fractions and percentages calculation task. "
            "Calculate the numeric result of the given problem. "
            "Provide your answer as a single number in the specified JSON format."
        )

        return prompt, schema, context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if the fractions/percentages result is correct.

        Args:
            question_data: Question data from database
            response: Model response (structured dictionary)

        Returns:
            Boolean indicating whether the response is correct
        """
        expected = float(question_data.get("correct_answer", 0))
        eval_criteria = question_data.get("evaluation_criteria") or {}
        tolerance = float(eval_criteria.get("tolerance", 0.01))

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

        return abs(actual - expected) <= tolerance

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """Build debug information for benchmark results."""
        if hasattr(response, "structured_data") and response.structured_data:
            return {
                "response": response.structured_data,
                "expected": question_data.get("correct_answer"),
                "is_correct": is_correct,
            }
        else:
            return {
                "response": response.response_text,
                "expected": question_data.get("correct_answer"),
                "is_correct": is_correct,
            }
