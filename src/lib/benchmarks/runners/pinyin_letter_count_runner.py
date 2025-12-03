#!/usr/bin/python3

"""Runner for the Pinyin Letter Count benchmark."""

import json
import logging
from typing import Dict, Tuple, Optional, Any

from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.data_models import BenchmarkMetadata
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@runner("0051_pinyin_letters")
class PinyinLetterCountRunner(BenchmarkRunner):
    """Runner for Pinyin letter count benchmark."""

    def __init__(self, model: str, metadata: BenchmarkMetadata):
        """Initialize runner with model name and benchmark metadata."""
        super().__init__(model, metadata)

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare the prompt for the benchmark question.

        Args:
            question_data: Question data dictionary

        Returns:
            Tuple of (prompt, schema, context)
        """
        # Extract question text from data
        question_text = question_data.get("question_text", "")

        # Create JSON schema for structured response
        schema = {
            "type": "object",
            "properties": {
                "letter_count": {
                    "type": "integer",
                    "description": "The count of the specified letter in the Pinyin representation",
                }
            },
            "required": ["letter_count"],
        }

        # Define system context
        context = """
        You are tasked with counting how many times a specific letter appears in the Pinyin representation of a Chinese sentence.
        
        Important rules:
        1. Pinyin is the romanization system for Mandarin Chinese.
        2. Convert the Chinese characters to their Pinyin representation first (you may know this already).
        3. Then count the occurrences of the specified letter in the Pinyin.
        4. Count uppercase and lowercase occurrences of the letter.
        5. Provide only the count as a number in your response.
        
        Example:
        For the Chinese sentence "你好" (nǐ hǎo), the Pinyin representation is "NI HAO".
        If asked to count the letter 'a', the answer would be 1.
        If asked to count the letter 'i', the answer would be 1.
        
        Return only the numerical count.
        """

        return question_text, schema, context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if the model's response is correct.

        Args:
            question_data: Question data dictionary
            response: Model response (expected to be a dictionary or integer)

        Returns:
            Boolean indicating whether the response is correct
        """
        # Get the expected count from question data
        expected_count = int(question_data.get("correct_answer", 0))

        # Extract model's answer
        model_count = None

        if isinstance(response, dict) and "letter_count" in response:
            model_count = response["letter_count"]
        elif isinstance(response, (int, str)):
            try:
                model_count = int(response)
            except (ValueError, TypeError):
                logger.error(f"Could not convert response to integer: {response}")
                return False

        if model_count is None:
            logger.error(f"Could not extract count from response: {response}")
            return False

        # Compare expected and actual counts
        return model_count == expected_count

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """
        Build debug information for the benchmark results.

        Args:
            question_data: Question data dictionary
            response: Model response
            is_correct: Whether the response is correct

        Returns:
            Dictionary with debug information
        """
        # Extract relevant information from question data
        question_text = question_data.get("question_text", "")
        expected_count = question_data.get("correct_answer", "")

        # Extract model's answer
        model_count = None
        if isinstance(response, dict) and "letter_count" in response:
            model_count = response["letter_count"]
        elif hasattr(response, "structured_data") and response.structured_data:
            model_count = response.structured_data.get("letter_count", "Unknown")
        else:
            model_count = (
                response.response_text if hasattr(response, "response_text") else str(response)
            )

        # Build debug info
        return {
            "question": question_text,
            "expected_count": expected_count,
            "model_count": model_count,
            "is_correct": is_correct,
        }
