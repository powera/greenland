#!/usr/bin/python3

"""Spell check benchmark runner implementation."""

import logging
from typing import Dict, Optional, Tuple, Any

from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.data_models import BenchmarkMetadata
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Define benchmark code
BENCHMARK_CODE = "0015_spell_check"


@runner(BENCHMARK_CODE)
class SpellCheckRunner(BenchmarkRunner):
    """Runner for evaluating model performance on spell check benchmark."""
    
    def __init__(self, model: str, metadata: BenchmarkMetadata):
        super().__init__(model, metadata)
        self.context = """You are a spell checking assistant. For each sentence, identify:
1. The incorrectly spelled word exactly as it appears
2. The correct spelling of that word"""

    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt, schema, and context for the question.
        
        Args:
            question_data: Question data from database
            
        Returns:
            Tuple of (prompt, schema, context)
        """
        question_text = question_data.get("question_text", "")
        schema = question_data.get("schema")
        
        return question_text, schema, self.context
    
    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if a response is correct according to question criteria.
        
        Args:
            question_data: Question data from database
            response: Model response (dictionary with incorrect/correct)
            
        Returns:
            Boolean indicating whether the response is correct
        """
        if not isinstance(response, dict):
            return False
            
        correct_answer = question_data.get("correct_answer", {})
        
        # Check if both incorrect and correct fields match
        return (response.get("incorrect", "").lower() == correct_answer.get("incorrect", "").lower() and
                response.get("correct", "").lower() == correct_answer.get("correct", "").lower())