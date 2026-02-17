#!/usr/bin/python3

"""Runner for multilingual sentence decomposition benchmark."""

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from benchmarks.lib.utils.base import BenchmarkRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata, BenchmarkResult
from benchmarks.lib.utils.factory import runner

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@runner("0062_sentence_decomposition")
class SentenceDecompositionRunner(BenchmarkRunner):
    """Runner for sentence decomposition benchmark tests."""

    # A reasonably strict bar while allowing minor annotation mismatch.
    CORRECTNESS_THRESHOLD = 70

    WORD_FIELD_WEIGHTS = {
        "position": 0.05,
        "role": 0.20,
        "english_gloss": 0.15,
        "surface_form": 0.25,
        "grammatical_form": 0.15,
        "lemma_guid": 0.10,
        "lemma": 0.10,
    }

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
        words: List[Dict[str, Any]] = [row for row in normalized.get("words", []) if isinstance(row, dict)]
        words_sorted = sorted(words, key=lambda row: row.get("position", 0))
        normalized["words"] = words_sorted
        normalized["word_count"] = len(words_sorted)
        return normalized

    def _score_word(self, expected_word: Dict[str, Any], model_word: Dict[str, Any]) -> float:
        score = 0.0
        total = sum(self.WORD_FIELD_WEIGHTS.values())
        if total <= 0:
            return 0.0

        for field, weight in self.WORD_FIELD_WEIGHTS.items():
            expected_value = expected_word.get(field)
            model_value = model_word.get(field)
            if expected_value == model_value:
                score += weight

        return score / total

    def _score_language_entry(self, expected: Dict[str, Any], model: Dict[str, Any]) -> float:
        score = 0.0

        # Require target language to match exactly.
        if expected.get("language_code") != model.get("language_code"):
            return 0.0

        # 15% translation fidelity.
        if expected.get("translation") == model.get("translation"):
            score += 0.15

        expected_words = [w for w in expected.get("words", []) if isinstance(w, dict)]
        model_by_pos = {
            word.get("position"): word
            for word in model.get("words", [])
            if isinstance(word, dict) and word.get("position") is not None
        }

        # 5% structural token count.
        if len(expected_words) == len(model.get("words", [])):
            score += 0.05

        # 80% token-level metadata accuracy.
        if expected_words:
            token_score = 0.0
            for expected_word in expected_words:
                position = expected_word.get("position")
                model_word = model_by_pos.get(position)
                if model_word is not None:
                    token_score += self._score_word(expected_word, model_word)
            score += 0.80 * (token_score / len(expected_words))

        return min(max(score, 0.0), 1.0)

    def score_response(self, question_data: Dict, response: Any) -> int:
        if not isinstance(response, dict):
            return 0

        expected = question_data.get("correct_answer", {})
        if not isinstance(expected, dict):
            return 0

        expected_languages = expected.get("languages", [])
        model_languages = response.get("languages", [])
        if not isinstance(expected_languages, list) or not isinstance(model_languages, list):
            return 0
        if len(expected_languages) != 1 or len(model_languages) != 1:
            return 0

        expected_entry = self._normalize_language_entry(expected_languages[0])
        model_entry = self._normalize_language_entry(model_languages[0])

        return int(round(self._score_language_entry(expected_entry, model_entry) * 100))

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
            debug_info["score"] = score
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

    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        if hasattr(response, "structured_data") and response.structured_data:
            model_answer = response.structured_data
        else:
            model_answer = response.response_text

        return {
            "prompt": question_data.get("question_text", ""),
            # Keep legacy keys so existing run views can render reliably.
            "response": model_answer,
            "expected": question_data.get("correct_answer"),
            # Also include descriptive keys used by newer runners.
            "model_answer": model_answer,
            "expected_answer": question_data.get("correct_answer"),
            "is_correct": is_correct,
        }
