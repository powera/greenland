#!/usr/bin/python3

"""Runner for multilingual sentence decomposition benchmark."""

import logging
from typing import Any, Dict, List, Optional, Tuple

from benchmarks.lib.utils.base import BenchmarkRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata
from benchmarks.lib.utils.factory import runner

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@runner("0062_sentence_decomposition")
class SentenceDecompositionRunner(BenchmarkRunner):
    """Runner for sentence decomposition benchmark tests."""

    def __init__(self, model: str, metadata: BenchmarkMetadata):
        super().__init__(model, metadata)

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        prompt = question_data["question_text"]
        schema = question_data.get("schema")

        context = """
        You are a multilingual linguistics expert.
        Build a complete sentence decomposition for exactly one requested target language.

        Rules:
        - Keep tokens in order.
        - Keep positions zero-indexed.
        - word_count must equal the number of entries in words.
        - grammatical_form should capture language-specific inflectional detail when possible.
        - lemma should be the base form or 'No lemma' when not applicable.
        - Output only valid JSON matching the schema.
        - languages must contain exactly one entry.
        """

        return prompt, schema, context

    def _normalize(self, value: Any) -> Any:
        if isinstance(value, str):
            return " ".join(value.strip().lower().split())
        if isinstance(value, list):
            return [self._normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: self._normalize(val) for key, val in value.items()}
        return value

    def _normalize_language_entry(self, item: Dict[str, Any]) -> Dict[str, Any]:
        normalized = self._normalize(item)
        words: List[Dict[str, Any]] = normalized.get("words", [])
        words_sorted = sorted(words, key=lambda row: row.get("position", 0))
        normalized["words"] = words_sorted
        normalized["word_count"] = len(words_sorted)
        return normalized

    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        if not isinstance(response, dict):
            return False

        expected = question_data.get("correct_answer", {})
        if not isinstance(expected, dict):
            return False

        expected_languages = expected.get("languages", [])
        model_languages = response.get("languages", [])
        if not isinstance(expected_languages, list) or not isinstance(model_languages, list):
            return False

        expected_by_code = {
            item.get("language_code", "").lower(): self._normalize_language_entry(item)
            for item in expected_languages
        }
        model_by_code = {
            item.get("language_code", "").lower(): self._normalize_language_entry(item)
            for item in model_languages
            if isinstance(item, dict)
        }

        if set(expected_by_code.keys()) != set(model_by_code.keys()):
            return False

        for code, expected_entry in expected_by_code.items():
            if expected_entry != model_by_code.get(code):
                return False

        return True

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        if hasattr(response, "structured_data") and response.structured_data:
            model_answer = response.structured_data
        else:
            model_answer = response.response_text

        return {
            "prompt": question_data.get("question_text", ""),
            "model_answer": model_answer,
            "expected_answer": question_data.get("correct_answer"),
            "is_correct": is_correct,
        }
