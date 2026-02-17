#!/usr/bin/python3

"""Runner for multilingual verb-form production benchmark."""

import logging
from typing import Any, Dict, List, Optional, Tuple

from benchmarks.lib.runners.partial_credit_runner import PartialCreditRunner
from benchmarks.lib.utils.factory import runner

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PERSON_SLOTS = ["1s", "2s", "3s", "1p", "2p", "3p"]
TENSES = ["present", "past", "future"]
@runner("0121_verb_forms")
class VerbFormsRunner(PartialCreditRunner):
    """Runner for verb forms benchmark tests."""

    CORRECTNESS_THRESHOLD = 70

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        prompt = question_data["question_text"]
        schema = question_data.get("schema")
        context = (
            "You are a linguistics assistant. Return valid JSON only. "
            "Do not omit required person-tense slots."
        )
        return prompt, schema, context

    def _has_nonempty_string(self, value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def _normalize(self, value: Any) -> str:
        return value.strip().lower() if isinstance(value, str) else ""

    def _is_structurally_valid(self, question_data: Dict, response: Any) -> bool:
        expected = question_data.get("correct_answer", {})

        if not isinstance(response, dict):
            return False

        if response.get("language_code") != expected.get("language_code"):
            return False

        forms = response.get("forms")
        if not isinstance(forms, dict):
            return False

        for tense in TENSES:
            tense_forms = forms.get(tense)
            if not isinstance(tense_forms, dict):
                return False
            for person in PERSON_SLOTS:
                if not self._has_nonempty_string(tense_forms.get(person)):
                    return False

        extras = response.get("extra_forms")
        if not isinstance(extras, dict):
            return False

        required_extra_forms: List[str] = expected.get("required_extra_forms", [])
        for key in required_extra_forms:
            if not self._has_nonempty_string(extras.get(key)):
                return False

        if not self._has_nonempty_string(response.get("lemma")):
            return False

        return True

    def _has_gold_forms(self, expected: Dict[str, Any]) -> bool:
        forms = expected.get("forms")
        extras = expected.get("extra_forms")
        return isinstance(forms, dict) and isinstance(extras, dict)

    def score_response(self, question_data: Dict, response: Any) -> int:
        """Score response with weighted exactness.

        Formula:
        - base = (percent exactly right) * 80
        - bonus = +20 if every scored form is exactly right
        """
        expected = question_data.get("correct_answer", {})

        if not self._is_structurally_valid(question_data, response):
            return 0

        if not self._has_gold_forms(expected):
            # Backward-compatible behavior for datasets that only validate structure.
            return 100

        total_slots = 0
        exact_matches = 0

        expected_forms = expected.get("forms", {})
        model_forms = response.get("forms", {}) if isinstance(response, dict) else {}

        for tense in TENSES:
            expected_tense = expected_forms.get(tense, {})
            model_tense = model_forms.get(tense, {}) if isinstance(model_forms, dict) else {}
            for person in PERSON_SLOTS:
                expected_value = expected_tense.get(person)
                if not isinstance(expected_value, str):
                    continue
                total_slots += 1
                if self._normalize(model_tense.get(person)) == self._normalize(expected_value):
                    exact_matches += 1

        expected_extras = expected.get("extra_forms", {})
        model_extras = response.get("extra_forms", {}) if isinstance(response, dict) else {}
        for key, expected_value in expected_extras.items():
            if not isinstance(expected_value, str):
                continue
            total_slots += 1
            if self._normalize(model_extras.get(key)) == self._normalize(expected_value):
                exact_matches += 1

        if total_slots == 0:
            return 0

        percent_exact = exact_matches / total_slots
        score = (percent_exact * 80.0) + (20.0 if exact_matches == total_slots else 0.0)
        return int(round(score))


    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict[str, Any]:
        if hasattr(response, "structured_data") and response.structured_data:
            model_answer = response.structured_data
        else:
            model_answer = getattr(response, "response_text", response)

        score = self.score_response(question_data, model_answer)

        return {
            "prompt": question_data.get("question_text", ""),
            "model_answer": model_answer,
            "expected_answer": question_data.get("correct_answer", {}),
            "score": score,
            "correctness_threshold": self.CORRECTNESS_THRESHOLD,
            "is_correct": is_correct,
        }
