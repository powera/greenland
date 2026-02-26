#!/usr/bin/python3

"""Generator for math word problems benchmark questions."""

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

BENCHMARK_CODE = "0023_word_problems"

benchmark(
    BENCHMARK_CODE,
    "Math Word Problems",
    "Tests ability to read word problems and extract relevant numbers, including problems with unused/distractor information.",
    category="simple math",
)(__name__)

_NAMES = [
    "Alice",
    "Bob",
    "Carlos",
    "David",
    "Emma",
    "Fatima",
    "George",
    "Hannah",
    "Ivan",
    "Julia",
]
_ITEMS = ["book", "pencil", "apple", "card", "sticker", "orange", "cookie", "marble"]


def _pick_names(count: int) -> List[str]:
    """Return `count` distinct random names."""
    return random.sample(_NAMES, count)


def _pick_item() -> str:
    return random.choice(_ITEMS)


@generator(BENCHMARK_CODE)
class WordProblemsGenerator(BenchmarkGenerator):
    """Generator for math word problems benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session: Optional[Any] = None) -> None:
        super().__init__(metadata, session)
        self.can_generate_locally = True

    def _generate_locally(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        while True:
            yield self._make_question()

    def _make_question(self) -> BenchmarkQuestion:
        # 9 templates total: 6 without distractors, 3 with distractors (~1/3 rate)
        template = random.randint(0, 8)

        if template == 0:
            # Addition: two people, combine
            name1, name2 = _pick_names(2)
            item = _pick_item()
            n1 = random.randint(2, 30)
            n2 = random.randint(2, 30)
            answer = n1 + n2
            question = (
                f"{name1} has {n1} {item}s and {name2} has {n2} {item}s. "
                f"How many {item}s do they have together?"
            )
            tags = ["word_problem", "addition"]

        elif template == 1:
            # Multiplication: rows and columns
            item = _pick_item()
            rows = random.randint(2, 12)
            cols = random.randint(2, 12)
            answer = rows * cols
            question = (
                f"There are {rows} rows of {item}s with {cols} {item}s in each row. "
                f"How many {item}s are there in total?"
            )
            tags = ["word_problem", "multiplication"]

        elif template == 2:
            # Division: share cookies equally among friends
            name1 = _pick_names(1)[0]
            n_friends = random.randint(2, 10)
            per_friend = random.randint(2, 15)
            n_total = n_friends * per_friend
            answer = per_friend
            question = (
                f"{name1} baked {n_total} cookies and wants to give an equal number "
                f"to each of {n_friends} friends. How many cookies does each friend get?"
            )
            tags = ["word_problem", "division"]

        elif template == 3:
            # Multiplication: distance at constant speed
            speed = random.randint(40, 120)
            hours = random.randint(2, 8)
            answer = speed * hours
            question = f"A car travels at {speed} km/h. How far does it travel in {hours} hours?"
            tags = ["word_problem", "multiplication"]

        elif template == 4:
            # Subtraction: spending money
            name1 = _pick_names(1)[0]
            n1 = random.randint(20, 100)
            n2 = random.randint(5, n1 - 1)
            answer = n1 - n2
            question = (
                f"{name1} had {n1} dollars. After spending {n2} dollars, "
                f"how much money does {name1} have left?"
            )
            tags = ["word_problem", "subtraction"]

        elif template == 5:
            # Subtraction: items sold from a store
            item = _pick_item()
            n1 = random.randint(20, 80)
            n2 = random.randint(5, n1 - 1)
            answer = n1 - n2
            question = (
                f"A store had {n1} {item}s. They sold {n2} {item}s. " f"How many {item}s are left?"
            )
            tags = ["word_problem", "subtraction"]

        elif template == 6:
            # Addition with distractor: three people, ask about two (n1 is unused)
            name1, name2, name3 = _pick_names(3)
            item = _pick_item()
            n1 = random.randint(2, 30)
            n2 = random.randint(2, 30)
            n3 = random.randint(2, 30)
            answer = n2 + n3
            question = (
                f"{name1} has {n1} {item}s, {name2} has {n2} {item}s, and "
                f"{name3} has {n3} {item}s. "
                f"How many {item}s do {name2} and {name3} have together?"
            )
            tags = ["word_problem", "addition", "distractor"]

        elif template == 7:
            # Subtraction with distractor: three fruit categories, only oranges asked
            n_apples = random.randint(10, 50)
            n_oranges = random.randint(15, 60)
            n_bananas = random.randint(10, 40)
            n_sold = random.randint(3, n_oranges - 1)
            answer = n_oranges - n_sold
            question = (
                f"A store has {n_apples} apples, {n_oranges} oranges, and {n_bananas} bananas. "
                f"A customer buys {n_sold} oranges. "
                f"How many oranges does the store have left?"
            )
            tags = ["word_problem", "subtraction", "distractor"]

        else:  # template == 8
            # Addition with distractor: three-hour journey, ask about first two hours (n3 unused)
            n1 = random.randint(40, 120)
            n2 = random.randint(40, 120)
            n3 = random.randint(40, 120)
            answer = n1 + n2
            question = (
                f"A train travels {n1} km in the first hour, {n2} km in the second hour, "
                f"and {n3} km in the third hour. "
                f"How far does it travel in the first two hours?"
            )
            tags = ["word_problem", "addition", "distractor"]

        return BenchmarkQuestion(
            question_text=question,
            answer_type=AnswerType.NUMERIC,
            correct_answer=float(answer),
            category="word_problems",
            difficulty=Difficulty.MEDIUM,
            tags=tags,
            evaluation_criteria=EvaluationCriteria(exact_match=True, tolerance=0.001),
        )
