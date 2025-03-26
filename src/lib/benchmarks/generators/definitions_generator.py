#!/usr/bin/python3

"""Word definitions benchmark generator implementation."""

import json
import logging
import random
from typing import Dict, List, Optional

from clients import unified_client, ollama_client
from lib.benchmarks.base import BenchmarkGenerator
from lib.benchmarks.data_models import (
    BenchmarkQuestion, BenchmarkMetadata, 
    AnswerType, Difficulty, EvaluationCriteria
)
from lib.benchmarks.factory import generator, benchmark
import lib.validation

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

    def generate_question(self, model: str = "gemma2:9b") -> BenchmarkQuestion:
        """
        Generate a single definition question.
        
        Args:
            model: Model to use for generating the definition
            
        Returns:
            BenchmarkQuestion object
        """
        # Load word list
        with open("benchmarks/0020_definitions/wordlist.txt") as f:
            words = [line.strip().lower() for line in f]

        # Select words for this question
        choices = random.sample(words, 10)
        correct = choices[0]
        choices.sort()  # Sort for consistent presentation

        # Generate definition using the specified model
        prompt = f'Define the word "{correct}"'
        
        response = ollama_client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=self.schema,
            context=self.context
        )
        
        definition = response.structured_data["definition"]

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

    def generate_validated_question(self, model: str = "gemma2:9b", max_attempts: int = 3) -> BenchmarkQuestion:
        """
        Generate a question with validated definition.
        
        Args:
            model: Model to use for generating the definition
            max_attempts: Maximum number of generation attempts
            
        Returns:
            Validated BenchmarkQuestion object
            
        Raises:
            ValueError: If unable to generate a valid question
        """
        for attempt in range(max_attempts):
            question = self.generate_question(model)
            
            # Extract definition and correct word from the question
            definition = question.question_text.split("\n\n")[0].replace("Which word has this definition: ", "")
            correct_word = question.correct_answer
            
            # Validate the definition
            validation = lib.validation.validate_definition(
                definition,
                correct_word
            )

            if validation.valid:
                return question

            logger.info(f"Attempt {attempt + 1} failed validation: {validation}")

        raise ValueError(f"Failed to generate valid definition after {max_attempts} attempts")

    def load_to_database(self, count: int = 100, model: str = "gemma2:9b") -> None:
        """
        Load generated definition questions into database.
        
        Args:
            count: Number of questions to generate
            model: Model to use for generating definitions
        """
        logger.info(f"Generating {count} definition questions using {model}...")
        
        questions = []
        for idx in range(count):
            try:
                question = self.generate_validated_question(model)
                questions.append(question)
                logger.info(f"Generated question {idx+1}/{count}: {question.correct_answer}")
            except ValueError as e:
                logger.error(f"Failed to generate question {idx+1}: {e}")
                
        # Save all questions with batch ID
        batch_id = f"batch_{model.replace(':', '_')}"
        question_ids = self.batch_save_questions(questions, batch_id)
        
        logger.info(f"Successfully saved {len(question_ids)} questions to database")
        return question_ids
