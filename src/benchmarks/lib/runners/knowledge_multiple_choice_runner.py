#!/usr/bin/python3

"""Shared runner helpers for simple knowledge multiple-choice benchmarks."""

from typing import Any, Dict, Optional, Tuple

from benchmarks.lib.utils.base import BenchmarkRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata


class KnowledgeMultipleChoiceRunner(BenchmarkRunner):
    """Shared evaluation behavior for knowledge benchmarks with MCQ answers."""

    def __init__(self, model: str, metadata: BenchmarkMetadata, context: str):
        super().__init__(model, metadata)
        self.context = context

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        choices = question_data.get("choices", [])
        options = "\n".join([f"{i+1}. {choice}" for i, choice in enumerate(choices)])
        prompt = (
            f"{question_data.get('question_text', '')}\n\n"
            f"Options:\n{options}\n\n"
            "First explain your reasoning, then give the exact text of the correct option as your answer. Do not include the option number."
        )

        schema = {
            "type": "object",
            "properties": {
                "reasoning": {"type": "string"},
                "answer": {"type": "string"},
            },
            "required": ["reasoning", "answer"],
        }
        return prompt, schema, self.context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        correct = str(question_data.get("correct_answer", "")).strip().lower()
        choices = [str(choice) for choice in question_data.get("choices", [])]

        actual = (
            response.get("answer")
            if isinstance(response, dict) and "answer" in response
            else response
        )
        actual_norm = str(actual).strip().lower()

        for choice in choices:
            if actual_norm == choice.strip().lower():
                return choice.strip().lower() == correct

        return actual_norm == correct
