#!/usr/bin/python3

"""Translation benchmark runner implementation."""

import json
import logging
from typing import Dict, List, Optional, Tuple, Any

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
        if len(parts) == 4:
            self.origin_lang = parts[2]
            self.target_lang = parts[3]
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
    
    @staticmethod
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
    
    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt, schema, and context for the translation question.
        
        Args:
            question_data: Question data from database
            
        Returns:
            Tuple of (prompt, schema, context)
        """
        # Extract question text
        question_text = question_data.get("question_text", "")
        
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
        
        return question_text, schema, context
        
    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if a translation response is correct.
        
        Args:
            question_data: Question data from database
            response: Model response (dictionary with translation key)
            
        Returns:
            Boolean indicating whether response is correct
        """
        # Get correct answer from question data
        correct_answer = question_data.get("correct_answer", "").lower()
        
        # Extract translation from response
        try:
            translated = response.get("translation", "").lower().strip()
            
            # Determine if answer is correct
            if question_data.get("answer_type") == AnswerType.MULTIPLE_CHOICE.value:
                # For multiple choice, validate against choices
                choices = [c.lower() for c in question_data.get("choices", [])]
                is_correct = translated in choices and translated == correct_answer
            else:
                # For free text, direct comparison
                is_correct = translated == correct_answer
                
            return is_correct
            
        except (KeyError, TypeError, AttributeError):
            return False
    
    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """
        Build debug information for translation benchmark results.
        
        Args:
            question_data: Question data from database
            response: Response object from unified_client
            is_correct: Whether the response was correct
            
        Returns:
            Dictionary with debug information
        """
        debug_info = {
            "response": response.structured_data.get("translation", ""),
            "expected": question_data.get("correct_answer"),
            "is_correct": is_correct
        }
        
        # Include language-specific details if available
        for detail_field in ["origin_details", "target_details"]:
            if detail_field in question_data:
                debug_info[detail_field] = question_data[detail_field]
                
        return debug_info