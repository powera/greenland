#!/usr/bin/python3

"""Runner for 0152 syllogism validity benchmark."""

from benchmarks.lib.runners.knowledge_multiple_choice_runner import KnowledgeMultipleChoiceRunner
from benchmarks.lib.utils.data_models import BenchmarkMetadata


class SyllogismValidityRunner(KnowledgeMultipleChoiceRunner):
    def __init__(self, model: str, metadata: BenchmarkMetadata):
        super().__init__(
            model,
            metadata,
            context="You are taking a logic test. Choose whether each syllogism is valid or invalid.",
        )
