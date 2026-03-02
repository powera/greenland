#!/usr/bin/python3

"""Generators for Python coding benchmarks 0301-0305."""

from typing import Any, Dict, Iterator

from benchmarks.lib.utils.base import BenchmarkGenerator
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    Difficulty,
    EvaluationCriteria,
)
from benchmarks.lib.utils.factory import generator, register_benchmark_metadata


class _PythonCodingGeneratorBase(BenchmarkGenerator):
    """Shared file-backed generator for Python coding benchmarks."""

    PROMPT_FILE: str = ""

    def __init__(self, metadata: BenchmarkMetadata, session=None):
        super().__init__(metadata, session)
        self.can_load_from_file = True
        self.can_generate_locally = False
        self.can_generate_with_llm = False
        self.strategy_order = ["file"]

    def _load_prompt(self) -> str:
        with open(self.PROMPT_FILE, "r", encoding="utf-8") as prompt_file:
            return prompt_file.read().strip()

    def _generate_from_file(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        samples = self.load_json_file("samples.json")
        prompt_text = self._load_prompt()

        for sample in samples:
            question_body = sample["question"].strip()
            question_text = f"{prompt_text}\n\nTask:\n{question_body}"

            yield BenchmarkQuestion(
                question_text=question_text,
                answer_type=AnswerType.FREE_TEXT,
                correct_answer=sample["correct_answer"],
                category="coding",
                difficulty=Difficulty.MEDIUM,
                tags=["python", "coding", "security"],
                evaluation_criteria=EvaluationCriteria(exact_match=False),
            )


register_benchmark_metadata(
    BenchmarkMetadata(
        code="0301_python_hello_world",
        name="Python Hello World Function",
        description="Write a Python 3.12 function that prints Hello world.",
        default_num_questions=1,
        category="coding",
    )
)


@generator("0301_python_hello_world")
class PythonHelloWorldGenerator(_PythonCodingGeneratorBase):
    """Generator for benchmark 0301."""

    PROMPT_FILE = "prompts/benchmarks/0301_python_hello_world.txt"


register_benchmark_metadata(
    BenchmarkMetadata(
        code="0302_python_gcd",
        name="Python GCD With Validation",
        description="Write a Python 3.12 function for GCD with invalid-input exceptions.",
        default_num_questions=1,
        category="coding",
    )
)


@generator("0302_python_gcd")
class PythonGCDGenerator(_PythonCodingGeneratorBase):
    """Generator for benchmark 0302."""

    PROMPT_FILE = "prompts/benchmarks/0302_python_gcd.txt"


register_benchmark_metadata(
    BenchmarkMetadata(
        code="0303_python_letter_count",
        name="Python Letter Count in String",
        description="Count occurrences of a target letter in a string.",
        default_num_questions=1,
        category="coding",
    )
)


@generator("0303_python_letter_count")
class PythonLetterCountGenerator(_PythonCodingGeneratorBase):
    """Generator for benchmark 0303."""

    PROMPT_FILE = "prompts/benchmarks/0303_python_letter_count.txt"


register_benchmark_metadata(
    BenchmarkMetadata(
        code="0304_python_coin_change",
        name="Python Minimum Coin Change",
        description="Compute minimum number of coins to make a target amount.",
        default_num_questions=1,
        category="coding",
    )
)


@generator("0304_python_coin_change")
class PythonCoinChangeGenerator(_PythonCodingGeneratorBase):
    """Generator for benchmark 0304."""

    PROMPT_FILE = "prompts/benchmarks/0304_python_coin_change.txt"


register_benchmark_metadata(
    BenchmarkMetadata(
        code="0305_python_prime_factorization",
        name="Python Prime Factorization",
        description="Return the prime factorization of a positive integer.",
        default_num_questions=1,
        category="coding",
    )
)


@generator("0305_python_prime_factorization")
class PythonPrimeFactorizationGenerator(_PythonCodingGeneratorBase):
    """Generator for benchmark 0305."""

    PROMPT_FILE = "prompts/benchmarks/0305_python_prime_factorization.txt"
