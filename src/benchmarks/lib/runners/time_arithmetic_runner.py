#!/usr/bin/python3

"""Runner for time arithmetic benchmark."""

import logging
import re
from typing import Any, Dict, Optional, Tuple

from benchmarks.lib.utils.base import BenchmarkRunner
from benchmarks.lib.utils.factory import runner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0026_time_arithmetic"
_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def _extract_time_string(response: Any) -> str:
    if isinstance(response, dict):
        value = response.get("time", "")
        return str(value).strip()
    return str(response).strip()


@runner(BENCHMARK_CODE)
class TimeArithmeticRunner(BenchmarkRunner):
    """Runner for testing a model's ability to compute times."""

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        prompt = question_data.get("question_text", "")

        schema = {
            "type": "object",
            "properties": {
                "time": {
                    "type": "string",
                    "description": "The resulting clock time in HH:MM 24-hour format",
                }
            },
            "required": ["time"],
        }

        context = (
            "You are solving a time arithmetic problem. "
            "Return only the resulting time in 24-hour HH:MM format using the JSON schema."
        )

        return prompt, schema, context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        expected = str(question_data.get("correct_answer", "")).strip()
        actual = _extract_time_string(response)

        if not _TIME_RE.match(actual):
            return False

        return actual == expected

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        actual = _extract_time_string(response)
        return {
            "response": actual,
            "expected": question_data.get("correct_answer"),
            "is_correct": is_correct,
        }
