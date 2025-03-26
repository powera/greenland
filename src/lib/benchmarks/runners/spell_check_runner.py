#!/usr/bin/python3

"""Spell check benchmark runner implementation."""

import json
import logging
import time
from typing import Dict, Optional, Tuple, Any

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.data_models import BenchmarkResult, BenchmarkMetadata
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define benchmark code
BENCHMARK_CODE = "0015_spell_check"


@runner(BENCHMARK_CODE)
class SpellCheckRunner(BenchmarkRunner):
    """Runner for evaluating model performance on spell check benchmark."""
    
    def __init__(self, model: str, metadata: BenchmarkMetadata):
        super().__init__(model, metadata)
        self.context = """You are a spell checking assistant. For each sentence, identify:
1. The incorrectly spelled word exactly as it appears
2. The correct spelling of that word"""

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt, schema, and context for the question.
        
        Args:
            question_data: Question data from database
            
        Returns:
            Tuple of (prompt, schema, context)
        """
        question_text = question_data.get("question_text", "")
        schema = question_data.get("schema")
        
        return question_text, schema, self.context
    
    def evaluate_response(self, question_data: Dict, response: Any) -> int:
        """
        Evaluate if a response is correct according to question criteria.
        
        Args:
            question_data: Question data from database
            response: Model response (dictionary with incorrect/correct)
            
        Returns:
            Score (100 for correct, 0 for incorrect)
        """
        if not isinstance(response, dict):
            return 0
            
        correct_answer = question_data.get("correct_answer", {})
        
        # Check if both incorrect and correct fields match
        if (response.get("incorrect", "").lower() == correct_answer.get("incorrect", "").lower() and
            response.get("correct", "").lower() == correct_answer.get("correct", "").lower()):
            return 100
            
        return 0
    
    def run(self) -> int:
        """
        Execute the spell check benchmark.
        
        Returns:
            Run ID of saved results
        """
        questions = self.load_questions()
        self.warm_up()
        
        results = []
        for question in questions:
            question_id = question["question_id"]
            question_data = json.loads(question["question_info_json"])
            
            prompt, schema, context = self.prepare_prompt(question_data)
            
            try:
                start_time = time.time()
                
                response = unified_client.generate_chat(
                    prompt=prompt,
                    model=self.remote_model,
                    json_schema=schema,
                    context=context
                )
                
                eval_time = int((time.time() - start_time) * 1000)
                
                # Evaluate the response
                score = self.evaluate_response(question_data, response.structured_data)
                
                results.append(BenchmarkResult(
                    question_id=question_id,
                    score=score,
                    eval_msec=eval_time,
                    debug_json=json.dumps({
                        "response": response.structured_data,
                        "expected": question_data.get("correct_answer")
                    })
                ))
                
            except OllamaTimeoutError as e:
                results.append(self.handle_timeout(question_id, e))
                
            except Exception as e:
                logger.error(f"Error processing question {question_id}: {str(e)}")
                results.append(BenchmarkResult(
                    question_id=question_id,
                    score=0,
                    eval_msec=0,
                    debug_json=json.dumps({"error": str(e)})
                ))

        # Calculate overall score
        overall_score = self.calculate_score(results)
        logger.info(f"Spell check benchmark completed. Score: {overall_score}/100")
        
        # Save results and get run ID
        run_id = self.save_results(overall_score, results)
        return run_id
