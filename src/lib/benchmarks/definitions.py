#!/usr/bin/python3

"""Word definitions benchmark implementation."""

import json
import logging

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner, BenchmarkResult

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
