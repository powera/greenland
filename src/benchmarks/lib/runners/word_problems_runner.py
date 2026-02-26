#!/usr/bin/python3

"""Runner for math word problems benchmark."""

import logging
from typing import Any, Dict, Optional, Tuple

from benchmarks.lib.utils.base import BenchmarkRunner
from benchmarks.lib.utils.factory import runner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0023_word_problems"


@runner(BENCHMARK_CODE)
class WordProblemsRunner(BenchmarkRunner):
    """Runner for testing a model's ability to solve math word problems."""

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        prompt = question_data.get("question_text", "")

        schema = {
            "type": "object",
            "properties": {
                "result": {
                    "type": "number",
                    "description": "The numeric answer to the word problem",
                }
            },
            "required": ["result"],
        }

        context = (
            "You are solving a math word problem. Read carefully and identify the relevant numbers. "
            "Some problems may contain extra information that is not needed to answer the question. "
            "Provide your final numeric answer in the specified JSON format."
        )

        return prompt, schema, context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        expected = float(question_data.get("correct_answer", 0))

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

        return abs(actual - expected) < 0.001

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
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
