#!/usr/bin/python3

"""Generator for validate_all_translations_for_word agent benchmark questions.

Tests the voras agent's validate_all_translations_for_word() LLM function
from wordfreq/tools/llm_validators.py, which validates whether multilingual
translations of an English word are semantically correct and in lemma form.
"""

import logging
from typing import Any, Dict, Iterator

from benchmarks.lib.utils.base_generator import BenchmarkGenerator
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    Difficulty,
    EvaluationCriteria,
)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0132_validate_translation"


class ValidateTranslationGenerator(BenchmarkGenerator):
    """Generator for validate_all_translations_for_word benchmark questions.

    Loads curated (english_word, translations, pos_type) records from
    samples.json. Each record specifies translations in multiple language codes
    and the expected per-language validation results, so the runner can call
    validate_all_translations_for_word() directly without DB access.
    """

    def __init__(self, metadata: BenchmarkMetadata, session: Any = None) -> None:
        super().__init__(metadata, session)
        self.can_load_from_file = True
        self.can_generate_locally = False
        self.can_generate_with_llm = False
        self.questions_file_path = "samples.json"

    def _generate_from_file(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        samples = self.load_json_file("samples.json")

        for sample in samples:
            english_word = sample["english_word"]
            pos_type = sample["pos_type"]
            translations: Dict[str, str] = sample["translations"]
            expected: Dict[str, Dict[str, bool]] = sample["expected"]

            # Determine difficulty based on whether any translation is wrong
            has_errors = any(
                not v.get("is_correct", True) or not v.get("is_lemma_form", True)
                for v in expected.values()
            )
            difficulty = Difficulty.HARD if has_errors else Difficulty.MEDIUM

            lang_summary = ", ".join(f"{lc}:{t}" for lc, t in translations.items())
            question_text = (
                f"Validate translations of '{english_word}' ({pos_type}): {lang_summary}"
            )

            yield BenchmarkQuestion(
                question_text=question_text,
                answer_type=AnswerType.JSON,
                correct_answer={
                    "inputs": {
                        "english_word": english_word,
                        "pos_type": pos_type,
                        "translations": translations,
                    },
                    "expected": expected,
                },
                category=f"validate_translation_{pos_type}",
                difficulty=difficulty,
                tags=[
                    "agent_benchmark",
                    "voras",
                    "translation_validation",
                    f"pos:{pos_type}",
                    f"languages:{','.join(sorted(translations.keys()))}",
                ],
                evaluation_criteria=EvaluationCriteria(
                    exact_match=False,
                    case_sensitive=False,
                    required_fields=list(expected.keys()),
                ),
            )
