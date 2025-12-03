#!/usr/bin/python3

"""Runner for part of speech benchmark."""

import json
import logging
from typing import Dict, List, Optional, Any, Tuple

from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.data_models import BenchmarkMetadata
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@runner("0032_part_of_speech")
class PartOfSpeechRunner(BenchmarkRunner):
    """Runner for part of speech benchmark tests."""

    def __init__(self, model: str, metadata: BenchmarkMetadata):
        """Initialize runner with model name and benchmark metadata."""
        super().__init__(model, metadata)

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt and context for part of speech question.

        Args:
            question_data: Question data from database (already parsed from JSON)

        Returns:
            Tuple of (prompt, schema, context)
        """
        prompt = question_data["question_text"]
        schema = question_data.get("schema")

        # Create system context with instructions
        context = """
        You are a language expert tasked with identifying parts of speech in sentences.
        
        Analyze the sentence carefully and identify the part of speech of the specified word.
        
        Valid parts of speech include: noun, verb, adjective, adverb, pronoun, preposition, conjunction, interjection, and determiner.
        
        Provide a concise response with just the part of speech, following the provided schema.
        """

        return prompt, schema, context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if the model's part of speech identification is correct.

        Args:
            question_data: Question data from database (already parsed from JSON)
            response: Model response (format depends on benchmark)

        Returns:
            Boolean indicating whether response is correct
        """
        # Get expected answer
        correct_answer = question_data.get("correct_answer", {})
        expected_pos = correct_answer.get("part_of_speech", "").lower()

        # Get model's answer
        if isinstance(response, dict) and "part_of_speech" in response:
            model_pos = response["part_of_speech"].lower()
        else:
            # Try to extract from text response
            model_pos = str(response).lower()

        # Normalize common variations
        normalized_pos = model_pos.strip()

        # Handle common variations in responses
        if normalized_pos in ["noun", "nouns"]:
            normalized_pos = "noun"
        elif normalized_pos in ["verb", "verbs", "action verb"]:
            normalized_pos = "verb"
        elif normalized_pos in ["adjective", "adjectives", "adj", "adj."]:
            normalized_pos = "adjective"
        elif normalized_pos in ["adverb", "adverbs", "adv", "adv."]:
            normalized_pos = "adverb"
        elif normalized_pos in ["preposition", "prepositions", "prep", "prep."]:
            normalized_pos = "preposition"
        elif normalized_pos in ["conjunction", "conjunctions", "conj", "conj."]:
            normalized_pos = "conjunction"
        elif normalized_pos in ["pronoun", "pronouns", "pron", "pron."]:
            normalized_pos = "pronoun"
        elif normalized_pos in ["determiner", "determiners", "det", "det."]:
            normalized_pos = "determiner"
        elif normalized_pos in ["interjection", "interjections", "interj", "interj."]:
            normalized_pos = "interjection"

        # Check if the normalized answer matches the expected part of speech
        return normalized_pos == expected_pos

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """
        Build debug information for benchmark results.

        Args:
            question_data: Question data from database (already parsed from JSON)
            response: Model response object
            is_correct: Whether the response was evaluated as correct

        Returns:
            Dictionary containing debug information
        """
        # Extract structured response or text response
        if hasattr(response, "structured_data") and response.structured_data:
            model_answer = response.structured_data
        else:
            model_answer = response.response_text

        return {
            "prompt": question_data.get("question_text", ""),
            "model_answer": model_answer,
            "expected_answer": question_data.get("correct_answer"),
            "is_correct": is_correct,
        }
