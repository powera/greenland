#!/usr/bin/python3

"""Generator for multilingual noun synonym identification benchmark questions."""

import logging
import random
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

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0017_synonyms"
BENCHMARK_NAME = "Multilingual Synonym Identification"
BENCHMARK_DESCRIPTION = (
    "Tests whether a model can identify the correct synonym for a noun from a list of candidates"
    " across multiple languages."
)

benchmark(
    BENCHMARK_CODE,
    BENCHMARK_NAME,
    BENCHMARK_DESCRIPTION,
    default_num_questions=52,
    category="word processing",
)(__name__)


@generator(BENCHMARK_CODE)
class SynonymsGenerator(BenchmarkGenerator):
    """Generator for multilingual noun synonym identification questions."""

    def __init__(self, metadata: BenchmarkMetadata, session: Any = None) -> None:
        super().__init__(metadata, session)

        self.can_load_from_file = True
        self.can_generate_locally = False
        self.can_generate_with_llm = False
        self.questions_file_path = "samples.json"

    def _generate_from_file(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        samples = self.load_json_file("samples.json")

        for sample in samples:
            language_code = sample["language_code"]
            language_name = sample.get("language_name", language_code)
            concept = sample["concept"]
            word = sample["word"]
            candidates = list(sample["candidates"])
            synonym = sample["synonym"]
            difficulty = Difficulty(sample.get("difficulty", "medium"))
            category = sample.get("category", concept)

            random.shuffle(candidates)

            yield BenchmarkQuestion(
                question_text=(
                    f'Which of these words is a synonym of "{word}" in {language_name}:'
                    f" {', '.join(candidates)}"
                ),
                answer_type=AnswerType.JSON,
                correct_answer={"synonym": synonym},
                category=f"synonyms_{language_code.lower()}",
                difficulty=difficulty,
                choices=candidates,
                tags=[
                    "synonyms",
                    "identification",
                    f"lang:{language_code.lower()}",
                    f"concept:{concept}",
                    f"category:{category}",
                ],
                schema={
                    "type": "object",
                    "properties": {"synonym": {"type": "string"}},
                    "required": ["synonym"],
                },
                evaluation_criteria=EvaluationCriteria(
                    exact_match=True,
                    case_sensitive=False,
                ),
            )
