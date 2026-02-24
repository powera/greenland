#!/usr/bin/python3

"""Generator for multilingual noun synonym benchmark questions."""

import logging
from typing import Any, Iterator

from benchmarks.lib.utils.base import BenchmarkGenerator
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    Difficulty,
    EvaluationCriteria,
)
from benchmarks.lib.utils.factory import benchmark, generator
from storage.backend.config import DataSourceConfig
from words import build_synonyms_prompt

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0111_synonyms"
BENCHMARK_NAME = "Multilingual Synonym Generation"
BENCHMARK_DESCRIPTION = (
    "Tests whether a model can generate synonyms for common nouns across multiple languages."
)

benchmark(
    BENCHMARK_CODE,
    BENCHMARK_NAME,
    BENCHMARK_DESCRIPTION,
    default_num_questions=64,
    category="word processing",
)(__name__)


@generator(BENCHMARK_CODE)
class SynonymsGenerator(BenchmarkGenerator):
    """Generator for multilingual noun synonym questions."""

    def __init__(self, metadata: BenchmarkMetadata, session=None):
        super().__init__(metadata, session)

        self.can_load_from_file = True
        self.can_generate_locally = False
        self.can_generate_with_llm = False
        self.questions_file_path = "samples.json"

    def _generate_from_file(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        samples = self.load_json_file(self.questions_file_path)

        for sample in samples:
            language_code = sample["language_code"]
            concept = sample["concept"]
            mandatory_synonyms = sample.get("mandatory_synonyms", [])
            optional_synonyms = sample.get("optional_synonyms", [])

            prompt_word = sample.get("word", concept)
            benchmark_config = kwargs.get("config")
            if benchmark_config is None:
                benchmark_config = DataSourceConfig()

            yield BenchmarkQuestion(
                question_text=build_synonyms_prompt(language_code, prompt_word, benchmark_config),
                answer_type=AnswerType.JSON,
                correct_answer={
                    "mandatory_synonyms": mandatory_synonyms,
                    "optional_synonyms": optional_synonyms,
                },
                category=f"synonyms_{language_code.lower()}",
                difficulty=Difficulty.MEDIUM,
                tags=[
                    "synonyms",
                    "generation",
                    f"lang:{language_code.lower()}",
                    f"concept:{concept}",
                ],
                schema={
                    "type": "object",
                    "properties": {
                        "synonyms": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 0,
                        }
                    },
                    "required": ["synonyms"],
                },
                evaluation_criteria=EvaluationCriteria(
                    exact_match=False,
                    case_sensitive=False,
                    required_fields=["synonyms"],
                ),
            )
