#!/usr/bin/python3

"""Spell check benchmark question generator."""

import json
import logging
import os
import random
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

import constants
from clients import unified_client
from lib.benchmarks.base import BenchmarkGenerator
from lib.benchmarks.data_models import (
    BenchmarkQuestion, BenchmarkMetadata,
    AnswerType, Difficulty, EvaluationCriteria
)
from lib.benchmarks.factory import generator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define benchmark code
BENCHMARK_CODE = "0015_spell_check"


@generator(BENCHMARK_CODE)
class SpellCheckGenerator(BenchmarkGenerator):
    """Generator for spell check benchmark questions."""
    
    def __init__(self, metadata: BenchmarkMetadata, session: Optional[Session] = None):
        super().__init__(metadata, session)
        self.context = """You are a creative writing assistant. Write a natural-sounding sentence that:
1. Uses the specified word as its subject or object
2. Introduces a spelling error in that word
3. Maintains proper grammar and natural flow aside from the misspelling
4. Is written at roughly an 8th grade reading level"""

    def generate_question(self, word: Optional[str] = None) -> BenchmarkQuestion:
        """
        Generate a standardized benchmark question for spell checking.
        
        Args:
            word: Optional specific word to use (if None, a random word will be selected)
            
        Returns:
            BenchmarkQuestion object
        """
        if word is None:
            # Load wordlist from data or use from existing list
            try:
                all_words = self.load_text_file("wordlist.txt")
                word = random.choice(all_words)
            except FileNotFoundError:
                # Fallback to a small set of common words
                common_words = ["attention", "demonstrate", "laboratory", "laughter", 
                              "liaison", "orange", "partition", "party", "stable", "table"]
                word = random.choice(common_words)
        
        # Use LLM to generate a sentence with misspelled word
        schema = {
            "type": "object",
            "properties": {
                "sentence": {"type": "string", "description": "A sentence containing the misspelled word"},
                "incorrect": {"type": "string", "description": "The misspelled version of the word"},
                "correct": {"type": "string", "description": "The correct spelling of the word"}
            },
            "required": ["sentence", "incorrect", "correct"]
        }
        
        prompt = f"""Create a sentence that contains a misspelled version of the word "{word}".
Make sure the misspelling is natural (like a common typing or spelling error).
The sentence should be grammatically correct except for the misspelling."""

        # Generate content using the LLM
        response = self.generate_llm_question(
            prompt=prompt,
            schema=schema,
            context=self.context
        )
        
        # Create the benchmark question
        question = BenchmarkQuestion(
            question_text=f"What is the incorrectly-spelled word in this sentence: {response['sentence']}",
            answer_type=AnswerType.JSON,
            correct_answer={
                "incorrect": response["incorrect"],
                "correct": response["correct"]
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
                "required": ["incorrect", "correct"]
            },
            evaluation_criteria=EvaluationCriteria(
                exact_match=True,
                case_sensitive=False,
                required_fields=["incorrect", "correct"]
            )
        )
        
        return question

    def load_question_from_file(self, filename: str) -> List[BenchmarkQuestion]:
        """
        Load questions from a JSON file.
        
        Args:
            filename: Name of the JSON file (without extension)
            
        Returns:
            List of BenchmarkQuestion objects
        """
        try:
            # Load the JSON file for this word
            word_data = self.load_json_file(f"{filename}.json")
            questions = []
            
            for item in word_data:
                if not all(k in item for k in ["sentence", "incorrect", "correct"]):
                    logger.warning(f"Skipping incomplete item in {filename}.json: {item}")
                    continue
                
                question = BenchmarkQuestion(
                    question_text=f"What is the incorrectly-spelled word in this sentence: {item['sentence']}",
                    answer_type=AnswerType.JSON,
                    correct_answer={
                        "incorrect": item["incorrect"],
                        "correct": item["correct"]
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
                        "required": ["incorrect", "correct"]
                    },
                    evaluation_criteria=EvaluationCriteria(
                        exact_match=True,
                        case_sensitive=False,
                        required_fields=["incorrect", "correct"]
                    )
                )
                questions.append(question)
            
            return questions
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.error(f"Error loading questions from {filename}.json: {str(e)}")
            return []