#!/usr/bin/python3

"""Simple haystack benchmark implementation."""

import json
import logging

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner, BenchmarkResult

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SimpleHaystackBenchmark(BenchmarkRunner):
    """Benchmark for testing information retrieval abilities."""

    def __init__(self, model: str):
        super().__init__(model)
        self.context = """You are an information retrieval assistant. For each set of sentences:
1. Find the sentence containing the specified location
2. Identify the subject (person or entity) in that sentence"""
        
        self.schema = {
            "type": "object",
            "properties": {"subject": {"type": "string"}},
            "required": ["subject"]
        }

    def run(self) -> None:
        """Execute the simple haystack benchmark."""
        questions = self.load_questions("0035_simple_haystack")
        self.warm_up()
        
        results = []
        for question in questions:
            info = json.loads(question["question_info_json"])
            sentences = [f"{i+1}. {s}" for i, s in enumerate(info["sentences"])]
            
            prompt = f"""Given these sentences:
{chr(10).join(sentences)}

What is the subject for the sentence where the location is {info["correct"]["location"]}?"""

            try:
                _, structured_response, perf = unified_client.generate_chat(
                    prompt=prompt,
                    model=self.remote_model,
                    json_schema=self.schema,
                    context=self.context
                )
                
                try:
                    is_correct = structured_response["subject"].lower() == info["correct"]["name"].lower()
                except KeyError:
                    is_correct = False
                    
                results.append(BenchmarkResult(
                    question["question_id"],
                    is_correct,
                    int(perf.total_msec),
                    json.dumps(structured_response)
                ))
            except OllamaTimeoutError as e:
                results.append(self.handle_timeout(question["question_id"], e))
            
        score = 4 * sum(r.score for r in results)  # 25 questions
        self.save_results("0035_simple_haystack", score, results)
        print(f"Correct: {score}/{len(questions)}")
