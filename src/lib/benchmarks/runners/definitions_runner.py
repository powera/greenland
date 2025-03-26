#!/usr/bin/python3

"""Word definitions benchmark runner implementation."""

import json
import logging
from typing import Dict, List, Optional, Tuple, Any

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.data_models import (
    BenchmarkQuestion, BenchmarkResult, BenchmarkMetadata,
    AnswerType, Difficulty
)
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@runner("0020_definitions")
class DefinitionsRunner(BenchmarkRunner):
    """Runner for testing word definition abilities."""

    def __init__(self, model: str, metadata: BenchmarkMetadata):
        """Initialize runner with model name and benchmark metadata."""
        super().__init__(model, metadata)
        self.context = """You are taking a vocabulary test. Your task is to select the word that best matches 
a given definition from a list of choices. Respond with only the correct word, nothing else."""

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt and context for the definitions question.
        
        Args:
            question_data: Question data from database
            
        Returns:
            Tuple of (prompt, schema, context)
        """
        # Question data already contains the formatted question text
        prompt = question_data.get("question_text", "")
        
        # No schema needed for this benchmark
        schema = None
        
        return prompt, schema, self.context
        
    def evaluate_response(self, question_data: Dict, response: str) -> bool:
        """
        Evaluate if a response matches the correct word.
        
        Args:
            question_data: Question data from database
            response: Model response text
            
        Returns:
            Boolean indicating whether response is correct
        """
        correct_answer = question_data.get("correct_answer", "").lower()
        
        # Clean and normalize the response
        cleaned_response = response.strip().lower()
        # Remove any punctuation at the end
        cleaned_response = cleaned_response.rstrip(".,;:!?")
        
        # Check if response contains the correct word
        return cleaned_response == correct_answer
        
    def process_question(self, question: Dict) -> BenchmarkResult:
        """
        Process a single benchmark question.
        
        Args:
            question: Question data from database
            
        Returns:
            BenchmarkResult object
        """
        question_data = json.loads(question["question_info_json"])
        question_id = question["question_id"]
        
        try:
            # Prepare the prompt
            prompt, schema, context = self.prepare_prompt(question_data)
            
            # Generate response
            response = unified_client.generate_chat(
                prompt=prompt,
                model=self.remote_model,
                brief=True,
                context=context
            )
            
            # Evaluate response
            is_correct = self.evaluate_response(question_data, response.response_text)
            
            # Return benchmark result
            return BenchmarkResult(
                question_id=question_id,
                score=100 if is_correct else 0,
                eval_msec=int(response.usage.total_msec),
                debug_json=json.dumps({
                    "response": response.response_text,
                    "correct_answer": question_data.get("correct_answer"),
                    "is_correct": is_correct
                })
            )
            
        except OllamaTimeoutError as e:
            return self.handle_timeout(question_id, e)
        except Exception as e:
            logger.error(f"Error processing question {question_id}: {e}")
            return BenchmarkResult(
                question_id=question_id,
                score=0,
                eval_msec=0,
                debug_json=json.dumps({"error": str(e)})
            )

    def run(self) -> int:
        """
        Execute the definitions benchmark.
        
        Returns:
            Run ID of the saved results
        """
        # Load questions for this benchmark
        questions = self.load_questions()
        if not questions:
            logger.error(f"No questions found for benchmark {self.metadata.code}")
            return -1
            
        # Warm up the model
        logger.info(f"Warming up model {self.model}...")
        self.warm_up()
        
        # Process each question
        logger.info(f"Running benchmark with {len(questions)} questions...")
        results = []
        for idx, question in enumerate(questions):
            logger.info(f"Processing question {idx+1}/{len(questions)}: {question['question_id']}")
            result = self.process_question(question)
            results.append(result)
            
        # Calculate score
        score = self.calculate_score(results)
        logger.info(f"Benchmark complete. Score: {score}/100 ({sum(1 for r in results if r.score == 100)}/{len(results)} correct)")
        
        # Save results to database
        run_id = self.save_results(score, results)
        logger.info(f"Results saved with run ID: {run_id}")
        
        return run_id
