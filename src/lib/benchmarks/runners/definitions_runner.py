#!/usr/bin/python3

"""Word definitions benchmark runner implementation."""

import json
import logging
from typing import Dict, List, Optional, Tuple, Any

from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.data_models import (
    BenchmarkMetadata,
    AnswerType
)
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@runner("0020_definitions")
class DefinitionsRunner(BenchmarkRunner):
    """Runner for testing word definition abilities."""

    def __init__(self, model: str, metadata: BenchmarkMetadata):
        """Initialize runner with model name and benchmark metadata."""
        super().__init__(model, metadata)
        self.context = """You are taking a vocabulary test. Your task is to select the word that best matches 
a given definition from a list of choices. Respond with only the correct word, nothing else."""

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt and context for the definitions question.
        
        Args:
            question_data: Question data from database
            
        Returns:
            Tuple of (prompt, schema, context)
        """
        # Question data already contains the formatted question text
        prompt = question_data.get("question_text", "")
        
        # No schema needed for this benchmark
        schema = None
        
        return prompt, schema, self.context
        
    def evaluate_response(self, question_data: Dict, response: str) -> bool:
        """
        Evaluate if a response matches the correct word.
        
        Args:
            question_data: Question data from database
            response: Model response text
            
        Returns:
            Boolean indicating whether response is correct
        """
        correct_answer = question_data.get("correct_answer", "").lower()
        
        # Clean and normalize the response
        cleaned_response = response.strip().lower()
        # Remove any punctuation at the end
        cleaned_response = cleaned_response.rstrip(".,;:!?")
        
        # Check if response contains the correct word
        return cleaned_response == correct_answer