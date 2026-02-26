#!/usr/bin/python3

"""Generator for algebra benchmark questions."""

import logging
import random
from typing import Any, Iterator, List, Optional

from benchmarks.lib.utils.base_generator import BenchmarkGenerator
from benchmarks.lib.utils.data_models import (
    AnswerType,
    BenchmarkMetadata,
    BenchmarkQuestion,
    Difficulty,
    EvaluationCriteria,
)
from benchmarks.lib.utils.factory import benchmark, generator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0025_algebra"

benchmark(
    BENCHMARK_CODE,
    "Algebra",
    "Tests ability to solve linear and quadratic equations with integer solutions.",
    category="simple math",
)(__name__)

# Non-zero integers used as roots and solutions
_NONZERO_ROOTS = list(range(-8, 0)) + list(range(1, 9))


def _format_linear(a: int, b: int, c: int) -> str:
    """Format 'ax + b = c' as a readable equation string."""
    if b > 0:
        return f"{a}x + {b} = {c}"
    elif b < 0:
        return f"{a}x - {abs(b)} = {c}"
    else:
        return f"{a}x = {c}"


def _format_quadratic(b_coef: int, c_coef: int) -> str:
    """Format x² + b_coef·x + c_coef = 0, handling sign and coefficient-1 cases."""
    parts: List[str] = ["x²"]

    if b_coef == 1:
        parts.append("+ x")
    elif b_coef == -1:
        parts.append("- x")
    elif b_coef > 0:
        parts.append(f"+ {b_coef}x")
    elif b_coef < 0:
        parts.append(f"- {abs(b_coef)}x")
    # b_coef == 0: omit the x term

    if c_coef > 0:
        parts.append(f"+ {c_coef}")
    elif c_coef < 0:
        parts.append(f"- {abs(c_coef)}")
    # c_coef == 0: omit the constant term

    return " ".join(parts) + " = 0"


@generator(BENCHMARK_CODE)
class AlgebraGenerator(BenchmarkGenerator):
    """Generator for linear and quadratic algebra benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session: Optional[Any] = None) -> None:
        super().__init__(metadata, session)
        self.can_generate_locally = True

    def _generate_locally(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        while True:
            problem_type = random.choice(["linear", "quadratic_two_roots", "quadratic_single"])

            if problem_type == "linear":
                yield self._make_linear()
            elif problem_type == "quadratic_two_roots":
                yield self._make_quadratic_two_roots()
            else:
                yield self._make_quadratic_single()

    def _make_linear(self) -> BenchmarkQuestion:
        """ax + b = c with a single integer solution."""
        a = random.randint(2, 5)
        x_sol = random.choice(_NONZERO_ROOTS)
        b = random.randint(-20, 20)
        c = a * x_sol + b
        equation = _format_linear(a, b, c)
        question_text = f"If {equation}, what is x?"
        return BenchmarkQuestion(
            question_text=question_text,
            answer_type=AnswerType.NUMERIC,
            correct_answer=float(x_sol),
            category="algebra",
            difficulty=Difficulty.MEDIUM,
            tags=["algebra", "linear"],
            evaluation_criteria=EvaluationCriteria(exact_match=True, tolerance=0.001),
            schema={
                "type": "object",
                "properties": {
                    "result": {
                        "type": "number",
                        "description": "The value of x",
                    }
                },
                "required": ["result"],
            },
        )

    def _make_quadratic_two_roots(self) -> BenchmarkQuestion:
        """(x - r1)(x - r2) = 0 expanded into standard form, two distinct roots."""
        r1, r2 = random.sample(_NONZERO_ROOTS, 2)
        b_coef = -(r1 + r2)
        c_coef = r1 * r2
        equation = _format_quadratic(b_coef, c_coef)
        r_lo = min(r1, r2)
        r_hi = max(r1, r2)
        answer_str = f"{r_lo}, {r_hi}"
        question_text = (
            f"If {equation}, what are the values of x? "
            "(Give both answers separated by a comma, smallest first.)"
        )
        return BenchmarkQuestion(
            question_text=question_text,
            answer_type=AnswerType.FREE_TEXT,
            correct_answer=answer_str,
            category="algebra",
            difficulty=Difficulty.MEDIUM,
            tags=["algebra", "quadratic", "two_roots"],
            evaluation_criteria=EvaluationCriteria(exact_match=False),
            schema={
                "type": "object",
                "properties": {
                    "values": {
                        "type": "string",
                        "description": (
                            "Both values of x, comma-separated, smallest first " "(e.g. '-3, 5')"
                        ),
                    }
                },
                "required": ["values"],
            },
        )

    def _make_quadratic_single(self) -> BenchmarkQuestion:
        """(x - r)² = 0 expanded into standard form, one repeated root."""
        r = random.choice(_NONZERO_ROOTS)
        b_coef = -2 * r
        c_coef = r * r
        equation = _format_quadratic(b_coef, c_coef)
        question_text = f"If {equation}, what is x?"
        return BenchmarkQuestion(
            question_text=question_text,
            answer_type=AnswerType.NUMERIC,
            correct_answer=float(r),
            category="algebra",
            difficulty=Difficulty.MEDIUM,
            tags=["algebra", "quadratic", "single_root"],
            evaluation_criteria=EvaluationCriteria(exact_match=True, tolerance=0.001),
            schema={
                "type": "object",
                "properties": {
                    "result": {
                        "type": "number",
                        "description": "The value of x",
                    }
                },
                "required": ["result"],
            },
        )
