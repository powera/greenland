#!/usr/bin/python3

"""Generator for fractions and percentages benchmark questions."""

import logging
import random
from typing import Any, Iterator, List, Optional, Tuple

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

BENCHMARK_CODE = "0024_percentage_math"

benchmark(
    BENCHMARK_CODE,
    "Fractions and Percentages",
    "Tests ability to calculate percentages and fractions, including percent-of, fraction-of, and percent change.",
    category="simple math",
)(__name__)

# Common "clean" percentages that yield integer or simple decimal answers
_NICE_PERCENTAGES: List[int] = [5, 10, 15, 20, 25, 30, 40, 50, 60, 75, 80, 90]

# Fractions as (numerator, denominator) pairs
_NICE_FRACTIONS: List[Tuple[int, int]] = [
    (1, 2),
    (1, 3),
    (1, 4),
    (1, 5),
    (2, 3),
    (2, 5),
    (3, 4),
    (3, 5),
    (4, 5),
    (1, 8),
    (3, 8),
    (5, 8),
]

# Base values for percent-of questions (multiples of common denominators)
_PERCENT_BASES: List[int] = [20, 40, 50, 60, 80, 100, 120, 150, 200, 400, 500]

# Original values for percent-change questions
_CHANGE_ORIGINALS: List[int] = [50, 80, 100, 120, 150, 200, 250]
_CHANGE_PERCENTAGES: List[int] = [5, 10, 20, 25, 50]


@generator(BENCHMARK_CODE)
class PercentageMathGenerator(BenchmarkGenerator):
    """Generator for fractions and percentages benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session: Optional[Any] = None) -> None:
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)

        self.can_load_from_file = False
        self.can_generate_locally = True
        self.can_generate_with_llm = False

    def _generate_locally(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        """
        Generate fractions and percentages questions.

        Yields:
            BenchmarkQuestion objects
        """
        question_types = ["percent_of", "fraction_of", "percent_increase", "percent_decrease"]

        while True:
            question_type = random.choice(question_types)

            if question_type == "percent_of":
                pct = random.choice(_NICE_PERCENTAGES)
                base = random.choice(_PERCENT_BASES)
                answer = round(pct * base / 100, 2)
                question_text = f"What is {pct}% of {base}?"
                difficulty = Difficulty.EASY if pct in [50, 25, 10] else Difficulty.MEDIUM
                tags = ["percentage", "percent_of"]

            elif question_type == "fraction_of":
                num, den = random.choice(_NICE_FRACTIONS)
                # Choose a base that is cleanly divisible by the denominator
                multiplier = random.randint(2, 20)
                base = den * multiplier
                answer = float(num * multiplier)
                question_text = f"What is {num}/{den} of {base}?"
                difficulty = Difficulty.MEDIUM
                tags = ["fraction", "fraction_of"]

            elif question_type == "percent_increase":
                original = random.choice(_CHANGE_ORIGINALS)
                pct = random.choice(_CHANGE_PERCENTAGES)
                answer = round(original * (1 + pct / 100), 2)
                question_text = f"If {original} increases by {pct}%, what is the new value?"
                difficulty = Difficulty.MEDIUM
                tags = ["percentage", "percent_increase"]

            else:  # percent_decrease
                original = random.choice(_CHANGE_ORIGINALS)
                pct = random.choice(_CHANGE_PERCENTAGES)
                answer = round(original * (1 - pct / 100), 2)
                question_text = f"If {original} decreases by {pct}%, what is the new value?"
                difficulty = Difficulty.MEDIUM
                tags = ["percentage", "percent_decrease"]

            yield BenchmarkQuestion(
                question_text=question_text,
                answer_type=AnswerType.NUMERIC,
                correct_answer=answer,
                category="percentage_math",
                difficulty=difficulty,
                tags=tags,
                evaluation_criteria=EvaluationCriteria(exact_match=False, tolerance=0.01),
            )
