#!/usr/bin/python3

"""Runner for 0155 historical event year benchmark."""

from benchmarks.lib.runners.knowledge_multiple_choice_runner import KnowledgeMultipleChoiceRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata


class HistoricalEventYearRunner(KnowledgeMultipleChoiceRunner):
    def __init__(self, model: str, metadata: BenchmarkMetadata):
        super().__init__(
            model,
            metadata,
            context="You are taking a history quiz. Select the correct year for each event.",
        )
