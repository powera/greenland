#!/usr/bin/python3

"""Word definitions benchmark generator implementation."""

import random
import os
from typing import List, Iterator

from lib.benchmarks.base import *
from lib.benchmarks.data_models import (
    BenchmarkQuestion, BenchmarkMetadata, 
    AnswerType, Difficulty, EvaluationCriteria
)
from lib.benchmarks.factory import generator, benchmark

# Define benchmark metadata
BENCHMARK_CODE = "0020_definitions"
BENCHMARK_NAME = "Word Definitions"
BENCHMARK_DESCRIPTION = "Tests ability to match definitions to correct words."

# Apply benchmark decorator to this module
@benchmark(code=BENCHMARK_CODE, name=BENCHMARK_NAME, description=BENCHMARK_DESCRIPTION)
class DefinitionsBenchmarkModule:
    """Module for word definitions benchmark."""
    pass

@generator(BENCHMARK_CODE)
class DefinitionsGenerator(BenchmarkGenerator):
    """Generator for definitions benchmark questions."""

    def __init__(self, metadata: BenchmarkMetadata, session=None):
        """Initialize generator with benchmark metadata."""
        super().__init__(metadata, session)
        
        # Enable appropriate generation strategies
        self.can_load_from_file = False  # No preexisting files for this benchmark
        self.can_generate_locally = False  # Can't generate fully locally (need LLM for definitions)
        self.can_generate_with_llm = True  # We need LLM for definitions
        
        # Configure context for LLM-based generation
        self.context = """You are a lexicographer writing clear, concise definitions. For each word:
1. Write a single-sentence definition
2. Do not use the word itself in the definition
3. Focus on the most common meaning of the word
4. Use simple, clear language"""
        
        # Define schema for structured LLM responses
        self.schema = {
            "type": "object",
            "properties": {
                "definition": {"type": "string"},
                "explanation": {"type": "string"},
            },
            "required": ["definition"],
        }
        
        # Define preferred generation order - only LLM is available
        self.strategy_order = ["llm"]

    def _load_word_list(self) -> List[str]:
        """Load word list from file or use fallback list."""
        try:
            return self.load_text_file("wordlist.txt")
        except FileNotFoundError:
            # Fallback to a small set of common words if file is not found
            return COMMON_MEDIUM_WORDS

    def _generate_with_llm(self, **kwargs) -> Iterator[BenchmarkQuestion]:
        """
        Generate questions using LLM for definitions with words from local word list.
        
        This is a generator function that yields BenchmarkQuestion objects
        one at a time.
        
        Args:
            **kwargs: Additional parameters to control generation
            
        Yields:
            BenchmarkQuestion objects
        """
        # Load word list
        words = self._load_word_list()
        
        # Track used words to avoid duplicates in a single generation session
        used_words = set()
        
        # Keep generating until we run out of unused correct words
        while len(used_words) < len(words):  # Stop when all words have been used as correct answers
            # Select the correct word from words that haven't been used as correct answers
            available_correct_words = [word for word in words if word not in used_words]
            if not available_correct_words:
                break
                
            # Select the correct word randomly from available words
            correct = random.choice(available_correct_words)
            used_words.add(correct)
            
            # Select decoy words (can include previously used correct words)
            # Ensure we don't include the current correct word in decoys
            decoy_pool = [word for word in words if word != correct]
            decoys = random.sample(decoy_pool, min(9, len(decoy_pool)))
            
            # Combine correct word and decoys
            choices = [correct] + decoys
            choices.sort()  # Sort for consistent presentation

            # Generate definition using the LLM
            prompt = f'Define the word "{correct}"'
            
            try:
                response = self.get_llm_question(
                    prompt=prompt,
                    schema=self.schema
                )
                
                definition = response["definition"]

                # Create question text
                question_text = f'Which word has this definition: {definition}\n\nThe choices are: {", ".join(choices)}'

                # Create and yield question object
                yield BenchmarkQuestion(
                    question_text=question_text,
                    answer_type=AnswerType.MULTIPLE_CHOICE,
                    correct_answer=correct,
                    choices=choices,
                    category="vocabulary",
                    difficulty=Difficulty.MEDIUM,
                    tags=["vocabulary", "definitions"],
                    evaluation_criteria=EvaluationCriteria(
                        exact_match=True,
                        case_sensitive=False
                    )
                )
            except Exception as e:
                # Log error and continue with next word
                import logging
                logging.getLogger(__name__).error(f"Error generating definition for '{correct}': {e}")
                continue

        # If we've exhausted the word list, switch to fully LLM-generated questions
        if len(used_words) >= len(words) - 10:
            # Define schema for full question generation
            full_question_schema = {
                "type": "object",
                "properties": {
                    "word": {"type": "string"},
                    "definition": {"type": "string"},
                    "choices": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 9,
                        "maxItems": 9
                    }
                },
                "required": ["word", "definition", "choices"]
            }
            
            # Generate questions using various difficulty levels and categories
            difficulty_levels = ["easy", "medium", "hard"]
            categories = ["common vocabulary", "academic vocabulary", "technical terms"]
            
            for difficulty in difficulty_levels:
                for category in categories:
                    prompt = f"""
                    Create a word definition question with the following requirements:
                    - Select a {difficulty} {category} word
                    - Write a clear, concise definition for the word
                    - Create 9 distractor words that are reasonable alternatives
                    - All words should be single words (no phrases)
                    - Do not include the target word in its definition
                    """
                    
                    try:
                        response = self.get_llm_question(
                            prompt=prompt,
                            schema=full_question_schema
                        )
                        
                        correct = response["word"]
                        definition = response["definition"]
                        distractors = response["choices"]
                        
                        # Combine correct word and distractors and sort
                        choices = [correct] + distractors
                        choices.sort()
                        
                        # Create question text
                        question_text = f'Which word has this definition: {definition}\n\nThe choices are: {", ".join(choices)}'
                        
                        # Map difficulty string to enum
                        if difficulty == "easy":
                            diff_enum = Difficulty.EASY
                        elif difficulty == "hard":
                            diff_enum = Difficulty.HARD
                        else:
                            diff_enum = Difficulty.MEDIUM
                            
                        # Create and yield question object
                        yield BenchmarkQuestion(
                            question_text=question_text,
                            answer_type=AnswerType.MULTIPLE_CHOICE,
                            correct_answer=correct,
                            choices=choices,
                            category=category,
                            difficulty=diff_enum,
                            tags=["vocabulary", "definitions", category, difficulty],
                            evaluation_criteria=EvaluationCriteria(
                                exact_match=True,
                                case_sensitive=False
                            )
                        )
                    except Exception as e:
                        # Log error and continue with next combination
                        import logging
                        logging.getLogger(__name__).error(f"Error in full LLM generation: {e}")
                        continue