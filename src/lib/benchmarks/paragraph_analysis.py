#!/usr/bin/python3

"""Paragraph analysis benchmark implementation."""

import json
import logging

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner, BenchmarkResult

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ParagraphAnalysisBenchmark(BenchmarkRunner):
    """Benchmark for testing paragraph comprehension abilities."""
    
    def __init__(self, model: str):
        super().__init__(model)
        self.context = """You are a reading comprehension assistant. For each passage:
1. Analyze the text carefully
2. Select the best answer from the choices provided
3. Explain your reasoning"""
        
        self.schema = {
            "type": "object",
            "properties": {
                "commentary": {"type": "string"},
                "answer": {"type": "string", "minLength": 1, "maxLength": 1}
            },
            "required": ["commentary", "answer"]
        }
    
    def run(self) -> None:
        """Execute the paragraph analysis benchmark."""
        questions = self.load_questions("0030_analyze_paragraph")
        self.warm_up()
        
        results = []
        for question in questions:
            info = json.loads(question["question_info_json"])
            query = info["query"].removesuffix("\nAnswer: ")
            
            try:
                _, structured_response, perf = unified_client.generate_chat(
                    prompt=query,
                    model=self.remote_model,
                    json_schema=self.schema,
                    context=self.context
                )
                
                try:
                    correct_letter = info["choices"][info["gold"]]
                    is_correct = structured_response["answer"].upper() == correct_letter
                    
                    debug_info = {
                        "response": structured_response,
                        "correct_answer": correct_letter,
                        "question": query
                    } if not is_correct else None
                    
                except (KeyError, TypeError):
                    is_correct = False
                    debug_info = structured_response
                    
                results.append(BenchmarkResult(
                    question["question_id"],
                    is_correct,
                    int(perf.total_msec),
                    json.dumps(debug_info) if debug_info else None
                ))
            except OllamaTimeoutError as e:
                results.append(self.handle_timeout(question["question_id"], e))
            
        score = sum(r.score for r in results) * 10
        self.save_results("0030_analyze_paragraph", score, results)
        print(f"Correct: {score}/{len(questions)}")
