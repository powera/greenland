#!/usr/bin/python3

"""Runner for antonym benchmark."""

import json
import logging
from typing import Dict, Optional, Tuple

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner, BenchmarkResult
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define benchmark code for this runner
BENCHMARK_CODE = "0016_antonym"


@runner(BENCHMARK_CODE)
class AntonymRunner(BenchmarkRunner):
    """Benchmark for testing antonym identification abilities."""
    
    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt and context for antonym questions.
        
        Args:
            question_data: Question data from database
            
        Returns:
            Tuple of (prompt, schema, context)
        """
        prompt = question_data["question_text"]
        schema = question_data.get("schema", {
            "type": "object",
            "properties": {
                "antonym": {"type": "string"}
            },
            "required": ["antonym"]
        })
        
        context = """You are a linguistics assistant. For each question, identify which word from the provided 
candidates is the antonym of the given word. Respond with only the antonym word."""
        
        return prompt, schema, context
    
    def run(self) -> int:
        """
        Execute the antonym benchmark.
        
        Returns:
            Run ID if successful, -1 otherwise
        """
        questions = self.load_questions()
        if not questions:
            logger.error("No questions found for benchmark %s", self.metadata.code)
            return -1
            
        self.warm_up()
        logger.info("Running antonym benchmark for model %s with %d questions", 
                   self.model, len(questions))
        
        results = []
        for question in questions:
            question_data = json.loads(question["question_info_json"])
            prompt, schema, context = self.prepare_prompt(question_data)
            
            try:
                # Generate response
                response = unified_client.generate_chat(
                    prompt=prompt,
                    model=self.remote_model,
                    json_schema=schema,
                    context=context
                )
                
                is_correct = self.evaluate_response(question_data, response.structured_data)
                
                # Create debug info
                debug_info = {
                    "model_answer": response.structured_data.get("antonym", ""),
                    "correct_answer": question_data["correct_answer"].get("antonym", ""),
                    "is_correct": is_correct
                }
                
                results.append(BenchmarkResult(
                    question_id=question["question_id"],
                    score=100 if is_correct else 0,  # 100 for correct, 0 for incorrect
                    eval_msec=int(response.usage.total_msec),
                    debug_json=json.dumps(debug_info)
                ))
                
            except OllamaTimeoutError as e:
                results.append(self.handle_timeout(question["question_id"], e))

        # Calculate overall score (percentage of correct answers)
        score = self.calculate_score(results)
        
        # Save results
        run_id = self.save_results(score, results)
        
        # Log summary
        correct_count = sum(1 for r in results if r.score == 100)
        logger.info("Antonym benchmark completed for %s: %d/%d correct (%.1f%%)",
                   self.model, correct_count, len(results), score)
        
        return run_id
