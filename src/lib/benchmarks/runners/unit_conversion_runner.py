#!/usr/bin/python3

"""Runner for unit conversion benchmark."""

import json
import logging
import time
import re
from typing import Dict, List, Optional, Any, Tuple

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.data_models import (
    BenchmarkResult, BenchmarkMetadata, AnswerType
)
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Benchmark code
BENCHMARK_CODE = "0022_unit_conversion"

@runner(BENCHMARK_CODE)
class UnitConversionRunner(BenchmarkRunner):
    """Runner for unit conversion benchmark."""
    
    def __init__(self, model: str, metadata: BenchmarkMetadata):
        """Initialize runner with model name."""
        super().__init__(model, metadata)
    
    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """Prepare the prompt for unit conversion questions."""
        # Ensure we're getting the expected question format
        question_text = question_data.get("question_text", "")
        
        # Create JSON schema for structured response
        schema = {
            "type": "object",
            "properties": {
                "value": {
                    "type": "number",
                    "description": "The numerical value of the conversion result"
                },
                "unit": {
                    "type": "string",
                    "description": "The unit of the conversion result"
                }
            },
            "required": ["value"],
            "additionalProperties": False
        }
        
        # Add context to guide the model
        context = """You are performing unit conversions. 
        Convert the units as accurately as possible.
        For numerical answers, aim for at most 2 decimal places of precision unless greater precision is necessary.
        Return the value as a numerical value (not text) and provide the unit of the result."""
        
        return question_text, schema, context
    
    def evaluate_response(self, question_data: Dict, response: Any) -> Tuple[bool, int]:
        """
        Evaluate if the response is correct.
        
        Args:
            question_data: Question data from database
            response: Model response (structured with "value" field)
            
        Returns:
            Tuple of (is_correct, score)
        """
        # Get the expected answer from question data
        expected_answer = float(question_data.get("correct_answer", 0))
        
        # Get evaluation criteria
        eval_criteria = question_data.get("evaluation_criteria", {})
        tolerance = float(eval_criteria.get("tolerance", 0.1))
        
        # Extract the answer from the response
        if isinstance(response, dict) and "value" in response:
            # Structured response
            try:
                actual_answer = float(response["value"])
            except (ValueError, TypeError):
                logger.warning(f"Invalid numeric response: {response}")
                return False, 0
        else:
            # Try to extract a number from text
            try:
                # First check if response is directly a number
                actual_answer = float(response)
            except (ValueError, TypeError):
                # Otherwise parse text to find the number
                if isinstance(response, str):
                    # Extract the first number from the response
                    numbers = re.findall(r"[-+]?\d*\.\d+|\d+", response)
                    if numbers:
                        try:
                            actual_answer = float(numbers[0])
                        except (ValueError, TypeError):
                            logger.warning(f"Could not extract number from: {response}")
                            return False, 0
                    else:
                        logger.warning(f"No numbers found in: {response}")
                        return False, 0
                else:
                    logger.warning(f"Unexpected response type: {type(response)}")
                    return False, 0
        
        # Compare the answers
        logger.info(f"Comparing actual {actual_answer} with expected {expected_answer}, tolerance {tolerance}")
        
        # Check if within tolerance
        if abs(actual_answer - expected_answer) <= tolerance:
            return True, 100
        
        # If not correct but close, give partial score
        if abs(actual_answer - expected_answer) <= tolerance * 3:
            return False, 50
        
        return False, 0
    
    def run(self) -> int:
        """Execute the benchmark and return the run ID."""
        # Warm up model first
        self.warm_up()
        
        # Load questions
        questions = self.load_questions()
        logger.info(f"Loaded {len(questions)} questions for benchmark {self.metadata.code}")
        
        if not questions:
            logger.error(f"No questions found for benchmark {self.metadata.code}")
            return -1
        
        # Track results
        results = []
        
        # Run each question
        for question in questions:
            question_id = question["question_id"]
            question_data = json.loads(question["question_info_json"])
            
            try:
                # Prepare prompt, schema and context
                prompt, schema, context = self.prepare_prompt(question_data)
                
                # Log the question
                logger.info(f"Running question {question_id}: {prompt}")
                
                # Measure time
                start_time = time.time()
                
                # Get response from model
                response = unified_client.generate_chat(
                    prompt=prompt,
                    model=self.remote_model,
                    json_schema=schema,
                    context=context
                )
                
                # Calculate duration
                duration_ms = int((time.time() - start_time) * 1000)
                
                # Get response data
                structured_data = response.structured_data
                
                # Evaluate response
                is_correct, score = self.evaluate_response(question_data, structured_data)
                
                # Create result
                result = BenchmarkResult(
                    question_id=question_id,
                    score=score,
                    eval_msec=duration_ms,
                    debug_json=json.dumps({
                        "prompt": prompt,
                        "response": structured_data,
                        "expected": question_data.get("correct_answer"),
                        "tolerance": question_data.get("evaluation_criteria", {}).get("tolerance", 0.1),
                        "is_correct": is_correct,
                        "score": score
                    })
                )
                
                # Add to results
                results.append(result)
                
                # Log result
                logger.info(f"Question {question_id}: {'CORRECT' if is_correct else 'INCORRECT'}, score: {score}")
                
            except OllamaTimeoutError as e:
                # Handle timeout
                result = self.handle_timeout(question_id, e)
                results.append(result)
                logger.warning(f"Timeout for question {question_id}")
                
            except Exception as e:
                # Handle other errors
                logger.error(f"Error processing question {question_id}: {str(e)}")
                results.append(BenchmarkResult(
                    question_id=question_id,
                    score=0,
                    eval_msec=0,
                    debug_json=json.dumps({"error": str(e)})
                ))
        
        # Calculate overall score
        overall_score = self.calculate_score(results)
        logger.info(f"Overall score for {self.model} on {self.metadata.code}: {overall_score}")
        
        # Save results to database
        run_id = self.save_results(overall_score, results)
        logger.info(f"Saved results as run ID: {run_id}")
        
        return run_id
