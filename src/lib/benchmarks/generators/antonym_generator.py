#!/usr/bin/python3

"""Generator for antonym benchmark questions."""

import json
import logging
import os
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from clients import ollama_client
from lib.benchmarks.base import BenchmarkGenerator
from lib.benchmarks.data_models import (
    BenchmarkQuestion, AnswerType, Difficulty, EvaluationCriteria
)
from lib.benchmarks.factory import generator, benchmark, get_benchmark_metadata

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Register benchmark metadata
BENCHMARK_CODE = "0016_antonym"
BENCHMARK_NAME = "Antonym Identification"
BENCHMARK_DESCRIPTION = "Tests ability to identify the correct antonym from a list of options."

# Apply benchmark decorator to this module
benchmark(BENCHMARK_CODE, BENCHMARK_NAME, BENCHMARK_DESCRIPTION)(__name__)


@generator(BENCHMARK_CODE)
class AntonymGenerator(BenchmarkGenerator):
    """Generator for antonym benchmark questions."""
    
    def __init__(self, metadata, session: Optional[Session] = None):
        super().__init__(metadata, session)
        # This will be used when generating questions
        self.context = """You are a linguistics assistant. Generate challenging antonym questions that:
1. Include a target word
2. Provide 6 candidate words, only one of which is a true antonym
3. Ensure the other 5 candidates are plausible distractors (synonyms, related words, etc.)
4. Include a mix of easy, medium, and hard difficulty levels"""

    def load_to_database(self) -> None:
        """Load antonym questions into database from JSON files."""
        DIR = os.path.join("benchmarks", "0016_antonym")
        files = sorted(os.listdir(DIR))

        for filename in files:
            if not filename.endswith(".json"):
                continue
                
            with open(os.path.join(DIR, filename)) as f:
                questions_data = json.load(f)
                questions = []
                
                for question_data in questions_data:
                    # Convert to standardized format
                    question = BenchmarkQuestion(
                        question_text=f"What is the antonym of '{question_data['word']}' among these candidates: {', '.join(question_data['candidates'])}",
                        answer_type=AnswerType.JSON,
                        correct_answer={"antonym": question_data["antonym"]},
                        category=question_data.get("category"),
                        difficulty=Difficulty(question_data.get("difficulty", "medium")),
                        choices=question_data["candidates"],
                        schema={
                            "type": "object",
                            "properties": {
                                "antonym": {"type": "string"}
                            },
                            "required": ["antonym"]
                        },
                        evaluation_criteria=EvaluationCriteria(
                            case_sensitive=False,
                            exact_match=True
                        )
                    )
                    questions.append(question)
                
                # Save questions in batch
                word = os.path.splitext(filename)[0]
                self.batch_save_questions(questions, word)
                logger.info(f"Loaded {len(questions)} antonym questions for {word}")

    def generate_batch(self, category: str, difficulty: str, count: int = 10, model: str = "gemma2:9b") -> List[BenchmarkQuestion]:
        """
        Generate a batch of antonym questions.
        
        Args:
            category: Word category (e.g., "adjectives", "verbs")
            difficulty: Difficulty level ("easy", "medium", "hard")
            count: Number of questions to generate
            model: Model to use for generation
            
        Returns:
            List of generated BenchmarkQuestion objects
        """
        # This is a placeholder for future implementation
        # The actual generation would use a language model to create new questions
        
        # Define JSON schema for the generated questions
        schema = {
            "type": "object",
            "properties": {
                "word": {"type": "string"},
                "candidates": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 6,
                    "maxItems": 6
                },
                "antonym": {"type": "string"},
                "difficulty": {
                    "type": "string",
                    "enum": ["easy", "medium", "hard"]
                },
                "category": {"type": "string"}
            },
            "required": ["word", "candidates", "antonym"]
        }
        
        prompt = f"""Generate {count} antonym questions for {category} words at {difficulty} difficulty level.
Each question should have:
1. A target word
2. 6 possible answers (candidates), only one of which is a true antonym
3. The correct antonym identified

Return the results as a JSON array with each item having 'word', 'candidates', 'antonym', 'difficulty', and 'category' fields."""

        response = ollama_client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=schema,
            context=self.context
        )
        
        # Convert the generated data to BenchmarkQuestion objects
        questions = []
        for item in response.structured_data:
            question = BenchmarkQuestion(
                question_text=f"What is the antonym of '{item['word']}' among these candidates: {', '.join(item['candidates'])}",
                answer_type=AnswerType.JSON,
                correct_answer={"antonym": item["antonym"]},
                category=item.get("category"),
                difficulty=Difficulty(item.get("difficulty", difficulty)),
                choices=item["candidates"],
                schema={
                    "type": "object",
                    "properties": {
                        "antonym": {"type": "string"}
                    },
                    "required": ["antonym"]
                },
                evaluation_criteria=EvaluationCriteria(
                    case_sensitive=False,
                    exact_match=True
                )
            )
            questions.append(question)
            
        return questions
