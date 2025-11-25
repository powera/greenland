#!/usr/bin/python3

"""Runner for the English-to-IPA benchmark."""

import json
import logging
import re
from typing import Dict, List, Tuple, Optional, Any

from lib.benchmarks.base_runner import BenchmarkRunner
from lib.benchmarks.data_models import BenchmarkMetadata, BenchmarkResult
from lib.benchmarks.factory import runner

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Define benchmark metadata
BENCHMARK_METADATA = BenchmarkMetadata(
    code="0061_english_to_ipa",
    name="English to IPA Pronunciation",
    description="A benchmark to evaluate a model's ability to convert English words to their IPA pronunciation."
)

@runner("0061_english_to_ipa")
class EnglishToIPARunner(BenchmarkRunner):
    """Runner for English-to-IPA benchmark."""
    
    def __init__(self, model: str, metadata: BenchmarkMetadata):
        """Initialize runner with model and benchmark metadata."""
        super().__init__(model, metadata)
    
    def prepare_prompt(self, question_data: Dict) -> Tuple[str, Optional[Dict], Optional[str]]:
        """
        Prepare prompt and context for the question.
        
        Args:
            question_data: Question data from database
            
        Returns:
            Tuple of (prompt, schema, context)
        """
        # Get the question text
        question_text = question_data.get("question_text", "")
        
        # Create a context that explains the task and expectations
        context = """You are a linguistic expert specializing in phonetics. 
Your task is to provide the IPA (International Phonetic Alphabet) pronunciation for English words.
Use American English pronunciation as your default standard.
Provide only the IPA transcription with no additional text or explanation.
Include stress markers and all appropriate IPA symbols.
"""
        
        # Create a prompt from the question text
        prompt = question_text
        
        # Define a schema to ensure the response is just the IPA
        schema = {
            "type": "object",
            "properties": {
                "ipa": {
                    "type": "string",
                    "description": "The IPA pronunciation of the word"
                }
            },
            "required": ["ipa"]
        }
        
        return prompt, schema, context
    
    def evaluate_response(self, question_data: Dict, response: Any) -> bool:
        """
        Evaluate if a response is correct according to question criteria.
        
        Args:
            question_data: Question data from database
            response: Model response (structured data with 'ipa' field)
            
        Returns:
            Boolean indicating whether response is correct
        """
        # Get the correct answer from the question data
        correct_answer = question_data.get("correct_answer", "")
        
        # Get the model's response
        if isinstance(response, dict) and "ipa" in response:
            model_answer = response["ipa"].strip()
        else:
            # If not a dict or doesn't have 'ipa' key, use the raw response
            model_answer = str(response).strip()
        
        # Clean up the IPA strings by removing extra spaces and normalizing
        model_answer = self._normalize_ipa(model_answer)
        correct_answer = self._normalize_ipa(correct_answer)
        
        # Check if the model's answer matches the correct answer
        if model_answer == correct_answer:
            return True
        
        # Check against alternative pronunciations if available
        if "evaluation_criteria" in question_data and "alternatives" in question_data["evaluation_criteria"]:
            alternatives = question_data["evaluation_criteria"]["alternatives"]
            for alt in alternatives:
                normalized_alt = self._normalize_ipa(alt)
                if model_answer == normalized_alt:
                    return True
        
        # Check for close matches with slight variations (allow small differences)
        if self._is_close_match(model_answer, correct_answer):
            return True
            
        # If we get here, the answer is incorrect
        return False
    
    def _normalize_ipa(self, ipa_string: str) -> str:
        """
        Normalize an IPA string for consistent comparison.
        
        Args:
            ipa_string: The IPA string to normalize
            
        Returns:
            Normalized IPA string
        """
        # Remove any text that's not part of the IPA (common with model responses)
        # Look for brackets, slashes, or other common IPA delimiters
        ipa_markers = [
            (r'/(.+?)/', r'\1'),  # Extract content between /.../ slashes
            (r'\[(.+?)\]', r'\1'),  # Extract content between [...] brackets
            (r'\((.+?)\)', r'\1'),  # Extract content between (...) parentheses
        ]
        
        # Try to extract IPA from delimiters
        extracted = ipa_string
        for pattern, replacement in ipa_markers:
            match = re.search(pattern, ipa_string)
            if match:
                extracted = re.sub(pattern, replacement, ipa_string)
                break
        
        # Remove any surrounding whitespace
        normalized = extracted.strip()
        
        # Remove any explanatory text before or after the IPA
        # This is a simple heuristic - we look for the longest contiguous segment with IPA-like characters
        ipa_chars = set("ɪiɛeæaɑɔoʊuʌəɚɝɜː̩̯̆͡ˌˈʰʷ.ptksʒʃθðŋnmɹrlvfbdgzʤʧywχѲ")
        segments = re.findall(r'[^\s,;:]+', normalized)
        if segments:
            # Find the segment with the highest percentage of IPA characters
            best_segment = max(segments, key=lambda s: sum(1 for c in s.lower() if c in ipa_chars) / len(s) if len(s) > 0 else 0)
            if best_segment and sum(1 for c in best_segment.lower() if c in ipa_chars) / len(best_segment) > 0.5:
                normalized = best_segment
        
        return normalized
    
    def _is_close_match(self, model_answer: str, correct_answer: str, threshold: float = 0.8) -> bool:
        """
        Check if the model's answer is a close match to the correct answer.
        
        Args:
            model_answer: The model's IPA answer
            correct_answer: The correct IPA answer
            threshold: Similarity threshold (0-1)
            
        Returns:
            Boolean indicating whether the answers are close enough
        """
        # If either string is empty, they're not close
        if not model_answer or not correct_answer:
            return False
        
        # Compare character by character and count matches
        # Allow for slight variations in symbols, especially for similar sounds
        similar_chars = {
            "i": set(["i", "ɪ", "iː"]),
            "ɪ": set(["ɪ", "i", "iː"]),
            "e": set(["e", "ɛ", "eɪ"]),
            "ɛ": set(["ɛ", "e", "eɪ"]),
            "æ": set(["æ", "a", "ɑ"]),
            "a": set(["a", "æ", "ɑ"]),
            "ɑ": set(["ɑ", "a", "æ", "ɒ"]),
            "ɒ": set(["ɒ", "ɑ", "o", "ɔ"]),
            "ɔ": set(["ɔ", "o", "ɒ"]),
            "o": set(["o", "ɔ", "ɒ", "oʊ"]),
            "u": set(["u", "ʊ", "uː"]),
            "ʊ": set(["ʊ", "u", "uː"]),
            "ʌ": set(["ʌ", "ə", "ɜ"]),
            "ə": set(["ə", "ʌ", "ɜ", "ɚ"]),
            "ɝ": set(["ɝ", "ɚ", "ɜ"]),
            "ɚ": set(["ɚ", "ɝ", "ə"]),
            "ɹ": set(["ɹ", "r"]),
            "r": set(["r", "ɹ"]),
            "t": set(["t", "ɾ"]),  # Especially for American English
            "ɾ": set(["ɾ", "t"]),
        }
        
        # Count match points
        total_points = max(len(model_answer), len(correct_answer))
        match_points = 0
        
        # Dynamic programming approach for alignment and scoring
        m, n = len(model_answer), len(correct_answer)
        if m == 0 or n == 0:
            return False
            
        # Simple character-by-character comparison
        for i in range(min(m, n)):
            if model_answer[i] == correct_answer[i]:
                match_points += 1
            elif model_answer[i] in similar_chars.get(correct_answer[i], set()) or\
                 correct_answer[i] in similar_chars.get(model_answer[i], set()):
                match_points += 0.5
        
        # Calculate similarity ratio
        similarity = match_points / total_points
        
        return similarity >= threshold
    
    
    def build_debug_info(self, question_data: Dict, response: Any, is_correct: bool) -> Dict:
        """Build debug information for benchmark results."""
        # Extract model's answer based on response type
        if hasattr(response, "structured_data") and isinstance(response.structured_data, dict) and "ipa" in response.structured_data:
            # Response object with structured data
            model_answer = response.structured_data["ipa"]
        elif isinstance(response, dict) and "ipa" in response:
            # Direct dictionary with ipa key
            model_answer = response["ipa"]
        elif hasattr(response, "response_text"):
            # Response object with text
            model_answer = response.response_text
        else:
            # Any other format
            model_answer = str(response)
            
        # Get the correct answer
        correct_answer = question_data.get("correct_answer", "")
            
        # Simplified debug info with just essential information
        return {
            "response": model_answer,
            "expected": correct_answer,
            "is_correct": is_correct
        }