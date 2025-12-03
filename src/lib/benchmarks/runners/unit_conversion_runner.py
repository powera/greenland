#!/usr/bin/python3

"""Runner for unit conversion benchmark."""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple

from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.data_models import BenchmarkMetadata
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Benchmark code
BENCHMARK_CODE = "0022_unit_conversion"


@runner(BENCHMARK_CODE)
class UnitConversionRunner(BenchmarkRunner):
    """Runner for unit conversion benchmark."""

    def __init__(self, model: str, metadata: BenchmarkMetadata):
        """Initialize runner with model name and metadata."""
        super().__init__(model, metadata)

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt for unit conversion question.

        Args:
            question_data: Question data from database

        Returns:
            Tuple of (prompt, schema, context)
        """
        prompt = question_data.get("question_text", "")

        # Create schema for structured numeric response
        schema = {
            "type": "object",
            "properties": {"value": {"type": "number", "description": "The converted value"}},
            "required": ["value"],
        }

        # Add brief context explaining the task
        context = """You are performing unit conversions. 
Answer with just the numeric value after conversion. 
Be as precise as possible and follow standard conversion formulas."""

        return prompt, schema, context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if a unit conversion response is correct.

        Args:
            question_data: Question data from database
            response: Model response (either structured data or text)

        Returns:
            Boolean indicating whether response is correct
        """
        # Extract the value from structured response
        if isinstance(response, dict) and "value" in response:
            actual_value = response["value"]
        else:
            # Try to parse the first number from text response
            try:
                import re

                numbers = re.findall(r"[-+]?\d*\.\d+|\d+", str(response))
                if numbers:
                    actual_value = float(numbers[0])
                else:
                    return False
            except (ValueError, TypeError):
                return False

        # Get correct answer and tolerance
        correct_value = float(question_data.get("correct_answer", 0))
        eval_criteria = question_data.get("evaluation_criteria", {})
        tolerance = float(eval_criteria.get("tolerance", 0.01))

        # Check if within tolerance
        return abs(float(actual_value) - correct_value) <= tolerance

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """Build debug information for benchmark results."""
        # Get the response value
        if hasattr(response, "structured_data") and response.structured_data:
            actual_value = response.structured_data.get("value", "No value provided")
            response_text = response.response_text
        else:
            actual_value = "Unknown (could not parse response)"
            response_text = response.response_text

        # Enhanced debug info
        return {
            "question": question_data.get("question_text"),
            "expected_value": question_data.get("correct_answer"),
            "tolerance": question_data.get("evaluation_criteria", {}).get("tolerance", 0.01),
            "actual_value": actual_value,
            "full_response": response_text,
            "is_correct": is_correct,
        }
