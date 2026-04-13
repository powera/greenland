#!/usr/bin/python3

"""Runner for Bebras bulk IPA/phonetic verification benchmark."""

import json
import time
from typing import Any, Dict, Optional, Tuple

from agents.bebras.verification import (
    build_bulk_pronunciation_verification_context,
    build_bulk_pronunciation_verification_prompt,
    build_bulk_pronunciation_verification_schema,
)
from benchmarks.lib.utils.base_runner import BenchmarkRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata, BenchmarkResult
from clients import unified_client

BENCHMARK_CODE = "0141_validate_pronunciation_bulk"


class ValidatePronunciationBulkRunner(BenchmarkRunner):
    """Run pronunciation-list validation and score wrong-word extraction accuracy."""

    def prepare_prompt(
        self, question_data: Dict[str, Any]
    ) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
        entries = question_data["correct_answer"]["inputs"]["entries"]
        prompt = build_bulk_pronunciation_verification_prompt(entries)
        schema = build_bulk_pronunciation_verification_schema()
        context = build_bulk_pronunciation_verification_context()
        return prompt, schema, context

    def process_question(self, question: Dict[str, Any]) -> BenchmarkResult:
        question_data = json.loads(question["question_info_json"])
        question_id = question["question_id"]
        expected = question_data["correct_answer"]["expected"]

        prompt, schema, context = self.prepare_prompt(question_data)

        try:
            start_time = time.time()
            response = unified_client.generate_chat(
                prompt=prompt,
                model=self.remote_model,
                json_schema=schema,
                context=context,
            )
            elapsed_msec = int((time.time() - start_time) * 1000)

            structured_data = response.structured_data or {}
            wrong_words = structured_data.get("wrong_words", [])
            if not isinstance(wrong_words, list):
                wrong_words = []

            normalized_actual = sorted(str(word).strip().lower() for word in wrong_words)
            normalized_expected = sorted(
                str(word).strip().lower() for word in expected["wrong_words"]
            )

            is_correct = normalized_actual == normalized_expected
            score = 100 if is_correct else 0

            debug_info = {
                "response": {"wrong_words": wrong_words},
                "expected": expected,
                "normalized_actual": normalized_actual,
                "normalized_expected": normalized_expected,
                "is_correct": is_correct,
            }

            return BenchmarkResult(
                question_id=question_id,
                score=score,
                eval_msec=elapsed_msec,
                debug_json=json.dumps(debug_info),
            )

        except Exception as error:
            return BenchmarkResult(
                question_id=question_id,
                score=0,
                eval_msec=0,
                debug_json=json.dumps({"error": str(error)}),
            )
