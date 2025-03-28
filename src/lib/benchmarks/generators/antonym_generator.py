#!/usr/bin/python3

"""Generator for antonym benchmark questions."""

import logging
from typing import Optional, List

from sqlalchemy.orm import Session

from lib.benchmarks.base import BenchmarkGenerator
from lib.benchmarks.data_models import (
    BenchmarkQuestion, AnswerType, Difficulty, EvaluationCriteria
)
from lib.benchmarks.factory import generator, benchmark

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
        self.context = """You are a linguistics assistant. Generate challenging antonym questions that:
1. Include a target word
2. Provide 6 candidate words, only one of which is a true antonym
3. Ensure the other 5 candidates are plausible distractors (synonyms, related words, etc.)
4. Include a mix of easy, medium, and hard difficulty levels"""

    def generate_question(self, category: str = "general", difficulty: str = "medium") -> BenchmarkQuestion:
        """
        Generate a single antonym question.
        
        Args:
            category: Word category (e.g., "adjectives", "verbs")
            difficulty: Difficulty level ("easy", "medium", "hard")
            
        Returns:
            BenchmarkQuestion object
        """
        # Define schema for question generation
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
        
        prompt = f"""Generate a single antonym question for a {category} word at {difficulty} difficulty level.
The question should have:
1. A target word
2. 6 possible answers (candidates), only one of which is a true antonym
3. The correct antonym identified within the candidates list

Return as a JSON object with 'word', 'candidates', 'antonym', 'difficulty', and 'category' fields."""

        # Use the LLM-based generation provided by the base class
        item = self.generate_llm_question(prompt=prompt, schema=schema)
        
        # Convert to BenchmarkQuestion format
        return BenchmarkQuestion(
            question_text=f"What is the antonym of '{item['word']}' among these candidates: {', '.join(item['candidates'])}",
            answer_type=AnswerType.JSON,
            correct_answer={"antonym": item["antonym"]},
            category=item.get("category", category),
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

    def load_to_database(self, num_questions: int = 40) -> List[str]:
        """
        Load antonym questions into database.
        
        Try to load from JSON files first, and if that fails, generate questions.
        
        Args:
            num_questions: Number of questions to generate if files not found
            
        Returns:
            List of question IDs
        """
        try:
            # Try to load questions from JSON files
            questions = []
            categories = ["adjectives", "verbs"]
            
            for category in categories:
                try:
                    # Load data from JSON files
                    questions_data = self.load_json_file(f"{category}.json")
                    
                    for item in questions_data:
                        question = BenchmarkQuestion(
                            question_text=f"What is the antonym of '{item['word']}' among these candidates: {', '.join(item['candidates'])}",
                            answer_type=AnswerType.JSON,
                            correct_answer={"antonym": item["antonym"]},
                            category=item.get("category", category),
                            difficulty=Difficulty(item.get("difficulty", "medium")),
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
                    
                    logger.info(f"Loaded {len(questions_data)} questions from {category}.json")
                except FileNotFoundError:
                    logger.warning(f"File {category}.json not found.")
            
            # If we got questions from files, save them
            if questions:
                return self.batch_save_questions(questions)
                
        except Exception as e:
            logger.error(f"Error loading from files: {str(e)}")
        
        # If we get here, either there was an error or no files were found
        # Fall back to generating questions
        logger.info(f"Generating {num_questions} antonym questions...")
        
        # Generate questions with a mix of categories and difficulties
        categories = ["adjectives", "verbs", "nouns", "adverbs"]
        difficulties = ["easy", "medium", "hard"]
        
        questions = []
        for i in range(num_questions):
            category = categories[i % len(categories)]
            difficulty = difficulties[(i // len(categories)) % len(difficulties)]
            
            try:
                # Generate a validated question
                question = self.generate_validated_question(
                    category=category,
                    difficulty=difficulty
                )
                questions.append(question)
                logger.info(f"Generated question {i+1}/{num_questions}: {category}, {difficulty}")
            except Exception as e:
                logger.error(f"Error generating question {i+1}: {str(e)}")
        
        # Save generated questions
        return self.batch_save_questions(questions)