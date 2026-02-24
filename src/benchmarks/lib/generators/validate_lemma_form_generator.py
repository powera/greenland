#!/usr/bin/python3

"""Generator for validate_lemma_form agent benchmark questions.

Tests the lokys agent's validate_lemma_form() LLM function from
wordfreq/tools/llm_validators.py, which checks whether a word is in its
correct base/lemma form and suggests the correct form when it is not.
"""

import logging
from typing import Any, Iterator

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

BENCHMARK_CODE = "0130_validate_lemma_form"


class ValidateLemmaFormGenerator(BenchmarkGenerator):
    """Generator for validate_lemma_form benchmark questions.

    Loads curated (word, pos_type) pairs from samples.json and produces
    BenchmarkQuestion objects whose correct_answer encodes both the
    function inputs and the expected output, so the runner can call
    validate_lemma_form() directly without touching the DB.
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
            word = sample["word"]
            pos_type = sample["pos_type"]
            is_lemma = sample["is_lemma"]
            suggested_lemma = sample.get("suggested_lemma", word)

            difficulty = Difficulty.EASY if is_lemma else Difficulty.MEDIUM

            yield BenchmarkQuestion(
                question_text=f"Is '{word}' ({pos_type}) already in lemma/base form?",
                answer_type=AnswerType.JSON,
                correct_answer={
                    "inputs": {"word": word, "pos_type": pos_type},
                    "expected": {"is_lemma": is_lemma, "suggested_lemma": suggested_lemma},
                },
                category=f"validate_lemma_form_{pos_type}",
                difficulty=difficulty,
                tags=[
                    "agent_benchmark",
                    "lokys",
                    "lemma_form",
                    f"pos:{pos_type}",
                    f"is_lemma:{str(is_lemma).lower()}",
                ],
                evaluation_criteria=EvaluationCriteria(
                    exact_match=True,
                    case_sensitive=False,
                    required_fields=["is_lemma"],
                ),
            )
