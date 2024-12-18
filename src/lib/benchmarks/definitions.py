#!/usr/bin/python3

"""Word definitions benchmark implementation."""

import json
import logging
import random
from typing import Dict, Optional
from sqlalchemy.orm import Session

from clients import unified_client, ollama_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner, BenchmarkResult, BenchmarkGenerator
import lib.validation

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DefinitionsGenerator(BenchmarkGenerator):
    """Generator for definitions benchmark questions."""

    def __init__(self, session: Optional[Session] = None):
        super().__init__(session)
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

    def generate_question(self, model: str = "gemma2:9b") -> Dict:
        """Generate a single definition question."""
        with open("benchmarks/0020_definitions/wordlist.txt") as f:
            words = [line.strip().lower() for line in f]

        choices = random.sample(words, 10)
        correct = choices[0]
        choices.sort()

        prompt = f'Define the word "{correct}"'
        
        _, structured_response, _ = ollama_client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=self.schema,
            context=self.context
        )
        
        definition = structured_response["definition"]

        question = f'Which word has this definition: {definition}\n\nThe choices are: {", ".join(choices)}'

        return {
            "question": question,
            "definition": definition,
            "correct": correct,
            "choices": choices
        }

    def generate_validated_question(self, model: str = "gemma2:9b", max_attempts: int = 3) -> Dict:
        """Generate a question with validated definition."""
        for attempt in range(max_attempts):
            question = self.generate_question(model)
            validation = lib.validation.validate_definition(
                question["definition"],
                question["correct"]
            )

            if validation.valid:
                return question

            print(f"Attempt {attempt + 1} failed validation:")
            print(json.dumps(vars(validation), indent=2))

        raise ValueError(f"Failed to generate valid definition after {max_attempts} attempts")

    def load_to_database(self) -> None:
        """Load generated definition questions into database."""
        for idx in range(100):
            question = self.generate_validated_question()
            self.save_question(
                f"0020:{question['correct']}:{idx}",
                "0020_definitions",
                question
            )

class DefinitionsBenchmark(BenchmarkRunner):
    """Benchmark for testing word definition abilities."""

    def run(self) -> None:
        """Execute the definitions benchmark."""
        questions = self.load_questions("0020_definitions")
        self.warm_up()
        
        results = []
        for question in questions:
            info = json.loads(question["question_info_json"])
            try:
                free_response, _, perf = unified_client.generate_chat(
                    info["question"],
                    self.remote_model,
                    brief=True
                )
                
                is_correct = free_response.strip().strip(".").lower() == info["correct"]
                results.append(BenchmarkResult(
                    question["question_id"],
                    is_correct,
                    int(perf.total_msec),
                    None if is_correct else free_response
                ))
            except OllamaTimeoutError as e:
                results.append(self.handle_timeout(question["question_id"], e))
            
        score = sum(r.score for r in results)
        self.save_results("0020_definitions", score, results)
        print(f"Correct: {score}/{len(questions)}")
