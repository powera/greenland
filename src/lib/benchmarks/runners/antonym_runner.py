#!/usr/bin/python3

"""Runner for antonym benchmark."""

import json
import logging
from typing import Dict, Optional, Tuple, Any

from lib.benchmarks.base import BenchmarkRunner
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Define benchmark code for this runner
BENCHMARK_CODE = "0016_antonym"


@runner(BENCHMARK_CODE)
class AntonymRunner(BenchmarkRunner):
    """Benchmark for testing antonym identification abilities."""
    
    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt and context for antonym questions.
        
        Args:
            question_data: Question data from database
            
        Returns:
            Tuple of (prompt, schema, context)
        """
        prompt = question_data["question_text"]
        schema = question_data.get("schema", {
            "type": "object",
            "properties": {
                "antonym": {"type": "string"}
            },
            "required": ["antonym"]
        })
        
        context = """You are a linguistics assistant. For each question, identify which word from the provided 
candidates is the antonym of the given word. Respond with only the antonym word."""
        
        return prompt, schema, context
    
    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """Build debug information for antonym benchmark results."""
        return {
            "model_answer": response.structured_data.get("antonym", ""),
            "correct_answer": question_data["correct_answer"].get("antonym", ""),
            "is_correct": is_correct
        }