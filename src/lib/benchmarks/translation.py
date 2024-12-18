#!/usr/bin/python3

"""Translation benchmark implementation."""

import json
import logging
from typing import Dict

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner, BenchmarkResult

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TranslationBenchmark(BenchmarkRunner):
    """Benchmark for testing language translation abilities."""
    
    def __init__(self, model: str, origin_lang: str, target_lang: str):
        """
        Initialize benchmark runner with model and language pair.
        
        Args:
            model: Name of the model to test
            origin_lang: Source language code (fr, de, ind, sw, ko, kn, zh)
            target_lang: Target language code (en, fr, de, ind, sw, ko, kn, zh)
        """
        super().__init__(model)
        self.origin_lang = origin_lang
        self.target_lang = target_lang
        
        # Validate language codes
        valid_langs = {'en', 'fr', 'de', 'ind', 'sw', 'ko', 'kn', 'zh'}
        if origin_lang not in valid_langs or target_lang not in valid_langs:
            raise ValueError(f"Language codes must be one of: {', '.join(valid_langs)}")
        if origin_lang == target_lang:
            raise ValueError("Origin and target languages must be different")
            
    @property
    def benchmark_codename(self) -> str:
        """Get unique benchmark codename for this language pair."""
        return f"0050_translation_{self.origin_lang}_{self.target_lang}"
    
    def run(self) -> None:
        """Execute the translation benchmark."""
        questions = self.load_questions(self.benchmark_codename)
        self.warm_up()
        
        schema = {
            "type": "object",
            "properties": {
                "translation": {"type": "string"}
            },
            "required": ["translation"]
        }
        
        # Set task context
        context = f"""You are helping with a language translation task.
When translating a word from {self.origin_lang.upper()} to {self.target_lang.upper()}:
- Provide the most direct and common translation
- Give only the base form of the word
- Do not include articles unless they are part of the standard translation
- Do not provide explanations or alternative translations"""
        
        results = []
        for question in questions:
            info = json.loads(question["question_info_json"])
            
            prompt = f"""Translate this word: "{info['word']}" """
            if info.get("choices"):
                prompt += f"\nPossible translations: {', '.join(info['choices'])}"

            try:
                _, structured_response, perf = unified_client.generate_chat(
                    prompt,
                    self.remote_model,
                    json_schema=schema,
                    context=context
                )
                
                try:
                    translated = structured_response["translation"].lower().strip()
                    
                    # Get correct answer based on target language
                    correct = info[self.target_lang].lower()
                    
                    # If choices are provided, validate against them
                    if info.get("choices"):
                        is_correct = translated in [c.lower() for c in info["choices"]] and translated == correct
                    else:
                        is_correct = translated == correct
                        
                    debug_info = None if is_correct else {
                        "response": structured_response["translation"],
                        "expected": info[self.target_lang]
                    }
                    
                    # Include any relevant usage details in debug info
                    if debug_info and info.get("origin_details"):
                        debug_info["origin_word_details"] = info["origin_details"]
                    if debug_info and info.get("target_details"):
                        debug_info["target_word_details"] = info["target_details"]
                except (json.JSONDecodeError, KeyError):
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

        score = sum(r.score for r in results) * 2
        if score > 100: score=100  # 51 questions
        self.save_results(self.benchmark_codename, score, results)
        print(f"Correct: {score}/{len(questions)}")
