#!/usr/bin/python3

"""Runner for geography benchmark questions."""

import json
import logging
from typing import Dict, Tuple, Optional, List, Any

from lib.benchmarks.base_runner import BenchmarkRunner
from lib.benchmarks.data_models import BenchmarkMetadata, AnswerType

logger = logging.getLogger(__name__)


class GeographyRunner(BenchmarkRunner):
    """
    Runner for executing geography benchmark questions against models.

    This benchmark tests a model's knowledge of world geography through
    multiple-choice questions about countries, cities, landmarks, etc.
    """

    def __init__(self, model: str, metadata: BenchmarkMetadata):
        """Initialize runner with model name and benchmark metadata."""
        super().__init__(model, metadata)

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare the prompt and schema for a geography question.

        Args:
            question_data: Question data from database

        Returns:
            Tuple of (prompt, schema, context)
        """
        # Extract question text and answer type
        question_text = question_data.get("question_text", "")
        answer_type = question_data.get("answer_type", AnswerType.MULTIPLE_CHOICE.value)

        # For multiple-choice questions, include the choices
        if answer_type == AnswerType.MULTIPLE_CHOICE.value:
            choices = question_data.get("choices", [])
            choices_text = "\n".join([f"{i+1}. {choice}" for i, choice in enumerate(choices)])

            prompt = f"""Answer the following geography question by selecting the correct option:

Question: {question_text}

Options:
{choices_text}

Provide your answer as a single option number or the exact text of your chosen answer.
"""

            # Simple JSON schema to ensure consistent output
            schema = {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "string",
                        "description": "The selected answer option (either the number or the text)",
                    }
                },
                "required": ["answer"],
            }

            # Context to guide the model
            context = """
            You are taking a geography test with multiple-choice questions.
            For each question, select the most accurate answer from the options provided.
            Answer directly with either the option number or the text of your chosen answer.
            """

            return prompt, schema, context

        # For free text questions (if any)
        else:
            prompt = f"""Answer the following geography question:

Question: {question_text}

Provide your answer as concisely as possible.
"""

            # No schema for free text answers
            context = """
            You are taking a geography test.
            For each question, provide the most accurate answer you can.
            Be concise and direct in your response.
            """

            return prompt, None, context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if a response is correct for a geography question.

        Args:
            question_data: Question data from database
            response: Model response

        Returns:
            Boolean indicating whether response is correct
        """
        answer_type = question_data.get("answer_type", AnswerType.MULTIPLE_CHOICE.value)
        correct_answer = question_data.get("correct_answer")
        choices = question_data.get("choices", [])

        # Handle different response formats
        if isinstance(response, dict) and "answer" in response:
            actual_response = response["answer"]
        else:
            actual_response = response

        # Convert to string for comparison
        actual_str = str(actual_response).strip().lower()

        # For multiple choice, check various ways model might respond
        if answer_type == AnswerType.MULTIPLE_CHOICE.value:
            # If answer is a number
            if actual_str.isdigit():
                try:
                    index = int(actual_str) - 1
                    if 0 <= index < len(choices):
                        return choices[index].lower() == correct_answer.lower()
                except (ValueError, IndexError):
                    return False

            # If answer is the text of an option
            for choice in choices:
                if actual_str == choice.lower():
                    return choice.lower() == correct_answer.lower()

            # Handle partial matches - if response contains exact correct answer
            if correct_answer.lower() in actual_str:
                return True

            return False

        # For free text (if any)
        else:
            return actual_str == correct_answer.lower()

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """
        Build debug information for benchmark results.

        Args:
            question_data: Question data from database
            response: Model response
            is_correct: Whether the response was evaluated as correct

        Returns:
            Dictionary with debug information
        """
        # Extract response based on format
        if hasattr(response, "structured_data") and response.structured_data:
            actual_response = response.structured_data
        else:
            actual_response = response.response_text

        # Format questions and answers for display
        choices = question_data.get("choices", [])
        choices_formatted = {f"option {i+1}": choice for i, choice in enumerate(choices)}

        return {
            "question": question_data.get("question_text"),
            "category": question_data.get("category", "Unknown"),
            "difficulty": question_data.get("difficulty", "medium"),
            "choices": choices_formatted,
            "correct_answer": question_data.get("correct_answer"),
            "model_response": actual_response,
            "is_correct": is_correct,
        }
