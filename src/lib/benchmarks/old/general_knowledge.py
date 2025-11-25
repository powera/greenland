#!/usr/bin/python3

"""General knowledge benchmark implementation."""

import json
import logging

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner, BenchmarkResult

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class GeneralKnowledgeBenchmark(BenchmarkRunner):
    """Benchmark for testing general knowledge abilities."""

    def __init__(self, model: str):
        super().__init__(model)
        self.context = """You are a knowledgeable assistant providing concise, factual answers.
Respond with just the answer - do not include explanations or additional context."""
    
    def run(self) -> None:
        """Execute the general knowledge benchmark."""
        questions = self.load_questions("0040_general_knowledge")
        self.warm_up()
        
        results = []
        for question in questions:
            info = json.loads(question["question_info_json"])
            try:
                free_response, _, perf = unified_client.generate_chat(
                    prompt=info["context"],
                    model=self.remote_model,
                    context=self.context
                )
                
                is_correct = info["continuation"] in free_response
                debug_info = None if is_correct else {
                    "response": free_response,
                    "expected": info["continuation"]
                }
                
                results.append(BenchmarkResult(
                    question["question_id"],
                    is_correct,
                    int(perf.total_msec),
                    json.dumps(debug_info) if debug_info else None
                ))
            except OllamaTimeoutError as e:
                results.append(self.handle_timeout(question["question_id"], e))
            
        score = sum(r.score for r in results)
        self.save_results("0040_general_knowledge", score, results)
        print(f"Correct: {score}/{len(questions)}")
