#!/usr/bin/python3

"""Generator for syllable count benchmark questions."""

import json
import logging
from typing import Any, Dict, Iterator, List, Optional

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
    "0014_syllable_count",
    "Syllable Count",
    "Tests ability to count syllables in words across Latin-alphabet languages.",
    category="token processing",
)(__name__)

_DIFFICULTY_MAP: Dict[str, Difficulty] = {
    "easy": Difficulty.EASY,
    "medium": Difficulty.MEDIUM,
    "hard": Difficulty.HARD,
}


@generator("0014_syllable_count")
class SyllableCountGenerator(BenchmarkGenerator):
    """Generator for syllable count benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session: Optional[Any] = None) -> None:
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)

        # Enable only file-based generation strategy
        self.can_load_from_file = True
        self.can_generate_locally = False
        self.can_generate_with_llm = False

        # Set file path for file-based generation
        self.questions_file_path = "samples.json"

        # Sample cache
        self._samples: Optional[List[Dict[str, Any]]] = None

    def _generate_from_file(self, **kwargs: Any) -> Iterator[BenchmarkQuestion]:
        """
        Generate syllable count questions from samples.json.

        Yields:
            BenchmarkQuestion objects
        """
        if not self.questions_file_path:
            logger.warning("No questions file path set")
            return

        try:
            if self._samples is None:
                self._samples = self.load_json_file(self.questions_file_path)

            samples = self._samples
            logger.info("Loaded %d syllable count samples from file", len(samples))

            for sample in samples:
                word: str = sample["word"]
                language_name: str = sample["language_name"]
                syllable_count: int = sample["syllable_count"]
                difficulty_str: str = sample.get("difficulty", "medium")
                difficulty = _DIFFICULTY_MAP.get(difficulty_str, Difficulty.MEDIUM)

                question_text = f"How many syllables are in the {language_name} word '{word}'?"

                question = BenchmarkQuestion(
                    question_text=question_text,
                    answer_type=AnswerType.NUMERIC,
                    correct_answer=syllable_count,
                    category="Syllable Count",
                    difficulty=difficulty,
                    tags=["syllable_count", "counting", "token_processing"],
                    evaluation_criteria=EvaluationCriteria(exact_match=True, tolerance=0.0),
                )

                yield question

        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error("Error loading syllable count sample data: %s", str(e))
