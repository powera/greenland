#!/usr/bin/python3

"""Word definitions benchmark generator implementation."""

import random
from typing import List

from lib.benchmarks.base import BenchmarkGenerator
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
        self.context = """You are a lexicographer writing clear, concise definitions. For each word:
1. Write a single-sentence definition
2. Do not use the word itself in the definition
3. Focus on the most common meaning of the word
4. Use simple, clear language"""
        
        self.schema = {
            "type": "object",
            "properties": {
                "definition": {"type": "string"},
                "explanation": {"type": "string"},
            },
            "required": ["definition"],
        }

    def generate_question(self) -> BenchmarkQuestion:
        """
        Generate a single definition question.
        
        Returns:
            BenchmarkQuestion object
        """
        # Load word list
        try:
            words = self.load_text_file("wordlist.txt")
        except FileNotFoundError:
            # Fallback to a small set of common words if file is not found
            words = [
                "apple", "banana", "computer", "dog", "elephant", "freedom",
                "garden", "happiness", "internet", "journey", "knowledge", "language",
                "mountain", "notebook", "ocean", "patience", "question", "rainbow",
                "science", "technology", "umbrella", "variety", "window", "xylophone",
                "yesterday", "zebra"
            ]

        # Select words for this question
        choices = random.sample(words, 10)
        correct = choices[0]
        choices.sort()  # Sort for consistent presentation

        # Generate definition using the LLM generation helper from base.py
        prompt = f'Define the word "{correct}"'
        
        response = self.generate_llm_question(
            prompt=prompt,
            schema=self.schema
        )

        definition = response["definition"]

        # Create question text
        question_text = f'Which word has this definition: {definition}\n\nThe choices are: {", ".join(choices)}'

        # Create and return question object
        return BenchmarkQuestion(
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