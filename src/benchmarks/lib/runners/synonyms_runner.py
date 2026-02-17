#!/usr/bin/python3

"""Runner for multilingual noun synonym benchmark."""

import logging
from typing import Any, Dict, Optional, Tuple

from benchmarks.synonyms_scoring import score_synonyms_response
from benchmarks.lib.utils.base import BenchmarkRunner
from benchmarks.lib.utils.factory import runner

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0111_synonyms"
PASSING_SCORE_PERCENT = 80.0


@runner(BENCHMARK_CODE)
class SynonymsRunner(BenchmarkRunner):
    """Runner for checking multilingual noun synonym generation."""

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        prompt = question_data["question_text"]
        schema = question_data.get("schema")
        context = (
            "You are taking a multilingual vocabulary test. "
            "Return only JSON that matches the schema and includes noun synonyms in the requested language."
        )
        return prompt, schema, context

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        return score_synonyms_response(question_data, response) >= PASSING_SCORE_PERCENT

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        response_data = response.structured_data if hasattr(response, "structured_data") else response
        response_text = response.response_text if hasattr(response, "response_text") else str(response)
        score_percent = score_synonyms_response(question_data, response_data or response_text)

        return {
            "model_answer": response_data,
            "model_response_text": response_text,
            "score_percent": score_percent,
            "pass_threshold_percent": PASSING_SCORE_PERCENT,
            "is_correct": is_correct,
            "correct_answer": question_data.get("correct_answer", {}),
        }
