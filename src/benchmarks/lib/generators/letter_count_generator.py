#!/usr/bin/python3

"""Generator for letter count benchmark questions."""

import json
import logging
import os
import random
from typing import Dict, Iterator, List, Optional

from benchmarks.lib.utils.base import *
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

benchmark(
    "0012_letter_count",
    "Letter Count",
    "Tests ability to count occurrences of a specific letter in a word.",
    category="token processing",
)(__name__)


@generator("0012_letter_count")
class LetterCountGenerator(BenchmarkGenerator):
    """Generator for letter count benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session=None):
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)

        # Use the common words list that is hardcoded
        self.word_list = COMMON_LONG_WORDS

        # Enable only local generation strategy
        self.can_load_from_file = False
        self.can_generate_locally = True
        self.can_generate_with_llm = False

        # Define the benchmark directory (in case we want to add file loading later)
        self.questions_directory = os.path.join("benchmarks", "0012_letter_count")

    def _generate_locally(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """
        Generate letter count questions algorithmically.

        This is a generator function that yields BenchmarkQuestion objects
        one at a time.

        Args:
            **kwargs: Additional parameters to control generation

        Yields:
            BenchmarkQuestion objects
        """
        logger.info("Generating letter count questions locally")

        # We can generate questions indefinitely with random selections
        while True:
            # Select a random word
            word = random.choice(self.word_list)

            # Select a random letter from the word
            letter_counts: dict[str, int] = {}
            for char in word:
                if char.isalpha():
                    letter_counts[char.lower()] = letter_counts.get(char.lower(), 0) + 1

            # Select letters that appear at least once
            candidates = list(letter_counts.keys())
            letter = random.choice(candidates)

            # Count occurrences
            count = word.lower().count(letter.lower())

            # Create the question
            question_text = (
                f"How many times does the letter '{letter}' appear in the word '{word}'?"
            )

            question = BenchmarkQuestion(
                question_text=question_text,
                answer_type=AnswerType.NUMERIC,
                correct_answer=count,
                category="Letter Counting",
                difficulty=Difficulty.EASY,
                tags=["letter_count", "spelling", "counting"],
                evaluation_criteria=EvaluationCriteria(
                    exact_match=True, tolerance=0.0  # No tolerance for counting - must be exact
                ),
            )

            yield question
