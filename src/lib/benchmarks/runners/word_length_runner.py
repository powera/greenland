#!/usr/bin/python3

"""Runner for word length benchmark."""

import logging
from typing import Dict, Optional, Any, Tuple

from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

@runner("0011_word_length")
class WordLengthRunner(BenchmarkRunner):
    """Runner for testing a model's ability to count the total number of letters in words."""
    
    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt for word length question.
        
        Args:
            question_data: Question data from database
            
        Returns:
            Tuple of (prompt, schema, context)
        """
        prompt = question_data.get("question_text", "")
        
        # Define schema for structured response
        schema = {
            "type": "object",
            "properties": {
                "length": {
                    "type": "integer",
                    "description": "The number of letters in the word"
                }
            },
            "required": ["length"]
        }
        
        # Add context for guidance
        context = """You are performing a word length counting task. 
Count the total number of letters in the word.
Provide your answer as a single integer in the specified JSON format.
Only count alphabetic characters (a-z, A-Z) and exclude any spaces, numbers, or punctuation."""
        
        return prompt, schema, context
        
    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if the word length count is correct.
        
        Args:
            question_data: Question data from database
            response: Model response (structured dictionary)
            
        Returns:
            Boolean indicating whether the response is correct
        """
        expected_length = int(question_data.get("correct_answer", 0))
        
        # Extract length from response
        actual_length = None
        if isinstance(response, dict) and "length" in response:
            try:
                actual_length = int(response["length"])
            except (ValueError, TypeError):
                return False
        else:
            # Try to parse response as a direct number
            try:
                actual_length = int(response)
            except (ValueError, TypeError):
                return False
                
        # Check for exact match (word length should be exact)
        return actual_length == expected_length
        
    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """Build debug information for benchmark results."""
        # Create debug info with the question text for better context
        if hasattr(response, "structured_data") and response.structured_data:
            return {
                "prompt": question_data.get("question_text", ""),
                "response": response.structured_data,
                "expected": question_data.get("correct_answer"),
                "is_correct": is_correct
            }
        else:
            return {
                "prompt": question_data.get("question_text", ""),
                "response": response.response_text,
                "expected": question_data.get("correct_answer"),
                "is_correct": is_correct
            }