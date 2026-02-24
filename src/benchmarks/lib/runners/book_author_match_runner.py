#!/usr/bin/python3

"""Runner for 0153 book-author matching benchmark."""

from benchmarks.lib.runners.knowledge_multiple_choice_runner import KnowledgeMultipleChoiceRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata


class BookAuthorMatchRunner(KnowledgeMultipleChoiceRunner):
    def __init__(self, model: str, metadata: BenchmarkMetadata):
        super().__init__(
            model,
            metadata,
            context="You are taking a literature quiz. Select the correct author for each book.",
        )
