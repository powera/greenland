#!/usr/bin/python3

"""Spell check benchmark implementation."""

import json
import logging
import os
from typing import Dict, Optional
from sqlalchemy.orm import Session

from clients import unified_client, ollama_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner, BenchmarkResult, BenchmarkGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SpellCheckGenerator(BenchmarkGenerator):
    """Generator for spell check benchmark questions."""
    
    def __init__(self, session: Optional[Session] = None):
        super().__init__(session)
        self.context = """You are a creative writing assistant. Write a natural-sounding sentence that:
1. Uses the specified word as its subject or object
2. Introduces a spelling error in that word
3. Maintains proper grammar and natural flow aside from the misspelling
4. Is written at roughly an 8th grade reading level"""

    def generate_sentence(self, start_word: str, model: str = "gemma2:9b") -> str:
        """Generate a sentence using start_word but spelled incorrectly."""
        prompt = f"Write a sentence using the word '{start_word}', but spell it incorrectly."
        
        free_response, _, _ = ollama_client.generate_chat(
            prompt=prompt,
            model=model,
            context=self.context
        )
            
        return free_response.strip()

    def generate_batch(self, start_word: str) -> None:
        """Generate 10 sentences for a given word."""
        sentences = []
        for _ in range(10):
            sentence = self.generate_sentence(start_word)
            sentences.append({
                "sentence": sentence,
                "incorrect": "",  # To be filled in by human annotator
                "correct": start_word
            })

        with open(f"benchmarks/0015_spell_check/{start_word}.json", "w") as f:
            json.dump(sentences, f, indent=2)

    def load_to_database(self) -> None:
        """Load generated spell check questions into database."""
        DIR = os.path.join("benchmarks", "0015_spell_check")
        files = sorted(os.listdir(DIR))

        idx = 0
        for filename in files:
            if not filename.endswith(".json"):
                continue
                
            with open(os.path.join(DIR, filename)) as f:
                sentences = json.load(f)
                for sentence in sentences:
                    self.save_question(
                        f"0015:{sentence['correct']}:{idx}",
                        "0015_spell_check",
                        sentence
                    )
                    idx += 1

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
                response = unified_client.generate_chat(
                    prompt=prompt,
                    model=self.remote_model,
                    json_schema=self.schema,
                    context=self.context
                )
                
                is_correct = (info["incorrect"] == response.structured_data["incorrect"] and 
                             info["correct"] == response.structured_data["correct"])
                
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
