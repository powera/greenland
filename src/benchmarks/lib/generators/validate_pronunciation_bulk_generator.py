#!/usr/bin/python3

"""Generator for Bebras bulk IPA/phonetic verification benchmark."""

from typing import Any, Dict, Iterator, List

from benchmarks.lib.utils.base_generator import BenchmarkGenerator
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    Difficulty,
    EvaluationCriteria,
)

BENCHMARK_CODE = "0141_validate_pronunciation_bulk"


class ValidatePronunciationBulkGenerator(BenchmarkGenerator):
    """Generate batch pronunciation QA questions from curated sample lists."""

    def __init__(self, metadata: BenchmarkMetadata, session: Any = None) -> None:
        super().__init__(metadata, session)
        self.can_load_from_file = True
        self.can_generate_locally = False
        self.can_generate_with_llm = False
        self.questions_file_path = "samples.json"

    def _generate_from_file(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        samples: List[Dict[str, Any]] = self.load_json_file("samples.json")

        for sample in samples:
            case_id = sample["case_id"]
            entries = sample["entries"]
            wrong_words = sample["wrong_words"]

            difficulty = Difficulty.EASY if not wrong_words else Difficulty.MEDIUM
            if len(wrong_words) >= 4:
                difficulty = Difficulty.HARD

            yield BenchmarkQuestion(
                question_text=f"Bulk pronunciation QA case: {case_id}",
                answer_type=AnswerType.JSON,
                correct_answer={
                    "inputs": {"entries": entries},
                    "expected": {"wrong_words": wrong_words},
                },
                category="agent_regression_pronunciation",
                difficulty=difficulty,
                tags=[
                    "agent_benchmark",
                    "bebras",
                    "pronunciation",
                    "ipa",
                    f"case:{case_id}",
                ],
                evaluation_criteria=EvaluationCriteria(
                    exact_match=True,
                    case_sensitive=False,
                    required_fields=["wrong_words"],
                ),
            )
