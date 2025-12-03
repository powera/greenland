#!/usr/bin/python3

"""Generator for part of speech benchmark questions."""

import json
import logging
import random
from typing import Dict, List, Optional, Any, Iterator

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

# Supported parts of speech for the benchmark
PARTS_OF_SPEECH = [
    "noun",
    "verb",
    "adjective",
    "adverb",
    "pronoun",
    "preposition",
    "conjunction",
    "interjection",
    "determiner",
]


@generator("0032_part_of_speech")
class PartOfSpeechGenerator(BenchmarkGenerator):
    """Generator for part of speech identification benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session=None):
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)

        # Strategy configuration
        self.can_load_from_file = True
        self.can_generate_locally = False  # No local algorithmic generation
        self.can_generate_with_llm = True

        # Set file paths for file-based generation
        self.questions_file_path = "samples.json"

        # Set custom context for LLM-based generation
        self.context = """You are a linguistics expert helping to create part-of-speech benchmark questions.
Your task is to create clear, unambiguous questions about identifying parts of speech in sentences.
Each question should have a clear, correct answer based on standard English grammar rules."""

        # Sample cache
        self._samples = None
        self._sample_index = 0

    def _generate_from_file(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """
        Generate questions from sample file.

        This generator yields BenchmarkQuestion objects one at a time.

        Yields:
            BenchmarkQuestion objects
        """
        try:
            # Load samples if not already loaded
            if not self._samples:
                self._samples = self.load_json_file(self.questions_file_path)
                logger.info(f"Loaded {len(self._samples)} sample sentences from file")

            # Yield questions for each sample
            for sample in self._samples:
                sentence = sample["sentence"]
                target_word = sample["target_word"]
                correct_pos = sample["pos"]

                # Create prompt for the model
                question_text = f"In the sentence '{sentence}', what is the part of speech of the word '{target_word}'?"

                # Create schema for structured response
                schema = {
                    "type": "object",
                    "properties": {
                        "part_of_speech": {
                            "type": "string",
                            "description": "The part of speech of the target word",
                        }
                    },
                    "required": ["part_of_speech"],
                }

                # Create the benchmark question
                question = BenchmarkQuestion(
                    question_text=question_text,
                    answer_type=AnswerType.JSON,
                    correct_answer={"part_of_speech": correct_pos},
                    category="grammar",
                    difficulty=Difficulty.MEDIUM,
                    tags=["grammar", "part-of-speech", "linguistics"],
                    schema=schema,
                    evaluation_criteria=EvaluationCriteria(
                        exact_match=False, case_sensitive=False, required_fields=["part_of_speech"]
                    ),
                )

                yield question

        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading sample data: {str(e)}")

    def _generate_with_llm(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """
        Generate questions using language model.

        This generator can yield an unlimited number of questions by continuously
        prompting the LLM for new sentences.

        Yields:
            BenchmarkQuestion objects
        """
        # Create schema for structured LLM response
        schema = {
            "type": "object",
            "properties": {
                "sentence": {
                    "type": "string",
                    "description": "A clear, grammatically correct sentence",
                },
                "target_word": {
                    "type": "string",
                    "description": "A word from the sentence to analyze",
                },
                "pos": {
                    "type": "string",
                    "description": "The part of speech of the target word",
                    "enum": PARTS_OF_SPEECH,
                },
            },
            "required": ["sentence", "target_word", "pos"],
        }

        # Generate an unlimited stream of questions
        while True:
            # Choose random part of speech to focus on
            pos_type = random.choice(PARTS_OF_SPEECH)

            # Create prompt for the LLM
            prompt = f"""Create a simple, clear sentence that contains at least one {pos_type}.
Choose one {pos_type} from your sentence as the target word.
Return the sentence, the target word (which must be a {pos_type}), and confirm that the part of speech is '{pos_type}'."""

            try:
                # Generate sentence data using LLM
                sentence_data = self.get_llm_question(prompt, schema=schema)

                sentence = sentence_data["sentence"]
                target_word = sentence_data["target_word"]
                correct_pos = sentence_data["pos"]

                # Create prompt for the benchmark question
                question_text = f"In the sentence '{sentence}', what is the part of speech of the word '{target_word}'?"

                # Create schema for structured response
                response_schema = {
                    "type": "object",
                    "properties": {
                        "part_of_speech": {
                            "type": "string",
                            "description": "The part of speech of the target word",
                        }
                    },
                    "required": ["part_of_speech"],
                }

                # Create the benchmark question
                question = BenchmarkQuestion(
                    question_text=question_text,
                    answer_type=AnswerType.JSON,
                    correct_answer={"part_of_speech": correct_pos},
                    category="grammar",
                    difficulty=Difficulty.MEDIUM,
                    tags=["grammar", "part-of-speech", "linguistics"],
                    schema=response_schema,
                    evaluation_criteria=EvaluationCriteria(
                        exact_match=False, case_sensitive=False, required_fields=["part_of_speech"]
                    ),
                )

                yield question

            except Exception as e:
                logger.error(f"Error generating question with LLM: {str(e)}")
                # If we encounter an error, we'll continue the loop and try again
