#!/usr/bin/python3

"""Runner for multilingual verb-form production benchmark."""

import logging
from typing import Any, Dict, List, Optional, Tuple

from benchmarks.lib.utils.base import BenchmarkRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata
from benchmarks.lib.utils.factory import runner

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

PERSON_SLOTS = ["1s", "2s", "3s", "1p", "2p", "3p"]
TENSES = ["present", "past", "future"]


@runner("0121_verb_forms")
class VerbFormsRunner(BenchmarkRunner):
    """Runner for verb forms benchmark tests."""

    def __init__(self, model: str, metadata: BenchmarkMetadata):
        super().__init__(model, metadata)

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

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
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

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict[str, Any]:
        if hasattr(response, "structured_data") and response.structured_data:
            model_answer = response.structured_data
        else:
            model_answer = getattr(response, "response_text", response)

        return {
            "prompt": question_data.get("question_text", ""),
            "model_answer": model_answer,
            "expected_answer": question_data.get("correct_answer", {}),
            "is_correct": is_correct,
        }
