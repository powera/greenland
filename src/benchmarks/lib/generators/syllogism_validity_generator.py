#!/usr/bin/python3

"""Generator for 0152 syllogism validity benchmark."""

import random
from typing import Iterator, List

from benchmarks.lib.utils.base import BenchmarkGenerator
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    Difficulty,
    EvaluationCriteria,
)


class SyllogismValidityGenerator(BenchmarkGenerator):
    """Generate syllogism validity multiple-choice questions from local seed data."""

    def __init__(self, metadata: BenchmarkMetadata, session=None):
        super().__init__(metadata, session)
        self.can_load_from_file = True
        self.strategy_order = ["file"]

    def _load_seed_examples(self) -> List[dict]:
        data = self.load_json_file("syllogisms.json")
        if not isinstance(data, list):
            raise ValueError("syllogisms.json must contain a JSON array")
        return data

    def _generate_from_file(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        examples = self._load_seed_examples()
        random.shuffle(examples)

        for example in examples:
            p1 = example["premise_1"].strip()
            p2 = example["premise_2"].strip()
            conclusion = example["conclusion"].strip()
            is_valid = bool(example["is_valid"])

            question_text = (
                "Evaluate this syllogism:\n"
                f"Premise 1: {p1}\n"
                f"Premise 2: {p2}\n"
                f"Conclusion: {conclusion}\n\n"
                "Is the conclusion logically valid given the premises?"
            )

            yield BenchmarkQuestion(
                question_text=question_text,
                answer_type=AnswerType.MULTIPLE_CHOICE,
                correct_answer="Valid" if is_valid else "Invalid",
                choices=["Valid", "Invalid"],
                category="logic",
                difficulty=Difficulty(example.get("difficulty", "medium")),
                tags=["knowledge", "logic", "syllogism"],
                evaluation_criteria=EvaluationCriteria(exact_match=True, case_sensitive=False),
            )
