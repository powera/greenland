#!/usr/bin/python3

"""Spell check benchmark question generator."""

import json
import logging
import os
import time
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

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

    def generate_question(self, word: str, incorrect_spelling: str, sentence: str) -> BenchmarkQuestion:
        """
        Generate a standardized benchmark question for spell checking.
        
        Args:
            word: The correctly spelled word
            incorrect_spelling: The misspelled version in the sentence
            sentence: The sentence containing the misspelled word
            
        Returns:
            BenchmarkQuestion object
        """
        # Create a structured question
        question = BenchmarkQuestion(
            question_text=f"What is the incorrectly-spelled word in this sentence: {sentence}",
            answer_type=AnswerType.JSON,
            correct_answer={
                "incorrect": incorrect_spelling,
                "correct": word
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

    def generate_sentence(self, word: str, model: str = "gemma2:9b") -> str:
        """Generate a sentence using word but spelled incorrectly."""
        prompt = f"Write a sentence using the word '{word}', but spell it incorrectly."
        
        response = unified_client.generate_chat(
            prompt=prompt,
            model=model,
            context=self.context
        )
            
        return response.response_text.strip()

    def extract_misspelled_word(self, sentence: str, correct_word: str, model: str = "gemma2:9b") -> str:
        """Extract the misspelled version of the word from the sentence."""
        prompt = f"""In this sentence: "{sentence}"
What is the misspelled version of the word "{correct_word}"? 
Just return the misspelled word with no other text."""
        
        response = unified_client.generate_chat(
            prompt=prompt,
            model=model,
            brief=True
        )
            
        return response.response_text.strip()

    def generate_batch(self, wordlist: List[str], model: str = "gemma2:9b") -> List[BenchmarkQuestion]:
        """
        Generate a batch of spell check questions from a wordlist.
        
        Args:
            wordlist: List of correctly spelled words
            model: Model to use for generating sentences
            
        Returns:
            List of BenchmarkQuestion objects
        """
        questions = []
        
        for word in wordlist:
            sentence = self.generate_sentence(word, model)
            time.sleep(1)  # Prevent rate limiting
            
            # Extract the misspelled word
            misspelled = self.extract_misspelled_word(sentence, word, model)
            
            # Generate the question
            question = self.generate_question(word, misspelled, sentence)
            questions.append(question)
            
        return questions

    def load_to_database(self) -> None:
        """Load generated spell check questions into database."""
        # Path to the directory containing spell check JSON files
        DIR = os.path.join("src", "benchmarks", "0015_spell_check")
        files = sorted(os.listdir(DIR))

        questions = []
        
        for filename in files:
            if not filename.endswith(".json"):
                continue
                
            word = filename.split('.')[0]  # Extract word from filename
            
            with open(os.path.join(DIR, filename)) as f:
                sentences = json.load(f)
                
                for idx, item in enumerate(sentences):
                    if not item.get("incorrect"):
                        logger.warning(f"Skipping item with missing 'incorrect' field: {item}")
                        continue
                        
                    question = self.generate_question(
                        word=item["correct"],
                        incorrect_spelling=item["incorrect"],
                        sentence=item["sentence"]
                    )
                    
                    # Save with a custom ID format
                    self.save_question(question, f"{word}:{idx}")
                    questions.append(question)
        
        logger.info(f"Loaded {len(questions)} spell check questions into database")
