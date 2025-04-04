#!/usr/bin/python3

"""Runner for the lemma identification benchmark."""

import json
import logging
from typing import Dict, List, Tuple, Optional, Any

from lib.benchmarks.base_runner import BenchmarkRunner
from lib.benchmarks.data_models import (
    BenchmarkMetadata, BenchmarkResult, AnswerType
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LemmaRunner(BenchmarkRunner):
    """Runner for lemma identification benchmark."""
    
    def __init__(self, model: str, metadata: BenchmarkMetadata):
        """Initialize runner with model name and benchmark metadata."""
        super().__init__(model, metadata)
    
    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt for the question.
        
        Args:
            question_data: Question data from database
            
        Returns:
            Tuple of (prompt, schema, context)
        """
        # Extract the question text
        prompt = question_data["question_text"]
        
        # Define JSON schema for structured response
        schema = {
            "type": "object",
            "properties": {
                "lemma": {
                    "type": "string",
                    "description": "The lemma (base form) of the word"
                }
            },
            "required": ["lemma"]
        }
        
        # Define system context/instructions
        context = """
        You are a linguistic expert specialized in lemmatization.
        
        Lemmatization is the process of finding the base form (lemma) of a word:
        - For nouns: the singular form (e.g., "cats" → "cat")
        - For verbs: the infinitive form without "to" (e.g., "running" → "run")
        - For adjectives and adverbs: the positive form (e.g., "better" → "good")
        
        For each word you are given, identify and return only its lemma.
        """
        
        return prompt, schema, context
    
    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if a response is correct.
        
        Args:
            question_data: Question data from database
            response: Model response (structured data or text)
            
        Returns:
            Boolean indicating whether response is correct
        """
        correct_answer = question_data.get("correct_answer", "").lower()
        
        # Handle structured response
        if isinstance(response, dict) and "lemma" in response:
            actual_answer = response["lemma"].lower()
        # Handle text response
        else:
            # Try to extract just the lemma word from possible text
            response_text = str(response).lower()
            
            # First look for the word itself without punctuation
            words = [word.strip(".,;:\"'?!") for word in response_text.split()]
            
            # Check if the correct answer is one of the words
            if correct_answer in words:
                return True
                
            # If not found, use the first word as the answer
            actual_answer = words[0] if words else ""
        
        # Compare answers (case-insensitive)
        return actual_answer == correct_answer
    
    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """Build debug information for benchmark results."""
        inflected_word = ""
        question_text = question_data.get("question_text", "")
        
        # Extract the inflected word from the question text
        if "'" in question_text:
            parts = question_text.split("'")
            if len(parts) >= 3:
                inflected_word = parts[1]
        
        # Format the debug info
        if hasattr(response, 'structured_data') and response.structured_data:
            return {
                "inflected_word": inflected_word,
                "model_response": response.structured_data.get("lemma", ""),
                "correct_lemma": question_data.get("correct_answer", ""),
                "response_text": response.response_text,
                "is_correct": is_correct
            }
        else:
            return {
                "inflected_word": inflected_word,
                "model_response": str(response),
                "correct_lemma": question_data.get("correct_answer", ""),
                "is_correct": is_correct
            }