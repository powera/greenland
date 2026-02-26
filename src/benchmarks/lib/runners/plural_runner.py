#!/usr/bin/python3

"""Runner for plural noun benchmark."""

import logging
from typing import Any, Dict, Optional, Tuple

from benchmarks.lib.utils.base import BenchmarkRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata
from benchmarks.lib.utils.factory import runner

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@runner("0033_plural")
class PluralRunner(BenchmarkRunner):
    """Runner for plural noun benchmark tests."""

    def __init__(self, model: str, metadata: BenchmarkMetadata) -> None:
        """Initialize runner with model name and benchmark metadata."""
        super().__init__(model, metadata)

    def prepare_prompt(
        self, question_data: Dict[str, Any]
    ) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
        """
        Prepare prompt and context for a plural question.

        Args:
            question_data: Question data from database (already parsed from JSON)

        Returns:
            Tuple of (prompt, schema, context)
        """
        prompt = question_data["question_text"]
        schema = question_data.get("schema")

        context = (
            "You are a linguistics expert. "
            "Given a singular English noun, produce its correct plural form. "
            "Apply the appropriate pluralization rule:\n"
            "- Regular nouns: add -s (cat → cats)\n"
            "- Nouns ending in -ch, -sh, -s, -x, -z: add -es (bus → buses)\n"
            "- Nouns ending in consonant + y: change y to -ies (city → cities)\n"
            "- Nouns ending in -f or -fe: change to -ves (leaf → leaves)\n"
            "- Irregular nouns: use the correct form (child → children, tooth → teeth)\n"
            "- Invariant nouns: same form for singular and plural (sheep → sheep)\n"
            "- Latin/Greek nouns: use the classical plural (cactus → cacti)\n"
            "Return only the plural form, following the provided schema."
        )

        return prompt, schema, context

    def evaluate_response(self, question_data: Dict[str, Any], response: Any) -> bool:
        """
        Evaluate if the model's plural form is correct.

        Args:
            question_data: Question data from database (already parsed from JSON)
            response: Model response

        Returns:
            Boolean indicating whether response is correct
        """
        correct_answer = question_data.get("correct_answer", {})
        expected_plural = correct_answer.get("plural", "").lower().strip()

        if isinstance(response, dict) and "plural" in response:
            model_plural = response["plural"].lower().strip()
        else:
            model_plural = str(response).lower().strip()

        return model_plural == expected_plural

    def build_debug_info(
        self, question_data: Dict[str, Any], response: Any, is_correct: bool
    ) -> Dict[str, Any]:
        """
        Build debug information for benchmark results.

        Args:
            question_data: Question data from database (already parsed from JSON)
            response: Model response object
            is_correct: Whether the response was evaluated as correct

        Returns:
            Dictionary containing debug information
        """
        if hasattr(response, "structured_data") and response.structured_data:
            model_answer = response.structured_data
        else:
            model_answer = getattr(response, "response_text", str(response))

        return {
            "model_answer": model_answer,
            "expected_answer": question_data.get("correct_answer"),
            "is_correct": is_correct,
        }
