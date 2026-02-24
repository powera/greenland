#!/usr/bin/python3

"""Generator for 0154 food category classification benchmark."""

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


class FoodCategoryClassificationGenerator(BenchmarkGenerator):
    """Generate food category multiple-choice questions from seed data."""

    def __init__(self, metadata: BenchmarkMetadata, session=None):
        super().__init__(metadata, session)
        self.can_load_from_file = True
        self.strategy_order = ["file"]

    def _load_items(self) -> List[dict]:
        data = self.load_json_file("food_items.json")
        if not isinstance(data, list):
            raise ValueError("food_items.json must contain a JSON array")
        return data

    def _generate_from_file(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        items = self._load_items()
        random.shuffle(items)
        categories = sorted({entry["category"] for entry in items})

        for entry in items:
            food = entry["food"].strip()
            category = entry["category"].strip()

            decoys = [c for c in categories if c != category]
            sampled = random.sample(decoys, k=min(3, len(decoys)))
            choices = [category] + sampled
            random.shuffle(choices)

            yield BenchmarkQuestion(
                question_text=f"Which category best fits '{food}'?",
                answer_type=AnswerType.MULTIPLE_CHOICE,
                correct_answer=category,
                choices=choices,
                category="food",
                difficulty=Difficulty(entry.get("difficulty", "easy")),
                tags=["knowledge", "food", "classification"],
                evaluation_criteria=EvaluationCriteria(exact_match=True, case_sensitive=False),
            )
