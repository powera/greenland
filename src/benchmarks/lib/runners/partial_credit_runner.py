#!/usr/bin/python3

"""Shared base runner for benchmarks that use partial-credit per question."""

import json
import logging
from typing import Any, Dict, List

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from benchmarks.lib.utils.base import BenchmarkRunner
from benchmarks.lib.utils.data_models import BenchmarkResult

logger = logging.getLogger(__name__)


class PartialCreditRunner(BenchmarkRunner):
    """Base runner that records per-question partial scores (0-100)."""

    CORRECTNESS_THRESHOLD = 70

    def score_response(self, question_data: Dict[str, Any], response: Any) -> int:
        """Return an integer score in [0, 100] for one response."""
        raise NotImplementedError

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        return self.score_response(question_data, response) >= self.CORRECTNESS_THRESHOLD

    def process_question(self, question: Dict) -> BenchmarkResult:
        question_data = json.loads(question["question_info_json"])
        question_id = question["question_id"]

        try:
            prompt, schema, context = self.prepare_prompt(question_data)
            response = unified_client.generate_chat(
                prompt=prompt, model=self.remote_model, json_schema=schema, context=context
            )

            model_payload = schema and response.structured_data or response.response_text
            score = self.score_response(question_data, model_payload)
            is_correct = score >= self.CORRECTNESS_THRESHOLD

            debug_info = self.build_debug_info(question_data, response, is_correct)
            if debug_info is None:
                debug_info = {}
            if "score" not in debug_info:
                debug_info["score"] = score
            if "correctness_threshold" not in debug_info:
                debug_info["correctness_threshold"] = self.CORRECTNESS_THRESHOLD

            return BenchmarkResult(
                question_id=question_id,
                score=score,
                eval_msec=int(response.usage.total_msec),
                debug_json=json.dumps(debug_info) if debug_info else None,
                thought_process=(
                    response.additional_thought if response.additional_thought else None
                ),
            )

        except OllamaTimeoutError as error:
            return self.handle_timeout(question_id, error)
        except Exception as error:
            logger.error("Error processing question %s: %s", question_id, error)
            return BenchmarkResult(
                question_id=question_id,
                score=0,
                eval_msec=0,
                debug_json=json.dumps({"error": str(error)}),
            )

    def calculate_score(self, results: List[BenchmarkResult]) -> int:
        if not results:
            return 0
        return int(round(sum(result.score for result in results) / len(results)))
