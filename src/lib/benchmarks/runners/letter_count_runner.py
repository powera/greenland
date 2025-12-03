#!/usr/bin/python3

"""Runner for letter count benchmark."""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple

from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@runner("0012_letter_count")
class LetterCountRunner(BenchmarkRunner):
    """Runner for testing a model's ability to count letter occurrences in words."""

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt for letter count question.

        Args:
            question_data: Question data from database

        Returns:
            Tuple of (prompt, schema, context)
        """
        prompt = question_data.get("question_text", "")

        # Define schema for structured response
        schema = {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "The number of times the letter appears in the word",
                }
            },
            "required": ["count"],
        }

        # Add context for guidance
        context = """You are performing a letter counting task. 
Count how many times a specific letter appears in a word.
Provide your answer as a single integer in the specified JSON format."""

        return prompt, schema, context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if the count is correct.

        Args:
            question_data: Question data from database
            response: Model response (structured dictionary)

        Returns:
            Boolean indicating whether the response is correct
        """
        expected_count = int(question_data.get("correct_answer", 0))

        # Extract count from response
        actual_count = None
        if isinstance(response, dict) and "count" in response:
            try:
                actual_count = int(response["count"])
            except (ValueError, TypeError):
                return False
        else:
            # Try to parse response as a direct number
            try:
                actual_count = int(response)
            except (ValueError, TypeError):
                return False

        # Check for exact match (letter counting should be exact)
        return actual_count == expected_count

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """Build debug information for benchmark results."""
        # Create debug info with the question text for better context
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
