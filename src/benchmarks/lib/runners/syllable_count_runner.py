#!/usr/bin/python3

"""Runner for syllable count benchmark."""

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


@runner("0014_syllable_count")
class SyllableCountRunner(BenchmarkRunner):
    """Runner for testing a model's ability to count syllables in words across Latin-alphabet languages."""

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt for syllable count question.

        Args:
            question_data: Question data from database

        Returns:
            Tuple of (prompt, schema, context)
        """
        prompt = question_data.get("question_text", "")

        schema = {
            "type": "object",
            "properties": {
                "syllable_count": {
                    "type": "integer",
                    "description": "The number of syllables in the word",
                }
            },
            "required": ["syllable_count"],
        }

        context = (
            "You are performing a syllable counting task. "
            "Count the number of syllables in the given word as it is pronounced. "
            "Each syllable corresponds to one vowel sound. "
            "Provide your answer as a single integer in the specified JSON format."
        )

        return prompt, schema, context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if the syllable count is correct.

        Args:
            question_data: Question data from database
            response: Model response (structured dictionary)

        Returns:
            Boolean indicating whether the response is correct
        """
        expected_count = int(question_data.get("correct_answer", 0))

        actual_count: Optional[int] = None
        if isinstance(response, dict) and "syllable_count" in response:
            try:
                actual_count = int(response["syllable_count"])
            except (ValueError, TypeError):
                return False
        else:
            try:
                actual_count = int(response)
            except (ValueError, TypeError):
                return False

        return actual_count == expected_count

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
