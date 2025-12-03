#!/usr/bin/python3

"""Spell check benchmark question generator."""

import json
import logging
import os
import random
from typing import Dict, List, Optional, Tuple, Iterator

from sqlalchemy.orm import Session

import constants
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

# Define benchmark code
BENCHMARK_CODE = "0015_spell_check"


@generator(BENCHMARK_CODE)
class SpellCheckGenerator(BenchmarkGenerator):
    """Generator for spell check benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session: Optional[Session] = None):
        """Initialize the generator with benchmark metadata."""
        super().__init__(metadata, session)

        # Configure generation strategies
        self.can_load_from_file = True
        self.can_generate_locally = False
        self.can_generate_with_llm = True

        # LLM generation context
        self.context = """You are a creative writing assistant. Write a natural-sounding sentence that:
1. Uses the specified word as its subject or object
2. Introduces a spelling error in that word
3. Maintains proper grammar and natural flow aside from the misspelling
4. Is written at roughly an 8th grade reading level"""

        # Set up file paths for question loading
        self.questions_directory = os.path.join(constants.BENCHMARK_DATA_DIR, self.metadata.code)

        # Determine available word files
        self.word_files = []
        try:
            for filename in os.listdir(self.questions_directory):
                if filename.endswith(".json"):
                    self.word_files.append(filename[:-5])  # Remove .json extension
        except FileNotFoundError:
            logger.warning(f"Questions directory not found: {self.questions_directory}")

    def _generate_from_file(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """
        Generate questions from JSON files in the benchmark directory.

        Yields:
            BenchmarkQuestion objects
        """
        if not self.word_files:
            logger.warning("No word files found for file-based generation")
            return

        # Shuffle the word files to get different questions each time
        random.shuffle(self.word_files)

        for filename in self.word_files:
            try:
                # Load the JSON file for this word
                word_data = self.load_json_file(f"{filename}.json")

                for item in word_data:
                    if not all(k in item for k in ["sentence", "incorrect", "correct"]):
                        logger.warning(f"Skipping incomplete item in {filename}.json: {item}")
                        continue

                    question = BenchmarkQuestion(
                        question_text=f"What is the incorrectly-spelled word in this sentence: {item['sentence']}",
                        answer_type=AnswerType.JSON,
                        correct_answer={"incorrect": item["incorrect"], "correct": item["correct"]},
                        category="spelling",
                        difficulty=Difficulty.MEDIUM,
                        tags=["spelling", "correction"],
                        schema={
                            "type": "object",
                            "properties": {
                                "incorrect": {"type": "string"},
                                "correct": {"type": "string"},
                            },
                            "required": ["incorrect", "correct"],
                        },
                        evaluation_criteria=EvaluationCriteria(
                            exact_match=True,
                            case_sensitive=False,
                            required_fields=["incorrect", "correct"],
                        ),
                    )
                    yield question
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logger.error(f"Error loading questions from {filename}.json: {str(e)}")

    def _generate_with_llm(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """
        Generate questions using a language model.

        Yields:
            BenchmarkQuestion objects
        """
        # Try to load wordlist or use default words
        try:
            all_words = self.load_text_file("wordlist.txt")
        except FileNotFoundError:
            # Fallback to a small set of common words
            all_words = COMMON_LONG_WORDS

        # Keep generating as long as words are available
        words_copy = all_words.copy()
        random.shuffle(words_copy)

        # Schema for LLM generation
        schema = {
            "type": "object",
            "properties": {
                "sentence": {
                    "type": "string",
                    "description": "A sentence containing the misspelled word",
                },
                "incorrect": {
                    "type": "string",
                    "description": "The misspelled version of the word",
                },
                "correct": {"type": "string", "description": "The correct spelling of the word"},
            },
            "required": ["sentence", "incorrect", "correct"],
        }

        for word in words_copy:
            prompt = f"""Create a sentence that contains a misspelled version of the word "{word}".
Make sure the misspelling is natural (like a common typing or spelling error).
The sentence should be grammatically correct except for the misspelling."""

            try:
                # Generate content using the LLM
                response = self.get_llm_question(prompt=prompt, schema=schema, context=self.context)

                # Create the benchmark question
                question = BenchmarkQuestion(
                    question_text=f"What is the incorrectly-spelled word in this sentence: {response['sentence']}",
                    answer_type=AnswerType.JSON,
                    correct_answer={
                        "incorrect": response["incorrect"],
                        "correct": response["correct"],
                    },
                    category="spelling",
                    difficulty=Difficulty.MEDIUM,
                    tags=["spelling", "correction"],
                    schema={
                        "type": "object",
                        "properties": {
                            "incorrect": {"type": "string"},
                            "correct": {"type": "string"},
                        },
                        "required": ["incorrect", "correct"],
                    },
                    evaluation_criteria=EvaluationCriteria(
                        exact_match=True,
                        case_sensitive=False,
                        required_fields=["incorrect", "correct"],
                    ),
                )

                yield question
            except Exception as e:
                logger.error(f"Error generating question for word '{word}': {str(e)}")
