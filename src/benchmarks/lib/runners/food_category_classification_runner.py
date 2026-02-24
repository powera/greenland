#!/usr/bin/python3

"""Runner for 0154 food category classification benchmark."""

from benchmarks.lib.runners.knowledge_multiple_choice_runner import KnowledgeMultipleChoiceRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata


class FoodCategoryClassificationRunner(KnowledgeMultipleChoiceRunner):
    def __init__(self, model: str, metadata: BenchmarkMetadata):
        super().__init__(
            model,
            metadata,
            context="You are taking a food knowledge quiz. Pick the best category for each food item.",
        )
