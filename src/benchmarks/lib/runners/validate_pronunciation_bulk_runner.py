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

    @staticmethod
    def _normalize_entry_ids(entries: Any) -> set[str]:
        """Extract normalized entry IDs from a response/expected entry list."""
        normalized_ids: set[str] = set()
        if not isinstance(entries, list):
            return normalized_ids
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_id = str(entry.get("entry_id", "")).strip().lower()
            if entry_id:
                normalized_ids.add(entry_id)
        return normalized_ids

    @classmethod
    def _score_from_entry_sets(
        cls,
        expected_wrong_ipa_entries: Any,
        expected_wrong_phonetic_entries: Any,
        actual_wrong_ipa_entries: Any,
        actual_wrong_phonetic_entries: Any,
    ) -> Tuple[int, Dict[str, Any]]:
        """Score according to missing-vs-extra rule for wrong-word extraction."""
        expected_wrong_ids = cls._normalize_entry_ids(expected_wrong_ipa_entries).union(
            cls._normalize_entry_ids(expected_wrong_phonetic_entries)
        )
        actual_wrong_ids = cls._normalize_entry_ids(actual_wrong_ipa_entries).union(
            cls._normalize_entry_ids(actual_wrong_phonetic_entries)
        )

        missing_ids = sorted(expected_wrong_ids - actual_wrong_ids)
        extra_ids = sorted(actual_wrong_ids - expected_wrong_ids)

        if missing_ids:
            return 0, {
                "expected_wrong_ids": sorted(expected_wrong_ids),
                "actual_wrong_ids": sorted(actual_wrong_ids),
                "missing_ids": missing_ids,
                "extra_ids": extra_ids,
                "missing_count": len(missing_ids),
                "extra_count": len(extra_ids),
            }

        if not extra_ids:
            score = 100
        else:
            score = max(0, 80 - (10 * len(extra_ids)))

        return score, {
            "expected_wrong_ids": sorted(expected_wrong_ids),
            "actual_wrong_ids": sorted(actual_wrong_ids),
            "missing_ids": missing_ids,
            "extra_ids": extra_ids,
            "missing_count": len(missing_ids),
            "extra_count": len(extra_ids),
        }

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
            wrong_ipa_entries = structured_data.get("wrong_ipa_entries", [])
            wrong_phonetic_entries = structured_data.get("wrong_phonetic_entries", [])

            score, scoring_breakdown = self._score_from_entry_sets(
                expected_wrong_ipa_entries=expected.get("wrong_ipa_entries", []),
                expected_wrong_phonetic_entries=expected.get("wrong_phonetic_entries", []),
                actual_wrong_ipa_entries=wrong_ipa_entries,
                actual_wrong_phonetic_entries=wrong_phonetic_entries,
            )
            is_correct = score == 100

            debug_info = {
                "response": {
                    "wrong_ipa_entries": wrong_ipa_entries,
                    "wrong_phonetic_entries": wrong_phonetic_entries,
                },
                "expected": expected,
                "scoring": scoring_breakdown,
                "is_correct": is_correct,
                "score": score,
            }

            return BenchmarkResult(
                question_id=question_id,
                score=score,
                eval_msec=elapsed_msec,
                debug_json=json.dumps(debug_info),
                cost_usd=response.usage.cost if response.usage else None,
                tokens_used=response.usage.total_tokens if response.usage else None,
                tokens_in=response.usage.tokens_in if response.usage else None,
                tokens_out=response.usage.tokens_out if response.usage else None,
            )

        except Exception as error:
            return BenchmarkResult(
                question_id=question_id,
                score=0,
                eval_msec=0,
                debug_json=json.dumps({"error": str(error)}),
            )
