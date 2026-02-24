#!/usr/bin/python3

"""Generator for validate_definition agent benchmark questions.

Tests the lokys agent's validate_definition() LLM function from
wordfreq/tools/llm_validators.py, which checks whether a definition is
well-formed and appropriate for a given word and part of speech.
"""

import logging
from typing import Any, Iterator, List

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

BENCHMARK_CODE = "0131_validate_definition"


class ValidateDefinitionGenerator(BenchmarkGenerator):
    """Generator for validate_definition benchmark questions.

    Loads curated (word, definition, pos_type) triples from samples.json
    and produces BenchmarkQuestion objects whose correct_answer encodes both
    the function inputs and expected output, so the runner can call
    validate_definition() directly without touching the DB.
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
            definition = sample["definition"]
            is_valid = sample["is_valid"]
            expected_issues: List[str] = sample.get("expected_issues", [])

            difficulty = Difficulty.EASY if is_valid else Difficulty.MEDIUM

            # Truncate definition in question_text for readability
            def_preview = definition[:60] + "..." if len(definition) > 60 else definition
            question_text = f"Is the definition \"{def_preview}\" valid for '{word}' ({pos_type})?"

            yield BenchmarkQuestion(
                question_text=question_text,
                answer_type=AnswerType.JSON,
                correct_answer={
                    "inputs": {
                        "word": word,
                        "pos_type": pos_type,
                        "definition": definition,
                    },
                    "expected": {
                        "is_valid": is_valid,
                        "expected_issues": expected_issues,
                    },
                },
                category=f"validate_definition_{pos_type}",
                difficulty=difficulty,
                tags=[
                    "agent_benchmark",
                    "lokys",
                    "definition",
                    f"pos:{pos_type}",
                    f"is_valid:{str(is_valid).lower()}",
                ],
                evaluation_criteria=EvaluationCriteria(
                    exact_match=True,
                    case_sensitive=False,
                    required_fields=["is_valid"],
                ),
            )
