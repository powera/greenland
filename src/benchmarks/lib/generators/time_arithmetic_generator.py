#!/usr/bin/python3

"""Generator for time arithmetic benchmark questions."""

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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

BENCHMARK_CODE = "0026_time_arithmetic"

benchmark(
    BENCHMARK_CODE,
    "Time Arithmetic",
    "Tests ability to add/subtract durations from clock times in 24-hour HH:MM format.",
    category="simple math",
)(__name__)


def _format_time(total_minutes: int) -> str:
    wrapped = total_minutes % (24 * 60)
    hour = wrapped // 60
    minute = wrapped % 60
    return f"{hour:02d}:{minute:02d}"


@generator(BENCHMARK_CODE)
class TimeArithmeticGenerator(BenchmarkGenerator):
    """Generator for time arithmetic benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session: Optional[Any] = None) -> None:
        super().__init__(metadata, session)
        self.can_load_from_file = False
        self.can_generate_locally = True
        self.can_generate_with_llm = False

    def _generate_locally(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        while True:
            start_hour = random.randint(0, 23)
            start_minute = random.choice([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55])
            start_total = (start_hour * 60) + start_minute

            op = random.choice(["add", "subtract"])
            duration = random.choice([5, 10, 15, 20, 30, 35, 40, 45, 50, 60, 75, 90, 120, 135])

            if op == "add":
                result_total = start_total + duration
                question_text = (
                    f"Starting at {start_hour:02d}:{start_minute:02d}, what time is it after {duration} minutes? "
                    "Return HH:MM in 24-hour format."
                )
                tags = ["time", "arithmetic", "addition"]
            else:
                result_total = start_total - duration
                question_text = (
                    f"Starting at {start_hour:02d}:{start_minute:02d}, what time was it {duration} minutes earlier? "
                    "Return HH:MM in 24-hour format."
                )
                tags = ["time", "arithmetic", "subtraction"]

            difficulty = Difficulty.EASY if duration <= 45 else Difficulty.MEDIUM
            if duration >= 120:
                difficulty = Difficulty.HARD

            yield BenchmarkQuestion(
                question_text=question_text,
                answer_type=AnswerType.FREE_TEXT,
                correct_answer=_format_time(result_total),
                category="time_arithmetic",
                difficulty=difficulty,
                tags=tags,
                evaluation_criteria=EvaluationCriteria(exact_match=True, case_sensitive=False),
                schema={
                    "type": "object",
                    "properties": {
                        "time": {
                            "type": "string",
                            "description": "Computed clock time in HH:MM 24-hour format",
                        }
                    },
                    "required": ["time"],
                },
            )
