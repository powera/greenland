#!/usr/bin/python3

"""Generator for letter count benchmark questions."""

import json
import logging
import random
from typing import Dict, List, Optional, Any

from lib.benchmarks.base import BenchmarkGenerator
from lib.benchmarks.data_models import (
    BenchmarkQuestion, BenchmarkMetadata, 
    AnswerType, Difficulty, EvaluationCriteria
)
from lib.benchmarks.factory import generator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Sample words to use for the benchmark
COMMON_WORDS = [
    "strawberry", "programming", "mathematics", "engineering", "intelligence",
    "development", "application", "successful", "interesting", "beautiful",
    "ordinary", "atmosphere", "excitement", "conversation", "experience",
    "knowledge", "necessary", "community", "education", "information",
    "technology", "understanding", "opportunity", "relationship", "environment",
    "significant", "performance", "profession", "university", "restaurant",
    "breakfast", "president", "television", "government", "important",
    "computer", "different", "business", "possible", "together"
]

@generator("0012_letter_count")
class LetterCountGenerator(BenchmarkGenerator):
    """Generator for letter count benchmark questions."""
    
    def __init__(self, metadata: BenchmarkMetadata, session=None):
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)
        self.word_list = COMMON_WORDS
        
    def generate_question(self, word: Optional[str] = None, letter: Optional[str] = None) -> BenchmarkQuestion:
        """
        Generate a question asking to count occurrences of a letter in a word.
        
        Args:
            word: Optional specific word to use
            letter: Optional specific letter to count
            
        Returns:
            BenchmarkQuestion object
        """
        # If no word provided, select a random one
        if not word:
            word = random.choice(self.word_list)
            
        # If no letter provided, select a random one from the word
        if not letter:
            # Prefer letters that appear multiple times
            letter_counts = {}
            for char in word:
                if char.isalpha():
                    letter_counts[char.lower()] = letter_counts.get(char.lower(), 0) + 1
                    
            # Select letters that appear at least once, with higher probability for those appearing multiple times
            candidates = [(letter, count) for letter, count in letter_counts.items()]
            letter = random.choice(candidates)[0]
        
        # Count occurrences
        count = word.lower().count(letter.lower())
        
        # Create the question
        question_text = f"How many times does the letter '{letter}' appear in the word '{word}'?"
        
        return BenchmarkQuestion(
            question_text=question_text,
            answer_type=AnswerType.NUMERIC,
            correct_answer=count,
            category="Letter Counting",
            difficulty=Difficulty.EASY,
            tags=["letter_count", "spelling", "counting"],
            evaluation_criteria=EvaluationCriteria(
                exact_match=True,
                tolerance=0.0  # No tolerance for counting - must be exact
            )
        )
        
    def load_to_database(self, num_questions: int = 50) -> List[str]:
        """
        Generate and load questions into the database.
        
        Args:
            num_questions: Number of questions to generate
            
        Returns:
            List of question IDs
        """
        questions = []
        
        # Generate a diverse set of questions
        used_pairs = set()  # Track (word, letter) pairs to avoid duplicates
        
        while len(questions) < num_questions:
            word = random.choice(self.word_list)
            
            # Select a letter that appears in the word
            letters = [char.lower() for char in word if char.isalpha()]
            letter = random.choice(letters)
            
            # Avoid duplicates
            if (word, letter) in used_pairs:
                continue
                
            used_pairs.add((word, letter))
            questions.append(self.generate_question(word, letter))
            
            if len(questions) % 10 == 0:
                logger.info("Generated %d/%d questions", len(questions), num_questions)
        
        # Save questions to database
        logger.info("Saving %d questions to database", len(questions))
        return self.batch_save_questions(questions)
