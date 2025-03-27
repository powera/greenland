#!/usr/bin/python3

"""Runner for letter count benchmark."""

import json
import logging
import time
from typing import Dict, List, Optional, Any, Tuple

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.data_models import BenchmarkResult
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@runner("0012_letter_count")
class LetterCountRunner(BenchmarkRunner):
    """Runner for testing a model's ability to count letter occurrences in words."""
    
    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt for letter count question.
        
        Args:
            question_data: Question data from database
            
        Returns:
            Tuple of (prompt, schema, context)
        """
        prompt = question_data.get("question_text", "")
        
        # Define schema for structured response
        schema = {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "The number of times the letter appears in the word"
                }
            },
            "required": ["count"]
        }
        
        # Add context for guidance
        context = """You are performing a letter counting task. 
Count how many times a specific letter appears in a word.
Provide your answer as a single integer in the specified JSON format."""
        
        return prompt, schema, context
        
    def evaluate_response(self, question_data: Dict, response: Any) -> int:
        """
        Evaluate if the count is correct.
        
        Args:
            question_data: Question data from database
            response: Model response (structured dictionary)
            
        Returns:
            Score (100 for correct, 0 for incorrect)
        """
        expected_count = int(question_data.get("correct_answer", 0))
        
        # Extract count from response
        actual_count = None
        if isinstance(response, dict) and "count" in response:
            try:
                actual_count = int(response["count"])
            except (ValueError, TypeError):
                return 0
        else:
            # Try to parse response as a direct number
            try:
                actual_count = int(response)
            except (ValueError, TypeError):
                return 0
                
        # Check for exact match (letter counting should be exact)
        return 100 if actual_count == expected_count else 0
        
    def run(self) -> int:
        """
        Execute the benchmark and return the run ID.
        
        Returns:
            Run ID of the benchmark results
        """
        self.warm_up()
        questions = self.load_questions()
        
        if not questions:
            logger.error("No questions found for benchmark %s", self.metadata.code)
            return -1
            
        logger.info("Running benchmark %s with %d questions on model %s", 
                   self.metadata.code, len(questions), self.model)
                   
        results = []
        
        for i, question_json in enumerate(questions):
            question_data = json.loads(question_json["question_info_json"])
            question_id = question_json["question_id"]
            
            logger.info("Processing question %d/%d: %s", 
                      i+1, len(questions), question_id)
            
            prompt, schema, context = self.prepare_prompt(question_data)
            
            start_time = time.time()
            try:
                # Use structured response format
                response = unified_client.generate_chat(
                    prompt=prompt,
                    model=self.remote_model,
                    json_schema=schema,
                    context=context
                )
                
                eval_time_ms = int((time.time() - start_time) * 1000)
                
                # Extract the count and evaluate
                structured_data = response.structured_data
                score = self.evaluate_response(question_data, structured_data)
                
                results.append(BenchmarkResult(
                    question_id=question_id,
                    score=score,
                    eval_msec=eval_time_ms,
                    debug_json=json.dumps({
                        "prompt": prompt,
                        "response": structured_data,
                        "expected": question_data.get("correct_answer"),
                        "score": score
                    })
                ))
                
            except OllamaTimeoutError as e:
                results.append(self.handle_timeout(question_id, e))
            except Exception as e:
                logger.error("Error processing question %s: %s", question_id, str(e))
                results.append(BenchmarkResult(
                    question_id=question_id,
                    score=0,
                    eval_msec=0,
                    debug_json=json.dumps({"error": str(e)})
                ))
        
        # Calculate overall score based on individual results
        overall_score = self.calculate_score(results)
        
        logger.info("Benchmark %s completed with score %d", 
                   self.metadata.code, overall_score)
                   
        # Save results to database
        run_id = self.save_results(overall_score, results)
        return run_id
