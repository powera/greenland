#!/usr/bin/python3

"""Generator for word length benchmark questions."""

import logging
import random
import os
from typing import Iterator

from lib.benchmarks.base import *
from lib.benchmarks.data_models import (
    BenchmarkQuestion,
    BenchmarkMetadata,
    AnswerType,
    Difficulty,
    EvaluationCriteria,
)
from lib.benchmarks.factory import generator

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@generator("0011_word_length")
class WordLengthGenerator(BenchmarkGenerator):
    """Generator for word length benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session=None):
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)

        # Use the common words lists that are hardcoded in base.py
        self.word_lists = {
            Difficulty.EASY: COMMON_SHORT_WORDS,
            Difficulty.MEDIUM: COMMON_MEDIUM_WORDS,
            Difficulty.HARD: COMMON_LONG_WORDS,
        }

        # Enable only local generation strategy
        self.can_load_from_file = False
        self.can_generate_locally = True
        self.can_generate_with_llm = False

        # Define the benchmark directory (in case we want to add file loading later)
        self.questions_directory = os.path.join("benchmarks", "0011_word_length")

    def _generate_locally(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """
        Generate word length questions algorithmically.

        This is a generator function that yields BenchmarkQuestion objects
        one at a time.

        Args:
            **kwargs: Additional parameters to control generation

        Yields:
            BenchmarkQuestion objects
        """
        logger.info("Generating word length questions locally")

        # We can generate questions indefinitely with random selections
        while True:
            # Select a random difficulty
            difficulty = random.choice(list(Difficulty))

            # Select a random word from the appropriate list
            word = random.choice(self.word_lists[difficulty])

            # Count letters (excluding spaces, punctuation, etc.)
            word_length = sum(1 for char in word if char.isalpha())

            # Create the question
            question_text = f"How many letters are in the word '{word}'?"

            question = BenchmarkQuestion(
                question_text=question_text,
                answer_type=AnswerType.NUMERIC,
                correct_answer=word_length,
                category="Word Length",
                difficulty=difficulty,
                tags=["word_length", "counting", "spelling"],
                evaluation_criteria=EvaluationCriteria(
                    exact_match=True, tolerance=0.0  # No tolerance for counting - must be exact
                ),
            )

            yield question
