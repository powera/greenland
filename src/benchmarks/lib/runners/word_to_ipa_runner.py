#!/usr/bin/python3

"""Runner for the word-to-IPA benchmark."""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from benchmarks.lib.utils.base_runner import BenchmarkRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata, BenchmarkResult
from benchmarks.lib.utils.factory import runner
from ipa import are_ipa_equivalent, normalize_ipa, weighted_similarity_ratio
from words import build_ipa_pronunciation_prompt

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Define benchmark metadata
BENCHMARK_METADATA = BenchmarkMetadata(
    code="0061_word_to_ipa",
    name="Word to IPA Pronunciation",
    description="A benchmark to evaluate a model's ability to convert words in multiple languages to IPA pronunciation.",
)


@runner("0061_word_to_ipa")
class WordToIPARunner(BenchmarkRunner):
    """Runner for word-to-IPA benchmark."""

    def __init__(self, model: str, metadata: BenchmarkMetadata):
        """Initialize runner with model and benchmark metadata."""
        super().__init__(model, metadata)

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt and context for the question.

        Args:
            question_data: Question data from database

        Returns:
            Tuple of (prompt, schema, context)
        """
        question_text = question_data.get("question_text", "")
        language_code = "en"
        word = ""
        definition = ""
        sentence = ""

        for line in question_text.splitlines():
            if line.startswith("Language:"):
                language_value = line.split(":", 1)[1].strip()
                language_code = language_value.split("(")[-1].rstrip(")").strip().lower()
            elif line.startswith("Word:"):
                word = line.split(":", 1)[1].strip()
            elif line.startswith("Definition:"):
                definition = line.split(":", 1)[1].strip()
            elif line.startswith("Sentence:"):
                sentence = line.split(":", 1)[1].strip()

        if not word:
            match = re.search(r"word ['\"]([^'\"]+)['\"]", question_text, re.IGNORECASE)
            word = match.group(1).strip() if match else question_text.strip()

        combined_prompt = build_ipa_pronunciation_prompt(
            language_code,
            word,
            definition=definition,
            sentence=sentence,
        )
        context, prompt = combined_prompt.split("\n\n", 1)

        # Define a schema to ensure the response is just the IPA
        schema = {
            "type": "object",
            "properties": {
                "ipa": {"type": "string", "description": "The IPA pronunciation of the word"}
            },
            "required": ["ipa"],
        }

        return prompt, schema, context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if a response is correct according to question criteria.

        Args:
            question_data: Question data from database
            response: Model response (structured data with 'ipa' field)

        Returns:
            Boolean indicating whether response is correct
        """
        # Get the correct answer from the question data
        correct_answer = question_data.get("correct_answer", "")

        # Get the model's response
        if isinstance(response, dict) and "ipa" in response:
            model_answer = response["ipa"].strip()
        else:
            # If not a dict or doesn't have 'ipa' key, use the raw response
            model_answer = str(response).strip()

        # Clean up the IPA strings by removing extra spaces and normalizing
        model_answer = self._normalize_ipa(model_answer)
        correct_answer = self._normalize_ipa(correct_answer)

        # Check if the model's answer matches the correct answer
        if model_answer == correct_answer:
            return True

        # Check against alternative pronunciations if available
        if (
            "evaluation_criteria" in question_data
            and "alternatives" in question_data["evaluation_criteria"]
        ):
            alternatives = question_data["evaluation_criteria"]["alternatives"]
            for alt in alternatives:
                normalized_alt = self._normalize_ipa(alt)
                if model_answer == normalized_alt:
                    return True

        # Check for close matches with slight variations (allow small differences)
        if are_ipa_equivalent(model_answer, correct_answer):
            return True

        # If we get here, the answer is incorrect
        return False

    def score_response(self, question_data: Dict, response: Any) -> int:
        """Score a response on a 0-100 scale.

        Rules:
        - exact/accepted match: 100
        - otherwise: phonetic-weighted Levenshtein similarity ratio scaled from 60
          (e.g. 80% -> 48, 50% -> 30)
        """
        if isinstance(response, dict) and "ipa" in response:
            model_answer = response["ipa"].strip()
        else:
            model_answer = str(response).strip()

        normalized_model = self._normalize_ipa(model_answer)
        if not normalized_model:
            return 0

        candidates = [self._normalize_ipa(question_data.get("correct_answer", ""))]
        if (
            "evaluation_criteria" in question_data
            and "alternatives" in question_data["evaluation_criteria"]
        ):
            candidates.extend(
                self._normalize_ipa(alt)
                for alt in question_data["evaluation_criteria"]["alternatives"]
            )

        # For rescoring/partial credit, reserve 100 for strict accepted matches only.
        if any(normalized_model == expected for expected in candidates if expected):
            return 100

        best_ratio = max(
            (
                weighted_similarity_ratio(normalized_model, expected)
                for expected in candidates
                if expected
            ),
            default=0.0,
        )
        return int(round(60 * best_ratio))

    def _weighted_similarity_ratio(self, left: str, right: str) -> float:
        """Backward-compatible wrapper around shared IPA similarity logic."""
        return weighted_similarity_ratio(left, right)

    def _normalize_ipa(self, ipa_string: str) -> str:
        """Backward-compatible wrapper around shared IPA normalization logic."""
        return normalize_ipa(ipa_string)

    def _is_close_match(
        self, model_answer: str, correct_answer: str, threshold: float = 0.8
    ) -> bool:
        """
        Check if the model's answer is a close match to the correct answer.

        Args:
            model_answer: The model's IPA answer
            correct_answer: The correct IPA answer
            threshold: Similarity threshold (0-1)

        Returns:
            Boolean indicating whether the answers are close enough
        """
        return are_ipa_equivalent(model_answer, correct_answer, threshold)

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """Build debug information for benchmark results."""
        # Extract model's answer based on response type
        if (
            hasattr(response, "structured_data")
            and isinstance(response.structured_data, dict)
            and "ipa" in response.structured_data
        ):
            # Response object with structured data
            model_answer = response.structured_data["ipa"]
        elif isinstance(response, dict) and "ipa" in response:
            # Direct dictionary with ipa key
            model_answer = response["ipa"]
        elif hasattr(response, "response_text"):
            # Response object with text
            model_answer = response.response_text
        else:
            # Any other format
            model_answer = str(response)

        # Get the correct answer
        correct_answer = question_data.get("correct_answer", "")

        # Simplified debug info with just essential information
        return {"response": model_answer, "expected": correct_answer, "is_correct": is_correct}
