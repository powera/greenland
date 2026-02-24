#!/usr/bin/python3

"""Runner for validate_all_translations_for_word agent benchmark.

Calls validate_all_translations_for_word() from wordfreq/tools/llm_validators.py
directly with the model under test, then scores the result using partial credit
based on how many per-language is_correct/is_lemma_form booleans match expected.
No DB access is required.
"""

import json
import logging
from typing import Any, Dict, Optional, Tuple

from benchmarks.lib.utils.base_runner import BenchmarkRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata, BenchmarkResult
from wordfreq.tools.llm_validators import validate_all_translations_for_word

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0132_validate_translation"


class ValidateTranslationRunner(BenchmarkRunner):
    """Runner for the validate_all_translations_for_word agent benchmark.

    Overrides process_question() to call validate_all_translations_for_word()
    directly rather than prompting the model through unified_client. Uses partial
    credit scoring: for each expected language, is_correct and is_lemma_form are
    each worth one point; the final score is (matching / total) * 100.
    """

    def process_question(self, question: Dict[str, Any]) -> BenchmarkResult:
        question_data = json.loads(question["question_info_json"])
        question_id = question["question_id"]
        correct_answer = question_data["correct_answer"]
        inputs: Dict[str, Any] = correct_answer["inputs"]
        expected: Dict[str, Dict[str, bool]] = correct_answer["expected"]

        try:
            result = validate_all_translations_for_word(
                english_word=inputs["english_word"],
                translations=inputs["translations"],
                pos_type=inputs["pos_type"],
                model=self.remote_model,
            )

            # Partial credit: count matching boolean fields across all expected languages
            total_checks = 0
            matching_checks = 0
            per_language_debug: Dict[str, Any] = {}

            for lang_code, lang_expected in expected.items():
                lang_actual = result.get(lang_code, {})
                lang_debug: Dict[str, Any] = {}

                for field in ("is_correct", "is_lemma_form"):
                    if field in lang_expected:
                        total_checks += 1
                        expected_val = lang_expected[field]
                        actual_val = lang_actual.get(field)
                        matches = actual_val == expected_val
                        if matches:
                            matching_checks += 1
                        lang_debug[field] = {
                            "expected": expected_val,
                            "actual": actual_val,
                            "match": matches,
                        }

                lang_debug["suggested_translation"] = lang_actual.get("suggested_translation")
                per_language_debug[lang_code] = lang_debug

            score = int((matching_checks / total_checks) * 100) if total_checks > 0 else 0

            debug_info = {
                "english_word": inputs["english_word"],
                "pos_type": inputs["pos_type"],
                "total_checks": total_checks,
                "matching_checks": matching_checks,
                "score": score,
                "per_language": per_language_debug,
            }

            logger.info(
                "Question %s: word='%s', matched %d/%d checks, score=%d",
                question_id,
                inputs["english_word"],
                matching_checks,
                total_checks,
                score,
            )

            return BenchmarkResult(
                question_id=question_id,
                score=score,
                eval_msec=0,
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
