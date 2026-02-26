#!/usr/bin/python3

"""Runner for multilingual noun synonym identification benchmark."""

import logging
from typing import Any, Dict, Optional, Tuple

from benchmarks.lib.utils.base import BenchmarkRunner
from benchmarks.lib.utils.factory import runner

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0017_synonyms"


@runner(BENCHMARK_CODE)
class SynonymsRunner(BenchmarkRunner):
    """Runner for checking multilingual noun synonym identification."""

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        prompt = question_data["question_text"]
        schema = question_data.get(
            "schema",
            {
                "type": "object",
                "properties": {"synonym": {"type": "string"}},
                "required": ["synonym"],
            },
        )
        context = (
            "You are a linguistics assistant. For each question, identify which word from the"
            " provided candidates is a synonym of the given word. Respond with only the synonym word."
        )
        return prompt, schema, context

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        return {
            "response": response.structured_data.get("synonym", ""),
            "expected": question_data["correct_answer"].get("synonym", ""),
            "is_correct": is_correct,
        }
