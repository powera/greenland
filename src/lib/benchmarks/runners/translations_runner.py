#!/usr/bin/python3

"""Translation benchmark runner implementation."""

import json
import logging
from typing import Dict, List, Optional

from clients import unified_client
from clients.ollama_client import OllamaTimeoutError
from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.data_models import (
    BenchmarkResult, BenchmarkMetadata, AnswerType
)
from lib.benchmarks.factory import runner, get_benchmark_metadata, benchmark
from lib.benchmarks.generators.translations_generator import VALID_LANGS, get_translation_metadata

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@runner("0050_translation")
class TranslationRunner(BenchmarkRunner):
    """Runner for translation benchmark."""
    
    def __init__(self, model: str, metadata: BenchmarkMetadata):
        """
        Initialize benchmark runner with model and metadata.
        
        Args:
            model: Name of the model to test
            metadata: Benchmark metadata
        """
        super().__init__(model, metadata)
        
        # Extract language codes from metadata code
        parts = metadata.code.split('_')
        if len(parts) >= 3:
            lang_parts = parts[2].split('_')
            if len(lang_parts) >= 2:
                self.origin_lang = lang_parts[0]
                self.target_lang = lang_parts[1]
            else:
                raise ValueError(f"Invalid metadata code format: {metadata.code}")
        else:
            raise ValueError(f"Invalid metadata code format: {metadata.code}")
        
        # Validate language codes
        if self.origin_lang not in VALID_LANGS or self.target_lang not in VALID_LANGS:
            raise ValueError(f"Language codes must be one of: {', '.join(VALID_LANGS)}")
        if self.origin_lang == self.target_lang:
            raise ValueError("Origin and target languages must be different")
    
    def get_system_context(self) -> str:
        """Get system context for translation task."""
        return f"""You are helping with a language translation task.
When translating a word from {self.origin_lang.upper()} to {self.target_lang.upper()}:
- Provide the most direct and common translation
- Give only the base form of the word
- Do not include articles unless they are part of the standard translation
- Do not provide explanations or alternative translations"""
    
    def create_language_pair_runner(model: str, origin_lang: str, target_lang: str) -> 'TranslationRunner':
        """
        Create a runner for a specific language pair.
        
        Args:
            model: Model name to benchmark
            origin_lang: Source language code
            target_lang: Target language code
            
        Returns:
            TranslationRunner for the specific language pair
        """
        metadata = get_translation_metadata(origin_lang, target_lang)
        return TranslationRunner(model, metadata)
    
    def run(self) -> int:
        """
        Execute the translation benchmark.
        
        Returns:
            Run ID of the saved results
        """
        # Load questions from database
        questions = self.load_questions()
        if not questions:
            logger.error(f"No questions found for benchmark {self.metadata.code}")
            return -1
            
        # Warm up model
        self.warm_up()
        
        # Define response schema
        schema = {
            "type": "object",
            "properties": {
                "translation": {"type": "string"}
            },
            "required": ["translation"]
        }
        
        # Get system context
        context = self.get_system_context()
        
        # Process each question
        results = []
        for question_data in questions:
            # Parse question info
            question_id = question_data["question_id"]
            question_info = json.loads(question_data["question_info_json"])
            
            # Extract question text and correct answer
            question_text = question_info.get("question_text", "")
            correct_answer = question_info.get("correct_answer", "")
            
            try:
                # Generate response from model
                response = unified_client.generate_chat(
                    question_text,
                    self.remote_model,
                    json_schema=schema,
                    context=context
                )
                
                # Extract and validate translation
                try:
                    translated = response.structured_data.get("translation", "").lower().strip()
                    
                    # Determine if answer is correct
                    if question_info.get("answer_type") == AnswerType.MULTIPLE_CHOICE.value:
                        # For multiple choice, validate against choices
                        choices = [c.lower() for c in question_info.get("choices", [])]
                        is_correct = translated in choices and translated == correct_answer.lower()
                    else:
                        # For free text, direct comparison
                        is_correct = translated == correct_answer.lower()
                    
                    # Prepare debug information
                    debug_info = None
                    if not is_correct:
                        debug_info = {
                            "response": response.structured_data.get("translation", ""),
                            "expected": correct_answer
                        }
                        
                        # Include language-specific details if available
                        for detail_field in ["origin_details", "target_details"]:
                            if detail_field in question_info:
                                debug_info[detail_field] = question_info[detail_field]
                
                except (KeyError, TypeError, AttributeError):
                    is_correct = False
                    debug_info = {
                        "error": "Failed to extract translation from response",
                        "response_data": response.structured_data
                    }
                
                # Create result
                score = 100 if is_correct else 0
                results.append(BenchmarkResult(
                    question_id=question_id,
                    score=score,
                    eval_msec=int(response.usage.total_msec),
                    debug_json=json.dumps(debug_info) if debug_info else None
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
        correct_count = sum(1 for r in results if r.score == 100)
        total_count = len(results)
        if total_count > 0:
            overall_score = int((correct_count / total_count) * 100)
        else:
            overall_score = 0
            
        logger.info(f"Translation benchmark complete: {correct_count}/{total_count} correct ({overall_score}%)")
        
        # Save results to database
        run_id = self.save_results(overall_score, results)
        return run_id
