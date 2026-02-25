#!/usr/bin/python3

"""Generator for simple arithmetic benchmark questions."""

import logging
import random
from typing import Any, Iterator, Optional

from benchmarks.lib.utils.base_generator import BenchmarkGenerator
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    Difficulty,
    EvaluationCriteria,
)
from benchmarks.lib.utils.factory import benchmark, generator

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0021_simple_arithmetic"

benchmark(
    BENCHMARK_CODE,
    "Simple Arithmetic",
    "Tests ability to perform basic arithmetic: addition, subtraction, multiplication, and division.",
    category="simple math",
)(__name__)


@generator(BENCHMARK_CODE)
class SimpleArithmeticGenerator(BenchmarkGenerator):
    """Generator for simple arithmetic benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session: Optional[Any] = None) -> None:
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)

        self.can_load_from_file = False
        self.can_generate_locally = True
        self.can_generate_with_llm = False

    def _generate_locally(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        """
        Generate simple arithmetic questions.

        Yields:
            BenchmarkQuestion objects
        """
        while True:
            op = random.choice(["+", "-", "*", "/"])

            if op == "+":
                a = random.randint(1, 100)
                b = random.randint(1, 100)
                answer: float = float(a + b)
                difficulty = Difficulty.EASY if a + b < 50 else Difficulty.MEDIUM
                question_text = f"What is {a} + {b}?"
                tags = ["arithmetic", "addition"]

            elif op == "-":
                a = random.randint(1, 100)
                b = random.randint(0, a)
                answer = float(a - b)
                difficulty = Difficulty.EASY if a < 50 else Difficulty.MEDIUM
                question_text = f"What is {a} - {b}?"
                tags = ["arithmetic", "subtraction"]

            elif op == "*":
                a = random.randint(2, 12)
                b = random.randint(2, 12)
                answer = float(a * b)
                difficulty = Difficulty.EASY if a * b < 50 else Difficulty.MEDIUM
                question_text = f"What is {a} × {b}?"
                tags = ["arithmetic", "multiplication"]

            else:  # /
                b = random.randint(2, 12)
                quotient = random.randint(1, 20)
                a = b * quotient
                answer = float(quotient)
                difficulty = Difficulty.MEDIUM
                question_text = f"What is {a} ÷ {b}?"
                tags = ["arithmetic", "division"]

            yield BenchmarkQuestion(
                question_text=question_text,
                answer_type=AnswerType.NUMERIC,
                correct_answer=answer,
                category="simple_arithmetic",
                difficulty=difficulty,
                tags=tags,
                evaluation_criteria=EvaluationCriteria(exact_match=True, tolerance=0.0),
            )
