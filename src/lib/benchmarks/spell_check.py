#!/usr/bin/python3

"""Spell check benchmark implementation."""

import json
import logging

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner, BenchmarkResult

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SpellCheckBenchmark(BenchmarkRunner):
    """Benchmark for testing spell checking abilities."""
    
    def __init__(self, model: str):
        super().__init__(model)
        self.context = """You are a spell checking assistant. For each sentence, identify:
1. The incorrectly spelled word exactly as it appears
2. The correct spelling of that word"""
        
        self.schema = {
            "type": "object",
            "properties": {
                "incorrect": {"type": "string"},
                "correct": {"type": "string"},
            },
            "required": ["incorrect", "correct"],
        }
    
    def run(self) -> None:
        """Execute the spell check benchmark."""
        questions = self.load_questions("0015_spell_check")
        self.warm_up()
        
        results = []
        for question in questions:
            info = json.loads(question["question_info_json"])
            prompt = f"What is the incorrectly-spelled word in this sentence: {info['sentence']}"
            
            try:
                _, structured_response, perf = unified_client.generate_chat(
                    prompt=prompt,
                    model=self.remote_model,
                    json_schema=self.schema,
                    context=self.context
                )
                
                is_correct = (info["incorrect"] == structured_response["incorrect"] and 
                             info["correct"] == structured_response["correct"])
                
                results.append(BenchmarkResult(
                    question["question_id"],
                    is_correct,
                    int(perf.total_msec),
                    json.dumps(structured_response)
                ))
            except OllamaTimeoutError as e:
                results.append(self.handle_timeout(question["question_id"], e))

        score = sum(r.score for r in results)
        self.save_results("0015_spell_check", score, results)
        print(f"Correct: {score}/{len(questions)}")
