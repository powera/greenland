#!/usr/bin/python3

"""Runner for validate_definition agent benchmark.

Calls validate_definition() from wordfreq/tools/llm_validators.py directly
with the model under test, then scores the result against the expected
is_valid boolean from the sample. No DB access is required.
"""

import json
import logging
import time
from typing import Any, Dict, Optional, Tuple

from benchmarks.lib.utils.base_runner import BenchmarkRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata, BenchmarkResult
from wordfreq.tools.llm_validators import validate_definition

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0131_validate_definition"


class ValidateDefinitionRunner(BenchmarkRunner):
    """Runner for the validate_definition agent benchmark.

    Overrides process_question() to call validate_definition() directly
    rather than prompting the model through unified_client. This tests
    the full agent function end-to-end, including its internal prompt.
    """

    def process_question(self, question: Dict[str, Any]) -> BenchmarkResult:
        question_data = json.loads(question["question_info_json"])
        question_id = question["question_id"]
        correct_answer = question_data["correct_answer"]
        inputs: Dict[str, str] = correct_answer["inputs"]
        expected: Dict[str, Any] = correct_answer["expected"]

        try:
            start_time = time.time()
            result = validate_definition(
                word=inputs["word"],
                definition=inputs["definition"],
                pos_type=inputs["pos_type"],
                model=self.remote_model,
            )
            elapsed_msec = int((time.time() - start_time) * 1000)

            actual_is_valid = result.get("is_valid")
            expected_is_valid = expected["is_valid"]

            # None means the validator call failed; score 0 regardless of expected.
            # With a valid response actual_is_valid is bool, so None != bool is always False.
            is_fallback = actual_is_valid is None
            is_correct = (not is_fallback) and (actual_is_valid == expected_is_valid)
            score = 100 if is_correct else 0

            debug_info = {
                "response": result,
                "expected": expected,
                "is_correct": is_correct,
                "word": inputs["word"],
                "pos_type": inputs["pos_type"],
                "definition_preview": inputs["definition"][:80],
                "fallback_detected": is_fallback,
            }

            logger.info(
                "Question %s: word='%s', expected_is_valid=%s, actual_is_valid=%s, score=%d",
                question_id,
                inputs["word"],
                expected_is_valid,
                actual_is_valid,
                score,
            )

            return BenchmarkResult(
                question_id=question_id,
                score=score,
                eval_msec=elapsed_msec,
                debug_json=json.dumps(debug_info),
            )

        except Exception as e:
            logger.error("Error processing question %s: %s", question_id, e)
            return BenchmarkResult(
                question_id=question_id,
                score=0,
                eval_msec=0,
                debug_json=json.dumps({"error": str(e)}),
            )

    def prepare_prompt(
        self, question_data: Dict[str, Any]
    ) -> Tuple[str, Optional[Dict[str, Any]], Optional[str]]:
        # Not used: process_question() is overridden to call the agent function directly.
        return "", None, None
