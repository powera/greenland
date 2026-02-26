#!/usr/bin/python3

"""Generator for geometry benchmark questions."""

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

BENCHMARK_CODE = "0027_geometry"

benchmark(
    BENCHMARK_CODE,
    "Geometry",
    "Tests ability to calculate area, perimeter, and volume for rectangles, triangles, boxes, and circles.",
    category="simple math",
)(__name__)

# Use the same π approximation stated in each circle question
_PI = 3.14159

# Tolerance for non-π answers (integer arithmetic exact)
_TOLERANCE_EXACT = 0.001
# Tolerance for π-based answers (rounding differences in π approximation)
_TOLERANCE_PI = 0.05

_SHAPE_TYPES = [
    "rect_area",
    "rect_perimeter",
    "triangle_area",
    "box_volume",
    "circle_area",
    "circle_circumference",
]


@generator(BENCHMARK_CODE)
class GeometryGenerator(BenchmarkGenerator):
    """Generator for geometry benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session: Optional[Any] = None) -> None:
        super().__init__(metadata, session)
        self.can_generate_locally = True

    def _generate_locally(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        while True:
            shape = random.choice(_SHAPE_TYPES)
            yield self._make_question(shape)

    def _make_question(self, shape: str) -> BenchmarkQuestion:
        if shape == "rect_area":
            length = random.randint(2, 20)
            width = random.randint(2, 20)
            answer = float(length * width)
            question = f"What is the area of a rectangle with length {length} and width {width}?"
            tags: List[str] = ["geometry", "rectangle", "area"]
            tolerance = _TOLERANCE_EXACT

        elif shape == "rect_perimeter":
            length = random.randint(2, 20)
            width = random.randint(2, 20)
            answer = float(2 * (length + width))
            question = (
                f"What is the perimeter of a rectangle with length {length} and width {width}?"
            )
            tags = ["geometry", "rectangle", "perimeter"]
            tolerance = _TOLERANCE_EXACT

        elif shape == "triangle_area":
            # Make base even so that base * height / 2 is always an integer
            base = random.randint(1, 10) * 2
            height = random.randint(2, 20)
            answer = float(base * height // 2)
            question = f"What is the area of a triangle with base {base} and height {height}?"
            tags = ["geometry", "triangle", "area"]
            tolerance = _TOLERANCE_EXACT

        elif shape == "box_volume":
            length = random.randint(2, 10)
            width = random.randint(2, 10)
            height = random.randint(2, 10)
            answer = float(length * width * height)
            question = (
                f"What is the volume of a rectangular box with "
                f"length {length}, width {width}, and height {height}?"
            )
            tags = ["geometry", "box", "volume"]
            tolerance = _TOLERANCE_EXACT

        elif shape == "circle_area":
            radius = random.randint(1, 10)
            answer = round(_PI * radius * radius, 2)
            question = (
                f"What is the area of a circle with radius {radius}? "
                f"Use π ≈ 3.14159 and round your answer to 2 decimal places."
            )
            tags = ["geometry", "circle", "area"]
            tolerance = _TOLERANCE_PI

        else:  # circle_circumference
            radius = random.randint(1, 10)
            answer = round(2 * _PI * radius, 2)
            question = (
                f"What is the circumference of a circle with radius {radius}? "
                f"Use π ≈ 3.14159 and round your answer to 2 decimal places."
            )
            tags = ["geometry", "circle", "circumference"]
            tolerance = _TOLERANCE_PI

        return BenchmarkQuestion(
            question_text=question,
            answer_type=AnswerType.NUMERIC,
            correct_answer=answer,
            category="geometry",
            difficulty=Difficulty.MEDIUM,
            tags=tags,
            evaluation_criteria=EvaluationCriteria(exact_match=True, tolerance=tolerance),
        )
